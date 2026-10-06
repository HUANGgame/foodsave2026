"""Old-baseline rebuild: stateful service/API doubles, NOT real SQL/race tests."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from foodsave.admin import AdminService
from foodsave.api import app, service
from foodsave.security import digest
from foodsave.service import dump
import foodsave.service as operations
import foodsave.admin as admin

NOW = datetime(2026, 10, 6)
CUSTOMER = {'id': 'customer', 'email': 'customer@example.test', 'role': 'consumer'}
MERCHANT = {'id': 'merchant', 'email': 'merchant@example.test', 'role': 'consumer'}
LEGACY = {'id': 'legacy', 'email': 'legacy@example.test', 'role': 'vendor'}
ADMIN = {'id': 'admin', 'email': 'admin@example.test', 'role': 'admin'}
STORE = {'name': 'Test store', 'latitude': 25.0, 'longitude': 121.0}


class MemoryDB:
    """Recognized query behavior only; no SQL parsing or locking simulation."""
    def __init__(self):
        self.state = dict(users={u['id']: dict(u) for u in (CUSTOMER, MERCHANT, LEGACY, ADMIN)},
                          sessions={digest(u['id']+'-session'):u['id'] for u in (CUSTOMER, MERCHANT, LEGACY, ADMIN)},
                          stores={}, products={}, orders={}, results={}, awards={}, reviews={}, terminals={}, schema=True)
        self.statements = []

    @contextmanager
    def begin(self):
        before = deepcopy(self.state)
        try:
            yield self
        except Exception:
            self.state = before
            raise

    def one(self, c, sql, **p):
        self.statements.append(sql)
        d = self.state
        if 'FROM dbo.sessions' in sql:
            identity=d['sessions'].get(p['h'])
            if identity is None:return None
            return {**d['users'][identity], 'is_vendor': any(s['owner_id']==identity for s in d['stores'].values())}
        if 'FROM dbo.users WITH' in sql:
            u=d['users'].get(p.get('u',p.get('id')))
            if u and "role='vendor'" in sql and u['role']!='vendor':return None
            return u
        if 'schema_migrations' in sql:return {'version':'013_store_capabilities.sql'} if d['schema'] else None
        if 'FROM dbo.request_results' in sql:
            key=(p['u'],p.get('op','pickup-preview'),p.get('k',p.get('key')))
            result=d['results'].get(key)
            return {**result,'now':NOW} if result else None
        if 'FROM dbo.reservation_terminals' in sql:return d['terminals'].get(p['id'])
        if 'FROM dbo.stores' in sql and 'WHERE owner_id=:u' in sql:
            return next((s for s in d['stores'].values() if s['owner_id']==p['u']),None)
        if 'FROM dbo.stores' in sql and 'WHERE id=:id' in sql:
            s=d['stores'].get(p['id'])
            return s if s and ('u' not in p or s['owner_id']==p['u']) else None
        if 'SELECT TOP (1) id FROM dbo.reservations' in sql:
            return next((o for o in d['orders'].values() if o['user_id']==p['u'] and o['product_id']==p['p'] and o['state']=='waiting' and o['expires_at']>NOW),None)
        if 'SELECT r.user_id,s.owner_id' in sql:
            o=d['orders'].get(p['id'])
            return {'user_id':o['user_id'],'owner_id':d['stores'][d['products'][o['product_id']]['store_id']]['owner_id']} if o else None
        if 'SELECT r.id,s.owner_id' in sql:
            o=d['orders'].get(p['id'])
            if not o or o['user_id']!=p['u'] or o['state']!='completed':return None
            return {'id':o['id'],'owner_id':d['stores'][d['products'][o['product_id']]['store_id']]['owner_id']}
        if 'FROM dbo.reviews' in sql:return d['reviews'].get(p['id'])
        if 'SELECT r.product_id,p.store_id' in sql:
            o=d['orders'].get(p['id'])
            return {'product_id':o['product_id'],'store_id':d['products'][o['product_id']]['store_id']} if o else None
        if 'SELECT p.id,s.owner_id' in sql:
            product=d['products'][p['p']]
            return {'id':product['id'],'owner_id':d['stores'][product['store_id']]['owner_id']}
        if 'FROM dbo.products' in sql:
            return d['products'].get(p.get('p',p.get('id')))
        if 'FROM dbo.reservations WITH' in sql:
            o=d['orders'].get(p['id']);return {**o,'now':NOW} if o else None
        if 'FROM dbo.exp_rules' in sql:return {'amount':1}
        if 'FROM dbo.exp_events' in sql:return d['awards'].get(p['key'])
        if sql=='SELECT SYSUTCDATETIME() AS now':return {'now':NOW}
        raise AssertionError(sql)

    def rows(self,c,sql,**p):
        self.statements.append(sql)
        if 'SELECT TOP (25)' in sql:return []
        if 's.owner_id=:vendor' in sql:
            matches=[]
            for o in self.state['orders'].values():
                store=self.state['stores'][self.state['products'][o['product_id']]['store_id']]
                qr=any(json.loads(r['response']).get('pickup_qr')==p.get('credential') and json.loads(r['response']).get('id')==o['id'] for (u,op,k),r in self.state['results'].items() if op=='reserve') if 'credential' in p else False
                if store['owner_id']==p['vendor'] and (qr or o['pickup_code_hash']==p.get('hash')):matches.append({**o,'now':NOW})
            return matches
        raise AssertionError(sql)

    def execute(self,c,sql,**p):
        self.statements.append(sql)
        d=self.state
        if 'sp_getapplock' in sql or 'INSERT INTO dbo.audit_logs' in sql:return
        if 'INSERT INTO dbo.request_results' in sql:
            d['results'][p['u'],p['op'],p['k']]={'fingerprint':p['f'],'response':p['r']};return
        if 'INSERT INTO dbo.stores' in sql:
            d['stores'][p['id']]={**p,'service_mode':'information'};return
        if 'available_quantity=available_quantity-:q' in sql:
            product=d['products'][p['p']]
            if product['available_quantity']<p['q']:return SimpleNamespace(rowcount=0)
            product['available_quantity']-=p['q'];return SimpleNamespace(rowcount=1)
        if 'available_quantity=available_quantity+:q' in sql:
            d['products'][p['p']]['available_quantity']+=p['q'];return
        if 'INSERT INTO dbo.reservations' in sql:
            d['orders'][p['id']]=dict(id=p['id'],user_id=p['u'],product_id=p['p'],state='waiting',quantity=p['q'],snapshot=p['snapshot'],pickup_code_hash=p['code'],expires_at=p['expiry']);return
        if 'UPDATE dbo.reservations SET state=' in sql:
            d['orders'][p['id']]['state']=p['state'];return
        if 'INSERT INTO dbo.reviews' in sql:
            d['reviews'][p['id']]=p;return
        if 'INSERT INTO dbo.exp_events' in sql:
            assert p['key'] not in d['awards']
            d['awards'][p['key']]=p;return
        # In particular, onboarding must never change users or sessions.
        raise AssertionError(sql)


@pytest.fixture
def system(monkeypatch):
    db=MemoryDB()
    for module in (operations,admin):
        monkeypatch.setattr(module,'one',db.one)
        monkeypatch.setattr(module,'rows',db.rows)
        monkeypatch.setattr(module,'execute',db.execute)
    return AdminService(db), db


def owner(svc,identity='merchant'):
    return svc.authenticate(identity+'-session')


def seed(db,store_owner='merchant',customer='customer'):
    db.state['stores']['s']={'id':'s','owner_id':store_owner,'service_mode':'reservation',**STORE}
    db.state['products']['p']=dict(id='p',store_id='s',name='Food',original_price_minor=100,sale_price_minor=50,photo_url='https://example.invalid/food',pickup_deadline=NOW+timedelta(hours=1),available_quantity=10)
    db.state['orders']['order']=dict(id='order',user_id=customer,product_id='p',state='waiting',quantity=1,snapshot=dump({'name':'Food','sale_price_minor':50}),pickup_code_hash=digest('ABCDEF123456'),expires_at=NOW+timedelta(minutes=5))


def denied(status,action):
    with pytest.raises(HTTPException) as e:action()
    assert e.value.status_code==status


def cache(db,identity,op,key,payload,result):
    db.state['results'][identity,op,key]={'fingerprint':digest(dump(payload)),'response':dump(result)}


def test_onboard_preserves_id_role_admin_and_all_existing_sessions(system):
    svc,db=system;before=deepcopy((db.state['users'],db.state['sessions']))
    first=svc.create_own_store(CUSTOMER,'open-store',STORE)
    assert first['owner_id']=='customer' and first['service_mode']=='information'
    assert owner(svc,'customer')['is_vendor']
    assert (db.state['users'],db.state['sessions'])==before
    assert svc.create_own_store(owner(svc,'customer'),'open-store',STORE)==first
    denied(409,lambda:svc.create_own_store(owner(svc,'customer'),'second-store',STORE))
    denied(409,lambda:svc.create_own_store(owner(svc,'customer'),'open-store',{**STORE,'name':'Changed'}))
    assert len(db.state['stores'])==1
    assert owner(svc,'admin')['role']=='admin'


def test_schema_gate_and_actor_injection_cannot_partially_onboard(system):
    svc,db=system;db.state['schema']=False
    denied(503,lambda:svc.create_own_store(CUSTOMER,'open',STORE))
    denied(422,lambda:svc.create_own_store(CUSTOMER,'open',{**STORE,'owner_id':'victim'}))
    denied(403,lambda:svc.create_own_store(ADMIN,'open',STORE))
    assert not db.state['stores'] and not db.state['results']


def test_admin_creation_and_self_creation_share_one_store_rule(system):
    svc,db=system
    svc.create_store(ADMIN,'admin-store',{**STORE,'owner_id':'legacy'})
    denied(409,lambda:svc.create_own_store(LEGACY,'own-store',STORE))
    denied(409,lambda:svc.create_store(ADMIN,'another-store',{**STORE,'owner_id':'legacy'}))
    assert len(db.state['stores'])==1


def test_onboarding_api_rejects_role_and_owner_injection_and_uses_session(system):
    svc,db=system;app.dependency_overrides[service]=lambda:svc
    try:
        with TestClient(app) as client:
            headers={'Authorization':'Bearer customer-session','Idempotency-Key':'onboard-intent-001'}
            assert client.post('/vendor/store',json=STORE).status_code==401
            for field in ('owner_id','role','is_vendor'):
                assert client.post('/vendor/store',headers=headers,json={**STORE,field:'admin'}).status_code==422
            r=client.post('/vendor/store',headers=headers,json=STORE)
            assert r.status_code==201 and r.json()['owner_id']=='customer'
            assert client.post('/vendor/store',headers=headers,json=STORE).json()==r.json()
    finally:app.dependency_overrides.clear()


@pytest.mark.parametrize('role',['consumer','vendor'])
def test_merchant_can_buy_elsewhere_and_cancel_without_role_switch(system,role):
    svc,db=system;seed(db);db.state['orders'].clear()
    db.state['users']['customer']['role']=role
    db.state['stores']['own']={'id':'own','owner_id':'customer',**STORE}
    user=owner(svc,'customer')
    r=svc.reserve(user,'buy-elsewhere','p',2)
    assert svc.reserve(user,'buy-elsewhere','p',2)==r
    assert db.state['products']['p']['available_quantity']==8
    svc.transition(user,'cancel-elsewhere',r['id'],'cancelled')
    svc.transition(user,'cancel-elsewhere',r['id'],'cancelled')
    assert db.state['products']['p']['available_quantity']==10 and not db.state['awards']


@pytest.mark.parametrize('mode',['new','cached'])
def test_self_reservation_blocked_including_legacy_success_cache(system,mode):
    svc,db=system;seed(db,customer='merchant');user=owner(svc)
    if mode=='new':db.state['orders'].clear()
    else:cache(db,'merchant','reserve','self',{'product_id':'p','quantity':1},{'id':'order','pickup_code':'ABCDEF123456'})
    denied(403,lambda:svc.reserve(user,'self','p',1))
    assert db.state['products']['p']['available_quantity']==10 and not db.state['awards']


@pytest.mark.parametrize('credential',['ABCDEF123456','FS1.'+'A'*43])
def test_self_preview_denied_for_manual_code_and_qr(system,credential):
    svc,db=system;seed(db,customer='merchant')
    cache(db,'merchant','reserve','old',{}, {'id':'order','pickup_qr':'FS1.'+'A'*43})
    denied(403,lambda:svc.preview_pickup(owner(svc),'preview',credential))
    assert ('merchant','pickup-preview','preview') not in db.state['results']


@pytest.mark.parametrize('operation',['transition','pickup-preview','pickup-confirm'])
@pytest.mark.parametrize('kind',['self','other-store'])
def test_cached_pickup_success_is_not_an_authorization_grant(system,operation,kind):
    svc,db=system;seed(db,customer='merchant' if kind=='self' else 'customer')
    user=owner(svc) if kind=='self' else LEGACY
    token='B'*43
    if operation=='transition':
        payload={'id':'order','target':'completed','code_hash':digest('ABCDEF123456')}
        action=lambda:svc.transition(user,'old-success','order','completed','ABCDEF123456')
    elif operation=='pickup-preview':
        payload={'credential_hash':digest('ABCDEF123456')}
        action=lambda:svc.preview_pickup(user,'old-success','ABCDEF123456')
    else:
        payload={'review_key':'review-key','token_hash':digest(token)}
        action=lambda:svc.confirm_pickup(user,'old-success','review-key',token)
    cache(db,user['id'],operation,'old-success',payload,{'id':'order','state':'completed'})
    denied(403 if kind=='self' else 404,action)
    assert not db.state['awards'] and db.state['orders']['order']['state']=='waiting'


@pytest.mark.parametrize('kind',['self','other-store'])
@pytest.mark.parametrize('path',['direct','confirm'])
def test_live_redemption_rechecks_owner_and_self_even_after_legacy_preview(system,kind,path):
    svc,db=system;seed(db,customer='merchant' if kind=='self' else 'customer')
    user=owner(svc) if kind=='self' else LEGACY
    token='B'*43
    cache(db,user['id'],'pickup-preview','review-key',{}, {'id':'order','review_token':token,'review_expires_at':NOW+timedelta(minutes=1)})
    action=(lambda:svc.transition(user,'redeem','order','completed','ABCDEF123456')) if path=='direct' else (lambda:svc.confirm_pickup(user,'redeem','review-key',token))
    denied(403 if kind=='self' else 404,action)
    assert not db.state['awards'] and db.state['orders']['order']['state']=='waiting'


def test_confirmation_belongs_to_authenticated_merchant_and_awards_once(system):
    svc,db=system;seed(db);user=owner(svc)
    preview=svc.preview_pickup(user,'review-key','ABCDEF123456')
    denied(404,lambda:svc.confirm_pickup(LEGACY,'steal','review-key',preview['review_token']))
    denied(404,lambda:svc.confirm_pickup(user,'bad-token','review-key','X'*43))
    first=svc.confirm_pickup(user,'redeem','review-key',preview['review_token'])
    assert first==svc.confirm_pickup(user,'redeem','review-key',preview['review_token'])
    denied(409,lambda:svc.confirm_pickup(user,'new-key','review-key',preview['review_token']))
    denied(409,lambda:svc.transition(user,'alternate-path','order','completed','ABCDEF123456'))
    assert len(db.state['awards'])==1
    assert next(iter(db.state['awards'].values()))['u']=='customer'


def test_cross_store_preview_returns_no_order(system):
    svc,db=system;seed(db)
    denied(404,lambda:svc.preview_pickup(LEGACY,'review-key','ABCDEF123456'))
    assert not db.state['results']


@pytest.mark.parametrize('actor,merchant,status', [('merchant',True,None),('customer',False,None),('customer',True,404),('merchant',False,404),('admin',None,404)])
def test_terminal_authorization_is_by_operation_not_legacy_role(system,actor,merchant,status):
    svc,db=system
    db.state['terminals']['order']=dict(user_id='customer',vendor_id='merchant',reason='expired')
    action=lambda:svc.terminal_result(db,db.state['users'][actor],'order',merchant=merchant)
    if status:denied(status,action)
    else:assert action()['state']=='expired'


def test_favorite_self_reward_rejected_before_cache_or_database(system):
    svc,db=system
    denied(403,lambda:svc.favorite(CUSTOMER,'cached-favorite','customer',True))
    assert not db.statements


@pytest.mark.parametrize('cached',[False,True])
def test_legacy_self_order_cannot_award_review_or_replay_it(system,cached):
    svc,db=system;seed(db,customer='merchant');db.state['orders']['order']['state']='completed'
    if cached:cache(db,'merchant','review','old-review',{'id':'order','rating':5,'body':'Food'}, {'reservation_id':'order','rating':5,'body':'Food'})
    denied(403,lambda:svc.review(owner(svc),'old-review','order',5,'Food'))
    assert not db.state['reviews'] and not db.state['awards']


def test_buyer_review_remains_idempotent(system):
    svc,db=system;seed(db);db.state['orders']['order']['state']='completed'
    first=svc.review(CUSTOMER,'review','order',5,'Food')
    assert svc.review(CUSTOMER,'review','order',5,'Food')==first
    denied(409,lambda:svc.review(CUSTOMER,'another-review','order',5,'Food'))
    assert len(db.state['reviews'])==1 and len(db.state['awards'])==1


def test_consumer_owner_cannot_write_other_stores_product(system):
    svc,db=system;seed(db)
    db.state['stores']['other']={'id':'other','owner_id':'legacy',**STORE}
    before=deepcopy(db.state)
    denied(404,lambda:svc.save_product(owner(svc),'cross-store',{'store_id':'other'}))
    assert db.state==before


def test_failed_onboarding_rolls_back_store_and_does_not_cache(monkeypatch,system):
    svc,db=system
    def fail_audit(*a,**kw):raise RuntimeError('simulated audit failure')
    monkeypatch.setattr(admin,'audit',fail_audit)
    before=deepcopy(db.state)
    with pytest.raises(RuntimeError):svc.create_own_store(CUSTOMER,'store',STORE)
    assert db.state==before


def test_legacy_vendor_can_consume_draw_grant_without_new_identity(monkeypatch,system):
    svc,db=system
    # Failure comes from the absence of a grant, not role denial.
    original=db.one
    def query(c,sql,**p):
        if 'FROM dbo.spin_grants' in sql:return None
        return original(c,sql,**p)
    monkeypatch.setattr(operations,'one',query)
    denied(409,lambda:svc.draw(LEGACY,'draw-key'))
    assert not db.state['awards']


def test_new_sql_only_changes_two_procedure_role_predicates():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'migrations'
    sql=(root/'013_store_capabilities.sql').read_text()
    for name in ('009_close_vendor_business.sql','010_report_stock_loss.sql'):
        expected=(root/name).read_text().replace('CREATE PROCEDURE','ALTER PROCEDURE',1).replace("u.role='vendor'", "u.role IN ('consumer','vendor')")
        assert "EXEC(N'"+expected.replace("'","''")+"');" in sql
    assert sql.count("EXEC(N'ALTER PROCEDURE")==2
    assert 'ux_stores_single_owner' in sql
    assert all(term not in sql.upper() for term in ('GRANT ', 'REVOKE ', 'UPDATE DBO.USERS', 'DELETE FROM DBO.SESSIONS', 'SET OWNER_ID'))
