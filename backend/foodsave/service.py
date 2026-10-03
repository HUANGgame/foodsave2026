import hmac
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

    def throttle(self, action, client):
        # Separate committed transaction: failed authentication still consumes quota.
        bucket = digest(action + ':' + client)
        with self.transaction() as c:
            rate = one(c, 'SELECT attempts,window_start FROM dbo.rate_limits WITH (UPDLOCK,HOLDLOCK) WHERE bucket=:b', b=bucket)
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            if not rate:
                execute(c, 'INSERT INTO dbo.rate_limits(bucket,attempts,window_start) VALUES(:b,1,:now)', b=bucket, now=now)
            elif now - rate['window_start'] >= timedelta(minutes=15):
                execute(c, 'UPDATE dbo.rate_limits SET attempts=1,window_start=:now WHERE bucket=:b', b=bucket, now=now)
            elif rate['attempts'] >= 10:
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
            user = one(c, 'SELECT * FROM dbo.users WHERE email=:e AND active=1', e=email)
            # Same expensive hash work for nonexistent users.
            valid = verify_password(password, user['password_hash']) if user else bool(hash_password(password)) and False
            if not valid:
                fail(401, '帳號或密碼不正確')
            token = secrets.token_urlsafe(32)
            execute(c, 'INSERT INTO dbo.sessions(token_hash,user_id,expires_at) VALUES(:h,:u,DATEADD(hour,12,SYSUTCDATETIME()))', h=digest(token), u=user['id'])
            return {'access_token': token, 'token_type': 'bearer', 'expires_in': 43200}

    def authenticate(self, token):
        with self.transaction() as c:
            user = one(c, 'SELECT u.id,u.email,u.role FROM dbo.sessions s JOIN dbo.users u ON u.id=s.user_id WHERE s.token_hash=:h AND s.expires_at>SYSUTCDATETIME() AND u.active=1', h=digest(token))
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
                return json.loads(old['response'])
            result = action(c)
            execute(c, 'INSERT INTO dbo.request_results(user_id,operation,request_key,fingerprint,response) VALUES(:u,:op,:k,:f,:r)',
                    u=user['id'], op=operation, k=key, f=fingerprint, r=dump(result))
            return json.loads(dump(result))

    def reserve(self, user, key, product_id, quantity):
        require(user, 'consumer')
        def action(c):
            p = one(c, 'SELECT * FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:p AND active=1 AND pickup_deadline>SYSUTCDATETIME()', p=product_id)
            if not p:
                fail(404, '商品不存在或已截止')
            result = execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity-:q,revision=revision+1 WHERE id=:p AND available_quantity>=:q', p=product_id, q=quantity)
            if result.rowcount != 1:
                fail(409, '商品庫存不足')
            identity, code = uid(), secrets.token_hex(6).upper()
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            expiry = min(now + timedelta(minutes=30), p['pickup_deadline'])
            snapshot = {k: p[k] for k in ('name','store_id','original_price_minor','sale_price_minor','photo_url')}
            execute(c, "INSERT INTO dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,'waiting',:q,:snapshot,:code,:expiry)",
                    id=identity, u=user['id'], p=product_id, q=quantity, snapshot=dump(snapshot), code=digest(code), expiry=expiry)
            return {'id': identity, 'state': 'waiting', 'quantity': quantity, 'pickup_code': code, 'expires_at': expiry, 'snapshot': snapshot}
        return self.mutate(user, 'reserve', key, {'product_id': product_id, 'quantity': quantity}, action)

    def transition(self, user, key, reservation_id, target, code=''):
        require(user, 'consumer' if target == 'cancelled' else 'vendor')
        def action(c):
            # Resolve immutable product id, then lock product before reservation.
            lookup = one(c, 'SELECT product_id FROM dbo.reservations WHERE id=:id', id=reservation_id)
            if not lookup:
                fail(404, '找不到預約')
            product = one(c, 'SELECT p.id,s.owner_id FROM dbo.products p WITH(UPDLOCK,HOLDLOCK) JOIN dbo.stores s ON s.id=p.store_id WHERE p.id=:p', p=lookup['product_id'])
            r = one(c, 'SELECT *,SYSUTCDATETIME() AS now FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE id=:id', id=reservation_id)
            if (target == 'cancelled' and r['user_id'] != user['id']) or (target == 'completed' and product['owner_id'] != user['id']):
                fail(404, '找不到預約')
            if target == 'completed' and not hmac.compare_digest(r['pickup_code_hash'], digest(code)):
                fail(400, '取貨碼不正確')
            if r['state'] != 'waiting':
                fail(409, '預約已處理')
            state = 'expired' if r['expires_at'] <= r['now'] else target
            execute(c, "UPDATE dbo.reservations SET state=:state,completed_at=CASE WHEN :state='completed' THEN SYSUTCDATETIME() ELSE NULL END WHERE id=:id", state=state, id=reservation_id)
            if state in ('cancelled','expired'):
                execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity+:q,revision=revision+1 WHERE id=:p', q=r['quantity'], p=r['product_id'])
            else:
                award(c, r['user_id'], 'pickup', reservation_id)
            return {'id': reservation_id, 'state': state}
        return self.mutate(user, 'transition', key, {'id': reservation_id, 'target': target, 'code_hash': digest(code)}, action)

    def draw(self, user, key):
        require(user, 'consumer')
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
        with self.transaction() as c:
            return [dict(r) for r in rows(c, 'SELECT p.id,p.store_id,s.name AS store_name,s.latitude,s.longitude,p.name,p.photo_url,p.original_price_minor,p.sale_price_minor,p.available_quantity,p.pickup_deadline,p.revision FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id WHERE p.active=1 AND p.pickup_deadline>SYSUTCDATETIME() ORDER BY p.id OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY')]

    def account(self, user):
        with self.transaction() as c:
            return {**user, 'exp': one(c, 'SELECT COALESCE(SUM(amount),0) AS total FROM dbo.exp_events WHERE user_id=:u', u=user['id'])['total'],
                    'spins': one(c, 'SELECT COALESCE(SUM(remaining),0) AS total FROM dbo.spin_grants WHERE user_id=:u AND expires_at>SYSUTCDATETIME()', u=user['id'])['total']}

    def history(self, user, resource):
        queries = {
            'reservations': "SELECT r.id,r.product_id,r.state,r.quantity,r.snapshot,r.expires_at,r.completed_at,(SELECT TOP (1) JSON_VALUE(q.response,'$.pickup_code') FROM dbo.request_results q WHERE q.user_id=r.user_id AND q.operation='reserve' AND JSON_VALUE(q.response,'$.id')=r.id) AS pickup_code FROM dbo.reservations r WHERE r.user_id=:u ORDER BY r.created_at DESC",
            'draws': 'SELECT d.id,d.prize_snapshot,d.created_at,c.code AS coupon_code FROM dbo.draws d LEFT JOIN dbo.coupons c ON c.draw_id=d.id WHERE d.user_id=:u ORDER BY d.created_at DESC',
        }
        with self.transaction() as c:
            return [dict(r) for r in rows(c, queries[resource] + ' OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY', u=user['id'])]

    def public_prizes(self):
        with self.transaction() as c:
            return [dict(r) for r in rows(c, 'SELECT id,name,kind,terms,expires_at,discount_percent FROM dbo.prizes WHERE enabled=1 AND remaining>0 AND expires_at>SYSUTCDATETIME() ORDER BY id')]

    def favorites(self, user):
        with self.transaction() as c:
            return [r['store_id'] for r in rows(c, 'SELECT store_id FROM dbo.favorites WHERE user_id=:u', u=user['id'])]

    def store_reviews(self, store_id):
        with self.transaction() as c:
            summary = one(c, 'SELECT COUNT(*) AS count,AVG(CAST(v.rating AS decimal(4,2))) AS average FROM dbo.reviews v JOIN dbo.reservations r ON r.id=v.reservation_id JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s', s=store_id)
            items = rows(c, 'SELECT v.rating,v.body,v.created_at FROM dbo.reviews v JOIN dbo.reservations r ON r.id=v.reservation_id JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s ORDER BY v.created_at DESC OFFSET 0 ROWS FETCH NEXT 50 ROWS ONLY', s=store_id)
            return {**dict(summary), 'items': [dict(r) for r in items]}

    def request_deletion(self, user, password):
        with self.transaction() as c:
            current = one(c, 'SELECT password_hash,active FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id=:u', u=user['id'])
            if not current or not verify_password(password, current['password_hash']):
                fail(401, '請確認密碼')
            existing = one(c, 'SELECT id,state FROM dbo.deletion_requests WHERE user_id=:u', u=user['id'])
            if existing:
                return {'id': existing['id'], 'state': existing['state'], 'account_disabled': not bool(current['active']), 'erasure_completed': existing['state'] == 'completed'}
            if not current['active']:
                fail(403, '帳號目前無法提出此申請，請聯絡營運者')
            # Same lock order as reservation transitions. Recheck after locking:
            # a vendor may have completed an order while this request waited.
            pending = rows(c, "SELECT id,product_id FROM dbo.reservations WHERE user_id=:u AND state='waiting' ORDER BY product_id,id", u=user['id'])
            for item in pending:
                one(c, 'SELECT id FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:p', p=item['product_id'])
                order = one(c, "SELECT quantity FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE id=:id AND user_id=:u AND state='waiting'", id=item['id'], u=user['id'])
                if order:
                    execute(c, "UPDATE dbo.reservations SET state='cancelled' WHERE id=:id", id=item['id'])
                    execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity+:q,revision=revision+1 WHERE id=:p', q=order['quantity'], p=item['product_id'])
            # Disable access now; retain an auditable request until the approved
            # retention/erasure job is implemented, never claim completed erasure.
            identity = uid()
            execute(c, 'EXEC dbo.submit_deletion_request @request_id=:id,@user_id=:u', id=identity, u=user['id'])
            execute(c, 'UPDATE dbo.users SET active=0 WHERE id=:u', u=user['id'])
            execute(c, 'DELETE FROM dbo.sessions WHERE user_id=:u', u=user['id'])
            if user['role'] == 'vendor':
                execute(c, 'UPDATE p SET active=0,revision=revision+1 FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u', u=user['id'])
            audit(c, user['id'], 'account.deletion_requested', identity)
            return {'id': identity, 'state': 'requested', 'account_disabled': True, 'erasure_completed': False}

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

    def favorite(self, user, key, store_id, enabled):
        require(user, 'consumer')
        def action(c):
            if not one(c, 'SELECT id FROM dbo.stores WHERE id=:id', id=store_id):
                fail(404, '找不到店家')
            exists = one(c, 'SELECT store_id FROM dbo.favorites WHERE user_id=:u AND store_id=:s', u=user['id'], s=store_id)
            if enabled and not exists:
                execute(c, 'INSERT INTO dbo.favorites(user_id,store_id) VALUES(:u,:s)', u=user['id'], s=store_id)
                award(c, user['id'], 'favorite', user['id'] + ':' + store_id)
            elif not enabled:
                execute(c, 'DELETE FROM dbo.favorites WHERE user_id=:u AND store_id=:s', u=user['id'], s=store_id)
            return {'store_id': store_id, 'enabled': enabled}
        return self.mutate(user, 'favorite', key, {'store_id': store_id, 'enabled': enabled}, action)

    def review(self, user, key, reservation_id, rating, body):
        require(user, 'consumer')
        def action(c):
            r = one(c, "SELECT id FROM dbo.reservations WHERE id=:id AND user_id=:u AND state='completed'", id=reservation_id, u=user['id'])
            if not r:
                fail(404, '只有本人已完成預約可評論')
            if one(c, 'SELECT reservation_id FROM dbo.reviews WHERE reservation_id=:id', id=reservation_id):
                fail(409, '此預約已評論')
            execute(c, 'INSERT INTO dbo.reviews(reservation_id,user_id,rating,body) VALUES(:id,:u,:rating,:body)', id=reservation_id, u=user['id'], rating=rating, body=body)
            award(c, user['id'], 'review', reservation_id)
            return {'reservation_id': reservation_id, 'rating': rating, 'body': body}
        return self.mutate(user, 'review', key, {'id': reservation_id, 'rating': rating, 'body': body}, action)
