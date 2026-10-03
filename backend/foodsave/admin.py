from .db import engine, execute, one, rows
from .service import Service, require, fail, uid, audit, lock_store_mode


class AdminService(Service):
    def configure_ranking(self, user, key, rules):
        require(user, 'admin')
        def action(c):
            execute(c, "DECLARE @r int; EXEC @r=sp_getapplock @Resource='foodsave:weekly', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000; IF @r<0 THROW 51000,'Ranking lock unavailable',1;")
            execute(c, 'DELETE FROM dbo.ranking_rules')
            for rule in rules:
                execute(c, 'INSERT INTO dbo.ranking_rules(start_rank,end_rank,spins) VALUES(:start_rank,:end_rank,:spins)', **rule)
            audit(c, user['id'], 'ranking.configure', 'ranking_rules')
            return {'rules': rules}
        return self.mutate(user, 'ranking.configure', key, rules, action)

    def create_store(self, user, key, data):
        require(user, 'admin')
        def action(c):
            if not one(c, "SELECT id FROM dbo.users WHERE id=:id AND role='vendor' AND active=1", id=data['owner_id']):
                fail(400, '請指定有效商家帳號')
            identity = uid()
            execute(c, 'INSERT INTO dbo.stores(id,owner_id,name,latitude,longitude) VALUES(:id,:owner_id,:name,:latitude,:longitude)', id=identity, **data)
            audit(c, user['id'], 'store.create', identity)
            return {'id': identity, **data, 'service_mode': 'information'}
        return self.mutate(user, 'store.create', key, data, action)

    def set_store_mode(self, user, key, store_id, mode):
        require(user, 'vendor')
        if mode not in ('information', 'reservation'):
            fail(422, '店家模式不正確')
        def action(c):
            lock_store_mode(c, store_id)
            store=one(c, 'SELECT id,service_mode FROM dbo.stores WITH(UPDLOCK,HOLDLOCK) WHERE id=:id AND owner_id=:u', id=store_id, u=user['id'])
            if not store:
                fail(404, '找不到此商家店舖')
            pending=one(c, "SELECT COUNT(*) AS n FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s AND r.state='waiting'", s=store_id)['n']
            if mode=='information' and store['service_mode']=='reservation' and pending>0:
                fail(409, '還有未完成預約，不能切換；請先完成、取消或確認逾期')
            execute(c, 'UPDATE dbo.stores SET service_mode=:mode WHERE id=:id', mode=mode,id=store_id)
            return {'id':store_id,'service_mode':mode,'pending_orders':pending,'history_preserved':True}
        return self.mutate(user, 'store-mode', key, {'id':store_id,'mode':mode}, action)

    def expire_store_orders(self, user, key, store_id):
        require(user, 'vendor')
        def action(c):
            lock_store_mode(c, store_id)
            if not one(c, 'SELECT id FROM dbo.stores WHERE id=:s AND owner_id=:u', s=store_id,u=user['id']):
                fail(404, '找不到此商家店舖')
            candidates=rows(c, "SELECT TOP (100) r.id,r.product_id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=:s AND r.state='waiting' AND r.expires_at<=SYSUTCDATETIME() ORDER BY r.expires_at,r.id", s=store_id)
            count=0
            for item in candidates:
                one(c, 'SELECT id FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:id', id=item['product_id'])
                expired=one(c, "SELECT quantity FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE id=:id AND state='waiting' AND expires_at<=SYSUTCDATETIME()", id=item['id'])
                if expired:
                    execute(c, "UPDATE dbo.reservations SET state='expired' WHERE id=:id", id=item['id'])
                    execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity+:q,revision=revision+1 WHERE id=:id', q=expired['quantity'],id=item['product_id'])
                    count+=1
            return {'expired_count':count, 'batch_limit':100}
        return self.mutate(user, 'store-expire', key, {'store_id':store_id}, action)

    def save_product(self, user, key, data, product_id=None):
        require(user, 'vendor')
        def action(c):
            store = one(c, 'SELECT id FROM dbo.stores WHERE id=:id AND owner_id=:u', id=data['store_id'], u=user['id'])
            if not store:
                fail(404, '找不到此商家店舖')
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            if data['pickup_deadline'] <= now:
                fail(422, '領取期限必須在未來')
            identity = product_id or uid()
            if product_id:
                existing = one(c, 'SELECT id,store_id,revision FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:id', id=identity)
                if not existing or existing['store_id'] != data['store_id']:
                    fail(404, '找不到商品')
                latest=one(c, "SELECT MAX(expires_at) AS expiry FROM dbo.reservations WHERE product_id=:p AND state='waiting'", p=identity)['expiry']
                if latest and data['pickup_deadline'] < latest:
                    fail(409, '還有未完成預約，領取截止不能早於既有預約期限')
                if existing['revision'] != data['revision']:
                    fail(409, '商品已更新，請重新載入再編輯')
                execute(c, 'UPDATE dbo.products SET name=:name,photo_url=:photo_url,original_price_minor=:original_price_minor,sale_price_minor=:sale_price_minor,available_quantity=:available_quantity,pickup_deadline=:pickup_deadline,active=:active,revision=revision+1 WHERE id=:id', id=identity, **data)
            else:
                execute(c, 'INSERT INTO dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active) VALUES(:id,:store_id,:name,:photo_url,:original_price_minor,:sale_price_minor,:available_quantity,:pickup_deadline,:active)', id=identity, **data)
            audit(c, user['id'], 'product.save', identity)
            return {'id': identity, 'revision': (data['revision'] + 1) if product_id else 1}
        return self.mutate(user, 'product.save', key, {'id': product_id, **data}, action)

    def adjust_stock(self, user, key, product_id, delta):
        require(user, 'vendor')
        def action(c):
            product = one(c, 'SELECT p.id FROM dbo.products p WITH(UPDLOCK,HOLDLOCK) JOIN dbo.stores s ON s.id=p.store_id WHERE p.id=:p AND s.owner_id=:u', p=product_id, u=user['id'])
            if not product:
                fail(404, '找不到此商品')
            result = execute(c, 'UPDATE dbo.products SET available_quantity=available_quantity+:delta,revision=revision+1 WHERE id=:p AND available_quantity+:delta BETWEEN 0 AND 1000000', p=product_id, delta=delta)
            if result.rowcount != 1:
                fail(409, '庫存不能小於0，請重新載入')
            return dict(one(c, 'SELECT id,available_quantity,revision FROM dbo.products WHERE id=:p', p=product_id))
        return self.mutate(user, 'stock-adjust', key, {'id': product_id, 'delta': delta}, action)

    def create_prize(self, user, key, data):
        require(user, 'admin')
        def action(c):
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            if data['expires_at'] <= now:
                fail(422, '獎品期限必須在未來')
            eligible = rows(c, 'SELECT id FROM dbo.prizes WITH(UPDLOCK,HOLDLOCK) WHERE enabled=1 AND expires_at>SYSUTCDATETIME()')
            if data['enabled'] and len(eligible) >= 6:
                fail(409, '目前最多同時開放六個獎項')
            identity = uid()
            execute(c, 'INSERT INTO dbo.prizes(id,name,kind,weight,remaining,enabled,expires_at,terms,discount_percent) VALUES(:id,:name,:kind,:weight,:remaining,:enabled,:expires_at,:terms,:discount_percent)', id=identity, **data)
            audit(c, user['id'], 'prize.create', identity)
            return {'id': identity}
        return self.mutate(user, 'prize.create', key, data, action)

    def grant_spins(self, user, key, data):
        require(user, 'admin')
        def action(c):
            if not one(c, "SELECT id FROM dbo.users WHERE id=:id AND active=1 AND role='consumer'", id=data['user_id']):
                fail(404, '找不到用戶')
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            if data['expires_at'] <= now:
                fail(422, '次數期限必須在未來')
            old = one(c, 'SELECT id FROM dbo.spin_grants WITH(UPDLOCK,HOLDLOCK) WHERE source_key=:k', k=data['source_key'])
            if old:
                fail(409, '此來源已發放，不能重發')
            identity = uid()
            execute(c, 'INSERT INTO dbo.spin_grants(id,user_id,source_key,remaining,expires_at) VALUES(:id,:user_id,:source_key,:remaining,:expires_at)', id=identity, **data)
            audit(c, user['id'], 'spin.grant', identity)
            return {'id': identity}
        return self.mutate(user, 'spin.grant', key, data, action)

    def configure_exp(self, user, key, event, amount, enabled):
        require(user, 'admin')
        def action(c):
            execute(c, 'UPDATE dbo.exp_rules SET amount=:a,enabled=:e WHERE event=:event', a=amount, e=enabled, event=event)
            audit(c, user['id'], 'exp.configure', event)
            return {'event': event, 'amount': amount, 'enabled': enabled}
        return self.mutate(user, 'exp.configure', key, {'event': event, 'amount': amount, 'enabled': enabled}, action)

    def vendor_orders(self, user):
        require(user, 'vendor')
        with self.transaction() as c:
            return [dict(r) for r in rows(c, 'SELECT r.id,r.product_id,r.state,r.quantity,r.snapshot,r.expires_at FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u ORDER BY r.created_at DESC OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY', u=user['id'])]

    def vendor_catalog(self, user):
        require(user, 'vendor')
        with self.transaction() as c:
            stores = rows(c, "SELECT s.id,s.name,s.service_mode,(SELECT COUNT(*) FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id WHERE p.store_id=s.id AND r.state='waiting') AS pending_orders FROM dbo.stores s WHERE s.owner_id=:u", u=user['id'])
            products = rows(c, 'SELECT p.* FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u ORDER BY p.id OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY', u=user['id'])
            return {'stores': [dict(r) for r in stores], 'products': [dict(r) for r in products]}

    def view_database(self, user, table, page):
        require(user, 'admin')
        # Fixed allowlist: no SQL, credentials, session hashes, pickup/coupon codes,
        # private review bodies, email addresses or arbitrary columns from client.
        allowed = {
            'users': 'id,role,active,created_at',
            'stores': 'id,owner_id,name,latitude,longitude',
            'products': 'id,store_id,name,available_quantity,revision',
            'reservations': 'id,user_id,product_id,state,quantity,expires_at',
            'draws': 'id,user_id,prize_id,created_at',
            'prizes': 'id,name,kind,weight,remaining,enabled,expires_at',
            'spin_grants': 'id,user_id,source_key,remaining,expires_at',
            'audit_logs': 'id,actor_id,action,target_id,created_at',
        }
        if table not in allowed:
            fail(404, '不允許查看此資料表')
        try:
            with engine('viewer').begin() as c:
                result = rows(c, f'SELECT {allowed[table]} FROM dbo.{table} ORDER BY id OFFSET :offset ROWS FETCH NEXT 50 ROWS ONLY', offset=(page-1)*50)
        except RuntimeError:
            fail(503, '唯讀檢視連線尚未配置')
        with self.transaction() as c:
            audit(c, user['id'], 'db.view', table)
        return {'page': page, 'page_size': 50, 'rows': [dict(r) for r in result]}
