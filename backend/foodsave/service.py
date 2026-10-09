from . import welcome, nearby
from .nearby_queries import query as nearby_query
import hmac
import os
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from .db import engine, execute, one, rows
from .security import digest, hash_password, verify_password, weighted_choice


def uid():
    return str(uuid4())


def fail(status, detail):
    raise HTTPException(status, detail)


def dump(value):
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def require(user, *roles):
    if user['role'] not in roles:
        fail(403, '此帳號無操作權限')


def require_vendor(user):
    # is_vendor is derived from store ownership during authentication, never a
    # client-supplied role. Legacy vendor accounts retain their existing access.
    if user['role'] != 'vendor' and not (user['role'] == 'consumer' and user.get('is_vendor')):
        fail(403, '此帳號無操作權限')


def lock_store_mode(c, store_id):
    # Same transaction-owned guard for reservation creation and mode changes.
    execute(c, "DECLARE @r int; EXEC @r=sp_getapplock @Resource=:resource, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000; IF @r<0 THROW 51000,'Store operation busy',1;", resource='foodsave:store-mode:'+store_id)


def audit(c, actor, action, target):
    execute(c, 'INSERT INTO dbo.audit_logs(id,actor_id,action,target_id) VALUES(:id,:actor,:action,:target)',
            id=uid(), actor=actor, action=action, target=target)


def award(c, user, event, source):
    rule = one(c, 'SELECT amount FROM dbo.exp_rules WHERE event=:event AND enabled=1', event=event)
    key = event + ':' + source
    if rule and not one(c, 'SELECT id FROM dbo.exp_events WHERE event_key=:key', key=key):
        execute(c, 'INSERT INTO dbo.exp_events(id,user_id,event_key,amount) VALUES(:id,:u,:key,:amount)',
                id=uid(), u=user, key=key, amount=rule['amount'])


class Service:
    def __init__(self, database=None):
        self.database = database

    def transaction(self):
        return (self.database or engine()).begin()

    def throttle(self, action, client, limit=10, window_seconds=900):
        # Separate committed transaction: failed authentication still consumes quota.
        bucket = digest(action + ':' + client)
        with self.transaction() as c:
            rate = one(c, 'SELECT attempts,window_start FROM dbo.rate_limits WITH (UPDLOCK,HOLDLOCK) WHERE bucket=:b', b=bucket)
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            if not rate:
                execute(c, 'INSERT INTO dbo.rate_limits(bucket,attempts,window_start) VALUES(:b,1,:now)', b=bucket, now=now)
            elif now - rate['window_start'] >= timedelta(seconds=window_seconds):
                execute(c, 'UPDATE dbo.rate_limits SET attempts=1,window_start=:now WHERE bucket=:b', b=bucket, now=now)
            elif rate['attempts'] >= limit:
                fail(429, '嘗試次數過多，請稍後再試')
            else:
                execute(c, 'UPDATE dbo.rate_limits SET attempts=attempts+1 WHERE bucket=:b', b=bucket)

    def register(self, email, password, role='consumer'):
        with self.transaction() as c:
            if one(c, 'SELECT id FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE email=:e', e=email):
                fail(409, '無法建立此帳號')
            identity = uid()
            execute(c, 'INSERT INTO dbo.users(id,email,password_hash,role) VALUES(:id,:e,:p,:r)',
                    id=identity, e=email, p=hash_password(password), r=role)
            return {'id': identity, 'email': email, 'role': role}

    def login(self, email, password):
        with self.transaction() as c:
            user = one(c, 'SELECT * FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE email=:e AND active=1', e=email)
            # Same expensive hash work for nonexistent users.
            valid = verify_password(password, user['password_hash']) if user else bool(hash_password(password)) and False
            if not valid:
                # Legacy hashes have a lower cost. Pad failed legacy checks with
                # current-cost hashing rather than making them a cheap oracle.
                if user and user['password_hash'].startswith('scrypt$'):
                    hash_password(password)
                fail(401, '帳號或密碼不正確')
            if os.getenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED')=='true' and user['password_hash'].startswith('scrypt$'):
                upgraded=one(c,'EXEC dbo.apply_account_password @user_id=:u,@expected_hash=:old,@new_hash=:new,@verify_email=0',u=user['id'],old=user['password_hash'],new=hash_password(password))
                if not upgraded or upgraded['changed']!=1:
                    fail(401,'帳號或密碼不正確')
            if os.getenv('FOODSAVE_WELCOME_SPIN_ENABLED')=='true':
                welcome.grant_once(c,user['id'])
            token = secrets.token_urlsafe(32)
            execute(c, 'INSERT INTO dbo.sessions(token_hash,user_id,expires_at) VALUES(:h,:u,DATEADD(hour,12,SYSUTCDATETIME()))', h=digest(token), u=user['id'])
            return {'access_token': token, 'token_type': 'bearer', 'expires_in': 43200}

    def authenticate(self, token):
        with self.transaction() as c:
            user = one(c, 'SELECT u.id,u.email,u.role,CASE WHEN EXISTS(SELECT 1 FROM dbo.stores owned WHERE owned.owner_id=u.id) THEN 1 ELSE 0 END AS is_vendor FROM dbo.sessions s JOIN dbo.users u ON u.id=s.user_id WHERE s.token_hash=:h AND s.expires_at>SYSUTCDATETIME() AND u.active=1', h=digest(token))
            if not user:
                fail(401, '請重新登入')
            return dict(user)

    def logout(self, token):
        with self.transaction() as c:
            execute(c, 'DELETE FROM dbo.sessions WHERE token_hash=:h', h=digest(token))
        return {'logged_out': True}

    def mutate(self, user, operation, key, payload, action):
        fingerprint = digest(dump(payload))
        with self.transaction() as c:
            # Consistent lock first for every user mutation; serializes retries even
            # with Azure SQL READ_COMMITTED_SNAPSHOT enabled.
            current = one(c, 'SELECT id,role FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id=:u AND active=1', u=user['id'])
            if not current or current['role'] != user['role']:
                fail(401, '帳號狀態已變更，請重新登入')
            old = one(c, 'SELECT fingerprint,response FROM dbo.request_results WHERE user_id=:u AND operation=:op AND request_key=:k', u=user['id'], op=operation, k=key)
            if old:
                if not hmac.compare_digest(old['fingerprint'], fingerprint):
                    fail(409, '相同重試識別碼不可用於不同內容')
                cached=json.loads(old['response'])
                if cached.get('terminal_reason') and operation in ('reserve','pickup-preview'):
                    fail(410, '此預約已移除，請查看通知與最新庫存')
                self._authorize_cached_order(c, user, operation, payload, cached)
                return cached
            result = action(c)
            execute(c, 'INSERT INTO dbo.request_results(user_id,operation,request_key,fingerprint,response) VALUES(:u,:op,:k,:f,:r)',
                    u=user['id'], op=operation, k=key, f=fingerprint, r=dump(result))
            return json.loads(dump(result))

    def _authorize_cached_order(self, c, user, operation, payload, cached):
        # A previous success is not an authorization grant. Recheck even for
        # legacy cached replies before returning pickup credentials or receipts.
        if operation == 'store-location':
            if not one(c, 'SELECT id FROM dbo.stores WHERE id=:id AND owner_id=:u', id=payload['id'], u=user['id']):
                fail(404, '找不到此商家店舖')
            return
        if operation not in ('reserve', 'transition', 'pickup-preview', 'pickup-confirm', 'review'):
            return
        merchant = operation in ('pickup-preview', 'pickup-confirm') or (operation == 'transition' and payload['target'] == 'completed')
        if cached.get('terminal_reason'):
            self.terminal_result(c, user, cached['id'], merchant=merchant)
            return
        identity = cached.get('reservation_id') if operation == 'review' else cached.get('id')
        order = one(c, 'SELECT r.user_id,s.owner_id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE r.id=:id', id=identity)
        if not order or order['owner_id' if merchant else 'user_id'] != user['id']:
            fail(404, '找不到預約')
        if (merchant or operation in ('reserve', 'review')) and order['user_id'] == order['owner_id']:
            fail(403, '不能預約或核銷自己的商品')

    def reserve(self, user, key, product_id, quantity):
        require(user, 'consumer', 'vendor')
        def action(c):
            if one(c, "SELECT TOP (1) id FROM dbo.reservations WHERE user_id=:u AND product_id=:p AND state='waiting' AND expires_at>SYSUTCDATETIME()", u=user['id'], p=product_id):
                fail(409, '你已保留此商品，請到我的預約查看')
            lookup = one(c, 'SELECT store_id FROM dbo.products WHERE id=:id', id=product_id)
            if not lookup:
                fail(404, '商品不存在或已截止')
            lock_store_mode(c, lookup['store_id'])
            p = one(c, 'SELECT * FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:p AND active=1 AND pickup_deadline>SYSUTCDATETIME()', p=product_id)
            if not p:
                fail(404, '商品不存在或已截止')
            store = one(c, 'SELECT owner_id,service_mode,latitude,longitude,location_revision,location_confirmed FROM dbo.stores WITH(UPDLOCK,HOLDLOCK) WHERE id=:id', id=p['store_id'])
            if store and store['owner_id'] == user['id']:
                fail(403, '不能預約自己的商品')
            if not store or store['service_mode'] != 'reservation':
                fail(409, '此店僅提供庫存資訊，不能在App保留商品；請以現場為準')
            if not store['location_confirmed']:
                fail(409, '店家尚未確認取貨位置')
            for old in rows(c, "SELECT TOP (25) id FROM dbo.reservations WHERE product_id=:p AND state IN ('waiting','expired') AND expires_at<=SYSUTCDATETIME() ORDER BY expires_at,id",p=product_id):
                one(c, 'EXEC dbo.expire_reservation @reservation_id=:id',id=old['id'])
            result = execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity-:q,revision=revision+1 WHERE id=:p AND available_quantity>=:q', p=product_id, q=quantity)
            if result.rowcount != 1:
                fail(409, '商品庫存不足')
            identity, code = uid(), secrets.token_hex(6).upper()
            qr = 'FS1.' + secrets.token_urlsafe(32)
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            expiry = min(now + timedelta(minutes=30), p['pickup_deadline'])
            snapshot = {k: p[k] for k in ('name','store_id','original_price_minor','sale_price_minor','photo_url')}
            if store:
                snapshot.update(latitude=float(store['latitude']), longitude=float(store['longitude']), location_revision=store['location_revision'])
            execute(c, "INSERT INTO dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,'waiting',:q,:snapshot,:code,:expiry)",
                    id=identity, u=user['id'], p=product_id, q=quantity, snapshot=dump(snapshot), code=digest(code), expiry=expiry)
            return {'id': identity, 'state': 'waiting', 'quantity': quantity, 'pickup_code': code, 'pickup_qr': qr, 'expires_at': expiry, 'snapshot': snapshot}
        return self.mutate(user, 'reserve', key, {'product_id': product_id, 'quantity': quantity}, action)

    def transition(self, user, key, reservation_id, target, code=''):
        if target not in ('cancelled', 'completed'):
            fail(422, '預約狀態不正確')
        if target == 'cancelled':
            require(user, 'consumer', 'vendor')
        else:
            require_vendor(user)
        def action(c):
            return self._transition(c, user, reservation_id, target, code)
        return self.mutate(user, 'transition', key, {'id': reservation_id, 'target': target, 'code_hash': digest(code)}, action)

    def terminal_result(self, c, user, reservation_id, merchant=None):
        terminal=one(c, 'SELECT reservation_id,user_id,vendor_id,reason FROM dbo.reservation_terminals WHERE reservation_id=:id',id=reservation_id)
        allowed = terminal and user['role'] in ('consumer', 'vendor') and (
            user['id'] in (terminal['user_id'], terminal['vendor_id']) if merchant is None
            else terminal['vendor_id' if merchant else 'user_id'] == user['id'])
        if not allowed:
            fail(404, '找不到預約')
        if merchant and terminal['user_id'] == terminal['vendor_id']:
            fail(403, '不能核銷自己的商品')
        return {'id':reservation_id,'state':'expired' if terminal['reason']=='expired' else 'removed','terminal_reason':terminal['reason']}

    def _transition(self, c, user, reservation_id, target, code='', reviewed=False):
        lookup=one(c,'SELECT r.product_id,p.store_id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id WHERE r.id=:id',id=reservation_id)
        if not lookup:
            return self.terminal_result(c,user,reservation_id,merchant=target=='completed')
        lock_store_mode(c,lookup['store_id'])
        product=one(c,'SELECT p.id,s.owner_id FROM dbo.products p WITH(UPDLOCK,HOLDLOCK) JOIN dbo.stores s ON s.id=p.store_id WHERE p.id=:p',p=lookup['product_id'])
        r=one(c,'SELECT *,SYSUTCDATETIME() AS now FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE id=:id',id=reservation_id)
        if not r:
            return self.terminal_result(c,user,reservation_id,merchant=target=='completed')
        if (target=='cancelled' and r['user_id']!=user['id']) or (target=='completed' and product['owner_id']!=user['id']):
            fail(404,'找不到預約')
        if target=='completed' and r['user_id']==product['owner_id']:
            fail(403,'不能核銷自己的商品')
        if r['state'] in ('waiting','expired') and r['expires_at']<=r['now']:
            one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=reservation_id)
            return self.terminal_result(c,user,reservation_id,merchant=target=='completed')
        if target=='completed' and not reviewed and not hmac.compare_digest(r['pickup_code_hash'],digest(code)):
            fail(400,'取貨碼不正確')
        if r['state']!='waiting':fail(409,'預約已處理')
        execute(c,"UPDATE dbo.reservations SET state=:state,completed_at=CASE WHEN :state='completed' THEN SYSUTCDATETIME() ELSE NULL END WHERE id=:id",state=target,id=reservation_id)
        if target=='cancelled':
            execute(c,'UPDATE dbo.products SET available_quantity=available_quantity+:q,revision=revision+1 WHERE id=:p',q=r['quantity'],p=r['product_id'])
        else:award(c,r['user_id'],'pickup',reservation_id)
        return {'id':reservation_id,'state':target}

    def preview_pickup(self, user, key, credential):
        """Read-only order verification; persist only a short-lived confirmation receipt."""
        require_vendor(user)
        def action(c):
            if credential.startswith('FS1.'):
                matches = rows(c, "SELECT r.*,SYSUTCDATETIME() AS now FROM dbo.request_results q JOIN dbo.reservations r ON JSON_VALUE(q.response,'$.id')=r.id AND q.user_id=r.user_id JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE q.operation='reserve' AND JSON_VALUE(q.response,'$.pickup_qr')=:credential AND s.owner_id=:vendor", credential=credential, vendor=user['id'])
            else:
                matches = rows(c, "SELECT r.*,SYSUTCDATETIME() AS now FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE r.pickup_code_hash=:hash AND s.owner_id=:vendor", hash=digest(credential), vendor=user['id'])
            if len(matches) != 1:
                fail(404, '找不到可領取的預約，請重新掃碼或確認取貨碼')
            order = matches[0]
            if order['user_id'] == user['id']:
                fail(403, '不能核銷自己的商品')
            if order['state'] != 'waiting' or order['expires_at'] <= order['now']:
                fail(409, '此預約已處理或逾時，請重新載入今日訂單')
            snapshot = json.loads(order['snapshot'])
            return {'id': order['id'], 'name': snapshot['name'], 'quantity': order['quantity'],
                    'unit_price_minor': snapshot['sale_price_minor'], 'total_price_minor': snapshot['sale_price_minor'] * order['quantity'],
                    'review_token': secrets.token_urlsafe(32), 'review_expires_at': min(order['expires_at'], order['now'] + timedelta(minutes=2))}
        # Credentials never become an idempotency key or log label.
        return self.mutate(user, 'pickup-preview', key, {'credential_hash': digest(credential)}, action)

    def confirm_pickup(self, user, key, review_key, review_token):
        require_vendor(user)
        def action(c):
            result = one(c, "SELECT response,SYSUTCDATETIME() AS now FROM dbo.request_results WHERE user_id=:u AND operation='pickup-preview' AND request_key=:key", u=user['id'], key=review_key)
            if not result:
                fail(404, '請先掃碼核對商品')
            receipt = json.loads(result['response'])
            if receipt.get('terminal_reason'):
                return self.terminal_result(c,user,receipt['id'],merchant=True)
            if not hmac.compare_digest(receipt['review_token'], review_token):
                fail(404, '請先掃碼核對商品')
            if datetime.fromisoformat(receipt['review_expires_at']) <= result['now']:
                fail(409, '核對已逾時，請重新掃碼')
            # Recheck store ownership, order state and expiry under product/order locks.
            # The receipt is bound to this authenticated vendor and reservation.
            return self._transition(c, user, receipt['id'], 'completed', reviewed=True)
        return self.mutate(user, 'pickup-confirm', key, {'review_key': review_key, 'token_hash': digest(review_token)}, action)

    def draw(self, user, key):
        require(user, 'consumer', 'vendor')
        def action(c):
            grant = one(c, 'SELECT TOP (1) id FROM dbo.spin_grants WITH(UPDLOCK,HOLDLOCK) WHERE user_id=:u AND remaining>0 AND expires_at>SYSUTCDATETIME() ORDER BY expires_at,id', u=user['id'])
            if not grant:
                fail(409, '目前沒有可用抽獎次數')
            prizes = rows(c, 'SELECT * FROM dbo.prizes WITH(UPDLOCK,HOLDLOCK) WHERE enabled=1 AND remaining>0 AND expires_at>SYSUTCDATETIME() ORDER BY id')
            if not prizes:
                fail(409, '獎品尚未開放，未扣除次數')
            prize = weighted_choice(prizes)
            execute(c, 'UPDATE dbo.spin_grants SET remaining=remaining-1 WHERE id=:id', id=grant['id'])
            execute(c, 'UPDATE dbo.prizes SET remaining=remaining-1 WHERE id=:id', id=prize['id'])
            identity = uid()
            snapshot = {k: prize[k] for k in ('id','name','kind','terms','expires_at','discount_percent')}
            execute(c, 'INSERT INTO dbo.draws(id,user_id,grant_id,prize_id,prize_snapshot) VALUES(:id,:u,:g,:p,:s)', id=identity, u=user['id'], g=grant['id'], p=prize['id'], s=dump(snapshot))
            result = {'id': identity, 'prize': snapshot, 'segments': [{'id': p['id'], 'name': p['name']} for p in prizes]}
            if prize['kind'] == 'coupon':
                code = secrets.token_urlsafe(24)
                execute(c, "INSERT INTO dbo.coupons(id,draw_id,user_id,code,state,expires_at) VALUES(:id,:d,:u,:code,'available',:expires)", id=uid(), d=identity, u=user['id'], code=code, expires=prize['expires_at'])
                result['coupon_code'] = code
            return result
        return self.mutate(user, 'draw', key, {}, action)

    def list_products(self):
        self.expire_reservations(limit=25)
        with self.transaction() as c:
            products = rows(c, "SELECT p.id,p.store_id,s.name AS store_name,s.owner_id AS vendor_id,s.latitude,s.longitude,s.service_mode,p.name,p.photo_url,p.original_price_minor,p.sale_price_minor,p.available_quantity,p.pickup_deadline,p.revision,updates.source_updated_at,SYSUTCDATETIME() AS checked_at FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id JOIN dbo.users u ON u.id=s.owner_id OUTER APPLY (SELECT MAX(q.created_at) AS source_updated_at FROM dbo.request_results q WHERE q.operation IN ('product.save','stock-adjust','stock-loss') AND JSON_VALUE(q.response,'$.id')=p.id) updates WHERE s.location_confirmed=1 AND u.active=1 AND u.role IN ('consumer','vendor') AND p.active=1 AND p.pickup_deadline>SYSUTCDATETIME() ORDER BY p.id")
            result=[]
            for row in products:
                item=dict(row);updated=item.pop('source_updated_at');checked=item.pop('checked_at')
                item.update(source='foodsave', sourceUpdatedAt=updated, checkedAt=checked, stale=updated is None or checked-updated>timedelta(minutes=30), sourceURL=None)
                result.append(item)
            return result

    def nearby_stores(self, latitude, longitude, limit=50, cursor=None):
        parameters, scope = nearby.parameters('stores', latitude, longitude, limit, cursor)
        sql, bindings = nearby_query('stores', parameters)
        with self.transaction() as c:
            items = rows(c, sql, **bindings)
        return nearby.page(items, limit, scope)

    def nearby_products(self, latitude, longitude, limit=50, cursor=None, store_id=None):
        parameters, scope = nearby.parameters('products', latitude, longitude, limit, cursor, store_id)
        sql, bindings = nearby_query('products', parameters, store_id)
        with self.transaction() as c:
            items = rows(c, sql, **bindings)
        page = nearby.page(items, limit, scope)
        for item in page['items']:
            updated = item.pop('source_updated_at')
            checked = item.pop('checked_at')
            item.update(source='foodsave', sourceUpdatedAt=updated, checkedAt=checked,
                        stale=updated is None or checked-updated>timedelta(minutes=30), sourceURL=None)
        return page

    def account(self, user):
        with self.transaction() as c:
            return {**user, **(welcome.status(c,user['id']) if os.getenv('FOODSAVE_WELCOME_SPIN_ENABLED')=='true' else {}), 'exp': one(c, 'SELECT COALESCE(SUM(amount),0) AS total FROM dbo.exp_events WHERE user_id=:u', u=user['id'])['total'],
                    'spins': one(c, 'SELECT COALESCE(SUM(remaining),0) AS total FROM dbo.spin_grants WHERE user_id=:u AND expires_at>SYSUTCDATETIME()', u=user['id'])['total']}

    def history(self, user, resource):
        if resource == 'reservations':
            self.expire_reservations(limit=25, user_id=user['id'])
        queries = {
            'reservations': "SELECT r.id,r.product_id,r.state,r.quantity,r.snapshot,r.expires_at,r.completed_at,(SELECT TOP (1) JSON_VALUE(q.response,'$.pickup_code') FROM dbo.request_results q WHERE q.user_id=r.user_id AND q.operation='reserve' AND JSON_VALUE(q.response,'$.id')=r.id) AS pickup_code,(SELECT TOP (1) JSON_VALUE(q.response,'$.pickup_qr') FROM dbo.request_results q WHERE q.user_id=r.user_id AND q.operation='reserve' AND JSON_VALUE(q.response,'$.id')=r.id) AS pickup_qr,(SELECT JSON_VALUE(q.response,'$.reason') FROM dbo.request_results q WHERE q.user_id=r.user_id AND q.operation='vendor-closed' AND q.request_key='vendor-closed:'+r.id) AS cancellation_reason FROM dbo.reservations r WHERE r.user_id=:u ORDER BY r.created_at DESC",
            'draws': 'SELECT d.id,d.prize_snapshot,d.created_at,c.code AS coupon_code FROM dbo.draws d LEFT JOIN dbo.coupons c ON c.draw_id=d.id WHERE d.user_id=:u ORDER BY d.created_at DESC',
        }
        with self.transaction() as c:
            return [dict(r) for r in rows(c, queries[resource] + ' OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY', u=user['id'])]

    def public_prizes(self):
        with self.transaction() as c:
            return [dict(r) for r in rows(c, 'SELECT id,name,kind,terms,expires_at,discount_percent FROM dbo.prizes WHERE enabled=1 AND remaining>0 AND expires_at>SYSUTCDATETIME() ORDER BY id')]

    def favorites(self, user):
        with self.transaction() as c:
            return [r['vendor_id'] for r in rows(c, 'SELECT vendor_id FROM dbo.favorites WHERE user_id=:u', u=user['id'])]

    def store_reviews(self, store_id):
        with self.transaction() as c:
            summary = one(c, 'SELECT COUNT(*) AS count,AVG(CAST(v.rating AS decimal(4,2))) AS average FROM dbo.reviews v JOIN dbo.reservations r ON r.id=v.reservation_id JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s', s=store_id)
            items = rows(c, 'SELECT v.rating,v.body,v.created_at FROM dbo.reviews v JOIN dbo.reservations r ON r.id=v.reservation_id JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s ORDER BY v.created_at DESC OFFSET 0 ROWS FETCH NEXT 50 ROWS ONLY', s=store_id)
            return {**dict(summary), 'items': [dict(r) for r in items]}

    def request_deletion(self, user, password):
        with self.transaction() as c:
            current=one(c,'SELECT password_hash,active,CASE WHEN EXISTS(SELECT 1 FROM dbo.stores WHERE owner_id=:u) THEN 1 ELSE 0 END AS owns_store FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id=:u',u=user['id'])
            if not current or not verify_password(password,current['password_hash']):fail(401,'請確認密碼')
            owns_store = user['role']=='vendor' or bool(current.get('owns_store'))
            existing=one(c,'SELECT id,state FROM dbo.deletion_requests WHERE user_id=:u',u=user['id'])
            if existing:
                if owns_store and existing['state']=='requested':
                    result=one(c,'EXEC dbo.close_vendor_business @vendor_id=:u',u=user['id'])
                    if result['outcome']!='closed':fail(409,'店家刪除尚未完成，請重試')
                return {'id':existing['id'],'state':existing['state'],'account_disabled':not bool(current['active']),'erasure_completed':existing['state']=='completed'}
            if not current['active']:fail(403,'帳號目前無法提出此申請，請聯絡營運者')
            # Own consumer reservations use ordinary cancellation semantics.
            # Vendor business orders are removed by the restricted procedure below.
            pending=rows(c,"SELECT id FROM dbo.reservations WHERE user_id=:u AND state='waiting' ORDER BY product_id,id",u=user['id'])
            for item in pending:
                try:
                    self._transition(c,{'id':user['id'],'role':'consumer'},item['id'],'cancelled')
                except HTTPException as error:
                    if error.status_code!=409:raise  # Concurrent completion is retained.
            identity=uid()
            execute(c,'EXEC dbo.submit_deletion_request @request_id=:id,@user_id=:u',id=identity,u=user['id'])
            execute(c,'UPDATE dbo.users SET active=0 WHERE id=:u',u=user['id'])
            execute(c,'DELETE FROM dbo.sessions WHERE user_id=:u',u=user['id'])
            if owns_store:
                result=one(c,'EXEC dbo.close_vendor_business @vendor_id=:u',u=user['id'])
                if result['outcome']!='closed':fail(409,'店家刪除尚未完成，請重試')
            audit(c,user['id'],'account.deletion_requested',identity)
            return {'id':identity,'state':'requested','account_disabled':True,'erasure_completed':False}

    def deletion_with_credentials(self, email, password, submit=False):
        # No session is issued: this remains usable after a lost deletion reply
        # has already disabled the account and revoked every existing session.
        with self.transaction() as c:
            user = one(c, 'SELECT id,role,password_hash,active FROM dbo.users WHERE email=:e', e=email)
            valid = verify_password(password, user['password_hash']) if user else bool(hash_password(password)) and False
            if not valid:
                fail(401, '帳號或密碼不正確')
            identity = {'id': user['id'], 'role': user['role']}
            if not submit:
                request = one(c, 'SELECT id,state FROM dbo.deletion_requests WHERE user_id=:u', u=user['id'])
                return {'id': request['id'] if request else None, 'state': request['state'] if request else 'not_requested', 'account_disabled': not bool(user['active']), 'erasure_completed': bool(request and request['state'] == 'completed')}
        return self.request_deletion(identity, password)

    def favorite(self, user, key, vendor_id, enabled):
        require(user,'consumer','vendor')
        if vendor_id == user['id']:
            fail(403, '不能收藏自己的店家取得獎勵')
        def action(c):
            if not one(c,"SELECT u.id FROM dbo.users u WITH(UPDLOCK,HOLDLOCK) JOIN dbo.stores s ON s.owner_id=u.id WHERE u.id=:id AND u.role IN ('consumer','vendor') AND u.active=1",id=vendor_id):
                fail(404,'找不到店家')
            exists=one(c,'SELECT vendor_id FROM dbo.favorites WHERE user_id=:u AND vendor_id=:v',u=user['id'],v=vendor_id)
            if enabled and not exists:
                execute(c,'INSERT INTO dbo.favorites(user_id,vendor_id) VALUES(:u,:v)',u=user['id'],v=vendor_id)
                award(c,user['id'],'favorite',user['id']+':'+vendor_id)
            elif not enabled:execute(c,'DELETE FROM dbo.favorites WHERE user_id=:u AND vendor_id=:v',u=user['id'],v=vendor_id)
            return {'vendor_id':vendor_id,'enabled':enabled}
        return self.mutate(user,'favorite',key,{'vendor_id':vendor_id,'enabled':enabled},action)

    def notifications(self,user):
        with self.transaction() as c:
            return [dict(r) for r in rows(c,'SELECT TOP (50) id,kind,body,created_at,read_at FROM dbo.notifications WHERE user_id=:u AND expires_at>SYSUTCDATETIME() ORDER BY created_at DESC,id',u=user['id'])]

    def mark_notification_read(self,user,notification_id):
        with self.transaction() as c:
            result=one(c,'EXEC dbo.mark_notification_read @user_id=:u,@notification_id=:id',u=user['id'],id=notification_id)
            if result['outcome']!='read':fail(404,'找不到通知')
            return {'read':True}

    def stores(self,user):
        with self.transaction() as c:
            return [dict(r) for r in rows(c,"SELECT s.id,s.owner_id AS vendor_id,s.name,s.latitude,s.longitude,s.service_mode,(SELECT COUNT(*) FROM dbo.products p WHERE p.store_id=s.id AND p.active=1 AND p.pickup_deadline>SYSUTCDATETIME() AND p.available_quantity>0) AS product_count FROM dbo.stores s JOIN dbo.users u ON u.id=s.owner_id WHERE s.location_confirmed=1 AND u.role IN ('consumer','vendor') AND u.active=1 ORDER BY s.id")]

    def review(self, user, key, reservation_id, rating, body):
        require(user, 'consumer', 'vendor')
        def action(c):
            r = one(c, "SELECT r.id,s.owner_id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE r.id=:id AND r.user_id=:u AND r.state='completed'", id=reservation_id, u=user['id'])
            if not r:
                fail(404, '只有本人已完成預約可評論')
            if r['owner_id'] == user['id']:
                fail(403, '不能評論自己的商品取得獎勵')
            if one(c, 'SELECT reservation_id FROM dbo.reviews WHERE reservation_id=:id', id=reservation_id):
                fail(409, '此預約已評論')
            execute(c, 'INSERT INTO dbo.reviews(reservation_id,user_id,rating,body) VALUES(:id,:u,:rating,:body)', id=reservation_id, u=user['id'], rating=rating, body=body)
            award(c, user['id'], 'review', reservation_id)
            return {'reservation_id': reservation_id, 'rating': rating, 'body': body}
        return self.mutate(user, 'review', key, {'id': reservation_id, 'rating': rating, 'body': body}, action)

    def expire_reservations(self, limit=100, user_id=None, vendor_id=None):
        if not 1<=limit<=100:raise ValueError('Expiry batch must be 1..100')
        with self.transaction() as c:
            candidates=rows(c,"SELECT TOP (:limit) r.id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE r.state IN ('waiting','expired') AND r.expires_at<=SYSUTCDATETIME() AND (:user IS NULL OR r.user_id=:user) AND (:vendor IS NULL OR s.owner_id=:vendor) ORDER BY r.expires_at,r.id",limit=limit,user=user_id,vendor=vendor_id)
        count=0
        for item in candidates:
            with self.transaction() as c:
                result=one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=item['id'])
                if result['outcome']=='expired':count+=1
        return count
