"""Location service/API control-flow doubles. No SQL Server locking proof."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from foodsave.api import app, service
from foodsave.admin import AdminService
from foodsave import schemas
import foodsave.service as operations
import foodsave.admin as admin
from test_store_capabilities import MemoryDB, seed, owner, denied, CUSTOMER, LEGACY, STORE, NOW


class LocationDB(MemoryDB):
    def __init__(self):
        super().__init__()
        self.events=[]
        self.conflict=False

    def one(self,c,sql,**p):
        if 'FROM dbo.reservations r JOIN dbo.products p' in sql and "r.state IN ('waiting','expired')" in sql:
            self.events.append('pending-check')
            matches=[o for o in self.state['orders'].values() if self.state['products'][o['product_id']]['store_id']==p['s'] and o['state'] in ('waiting','expired')]
            return {'n':len(matches)} if 'COUNT(*)' in sql else (matches[0] if matches else None)
        if 'FROM dbo.stores WITH(UPDLOCK,HOLDLOCK)' in sql and 'location_revision' in sql:self.events.append('store-read')
        return super().one(c,sql,**p)

    def execute(self,c,sql,**p):
        if 'sp_getapplock' in sql:self.events.append(('lock',p['resource']))
        if 'UPDATE dbo.stores SET latitude=' in sql:
            self.events.append('move-write')
            store=self.state['stores'].get(p['id'])
            if self.conflict or not store or store['owner_id']!=p['u'] or store['location_revision']!=p['expected_revision']:return SimpleNamespace(rowcount=0)
            store.update(latitude=float(Decimal(str(p['latitude'])).quantize(Decimal('.000001'))),longitude=float(Decimal(str(p['longitude'])).quantize(Decimal('.000001'))),location_confirmed=True,location_revision=store['location_revision']+1)
            return SimpleNamespace(rowcount=1)
        return super().execute(c,sql,**p)


@pytest.fixture
def location(monkeypatch):
    db=LocationDB();seed(db)
    for module in (operations,admin):
        monkeypatch.setattr(module,'one',db.one)
        monkeypatch.setattr(module,'rows',db.rows)
        monkeypatch.setattr(module,'execute',db.execute)
    return AdminService(db),db


def point(revision=1,latitude=25.12345678,longitude=121.12345678):
    return dict(latitude=latitude,longitude=longitude,expected_revision=revision,confirm='SAVE_LOCATION')


@pytest.mark.parametrize('state,expired',[('waiting',False),('waiting',True),('expired',True),('expired',False)])
def test_pending_or_unsettled_orders_block_move_without_implicit_settlement(location,state,expired):
    svc,db=location;db.state['orders']['order'].update(state=state,expires_at=NOW+timedelta(minutes=-1 if expired else 5))
    before=deepcopy(db.state)
    denied(409,lambda:svc.save_store_location(owner(svc),'move','s',point()))
    assert db.state==before
    assert db.events==[('lock','foodsave:store-mode:s'),'store-read','pending-check']
    assert not any('EXEC dbo.expire_reservation' in s for s in db.statements)


@pytest.mark.parametrize('state',['completed','cancelled'])
def test_settled_orders_keep_snapshot_when_store_moves(location,state):
    svc,db=location;db.state['orders']['order']['state']=state
    before=deepcopy(db.state['orders'])
    r=svc.save_store_location(owner(svc),'move','s',point())
    assert r['location_revision']==2 and r['location_confirmed'] is True
    assert (r['latitude'],r['longitude'])==(25.123457,121.123457)
    assert db.state['orders']==before
    assert db.events==[('lock','foodsave:store-mode:s'),'store-read','pending-check','move-write']


def test_new_store_starts_draft_and_no_preview_read_publishes_it(location):
    svc,db=location
    created=svc.create_own_store(CUSTOMER,'open',STORE)
    identity=created['id']
    assert not created['location_confirmed'] and created['location_revision']==1
    row=svc.store_location(owner(svc,'customer'),identity)
    assert not row['location_confirmed'] and row['can_move']
    assert not db.state['stores'][identity]['location_confirmed']
    result=svc.save_store_location(owner(svc,'customer'),'confirm-gps',identity,point())
    assert result['location_confirmed'] and result['location_revision']==2


def test_no_confirm_and_cross_store_and_stale_revision_never_write(location):
    svc,db=location;db.state['orders'].clear();before=deepcopy(db.state)
    denied(422,lambda:svc.save_store_location(owner(svc),'no-confirm','s',{'latitude':0,'longitude':0,'expected_revision':1}))
    denied(404,lambda:svc.save_store_location(LEGACY,'cross-store','s',point()))
    denied(404,lambda:svc.store_location(LEGACY,'s'))
    denied(409,lambda:svc.save_store_location(owner(svc),'stale','s',point(2)))
    assert db.state==before and 'move-write' not in db.events


def test_location_original_retry_is_noop_and_payload_change_conflicts(location):
    svc,db=location;db.state['orders'].clear();user=owner(svc)
    first=svc.save_store_location(user,'move','s',point())
    assert svc.save_store_location(user,'move','s',point())==first
    assert db.events.count('move-write')==1
    denied(409,lambda:svc.save_store_location(user,'move','s',point(latitude=26)))
    denied(409,lambda:svc.save_store_location(user,'new-key','s',point()))
    assert db.state['stores']['s']['location_revision']==2


def test_cached_move_rechecks_owner_and_does_not_revert_new_location(location):
    svc,db=location;db.state['orders'].clear();user=owner(svc)
    first=svc.save_store_location(user,'first','s',point())
    svc.save_store_location(user,'second','s',point(2,latitude=26))
    assert svc.save_store_location(user,'first','s',point())==first
    assert db.state['stores']['s']['latitude']==26
    db.state['stores']['s']['owner_id']='legacy'  # legacy/admin reassignment scenario
    denied(404,lambda:svc.save_store_location(user,'first','s',point()))


def test_compare_and_swap_or_audit_failure_rolls_back_and_never_caches(location,monkeypatch):
    svc,db=location;db.state['orders'].clear();before=deepcopy(db.state)
    db.conflict=True
    denied(409,lambda:svc.save_store_location(owner(svc),'conflict','s',point()))
    assert db.state==before
    db.conflict=False
    monkeypatch.setattr(admin,'audit',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('audit failed')))
    with pytest.raises(RuntimeError):svc.save_store_location(owner(svc),'failure','s',point())
    assert db.state==before


def test_reserve_then_move_is_blocked_and_snapshot_is_original(location):
    svc,db=location;db.state['orders'].clear()
    reservation=svc.reserve(CUSTOMER,'reserve','p',1)
    assert reservation['snapshot']['latitude']==25 and reservation['snapshot']['longitude']==121
    assert reservation['snapshot']['location_revision']==1
    denied(409,lambda:svc.save_store_location(owner(svc),'move','s',point()))
    assert db.events.count(('lock','foodsave:store-mode:s'))==2
    assert db.state['stores']['s']['location_revision']==1


def test_move_then_reserve_uses_persisted_new_location_and_revision(location):
    svc,db=location;db.state['orders'].clear()
    moved=svc.save_store_location(owner(svc),'move','s',point())
    reservation=svc.reserve(CUSTOMER,'reserve','p',1)
    assert reservation['snapshot']['latitude']==moved['latitude']
    assert reservation['snapshot']['longitude']==moved['longitude']
    assert reservation['snapshot']['location_revision']==2
    assert db.events.count(('lock','foodsave:store-mode:s'))==2


def test_unpublished_location_cannot_be_reserved_even_if_mode_tampered(location):
    svc,db=location;db.state['orders'].clear();db.state['stores']['s']['location_confirmed']=False
    before=deepcopy(db.state)
    denied(409,lambda:svc.reserve(CUSTOMER,'reserve','p',1))
    assert db.state==before


@pytest.mark.parametrize('changes',[{'latitude':91},{'longitude':181},{'latitude':float('nan')},{'longitude':float('inf')},{'expected_revision':True},{'expected_revision':0},{'confirm':'AUTO'},{'owner_id':'victim'},{'location_revision':99}])
def test_location_payload_validation(changes):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):schemas.StoreLocation(**{**point(),**changes})


def test_location_api_requires_session_key_and_explicit_confirmation(location):
    svc,db=location;db.state['orders'].clear();app.dependency_overrides[service]=lambda:svc
    try:
        with TestClient(app) as client:
            headers={'Authorization':'Bearer merchant-session','Idempotency-Key':'location-intent-0001'}
            assert client.put('/vendor/stores/s/location',json=point()).status_code==401
            assert client.put('/vendor/stores/s/location',headers={'Authorization':'Bearer merchant-session'},json=point()).status_code==422
            assert client.put('/vendor/stores/s/location',headers=headers,json={**point(),'owner_id':'victim'}).status_code==422
            assert client.get('/vendor/stores/s/location',headers=headers).json()['location_revision']==1
            r=client.put('/vendor/stores/s/location',headers=headers,json=point())
            assert r.status_code==200 and r.json()['location_revision']==2
    finally:app.dependency_overrides.clear()


def test_location_migration_preserves_existing_public_points_and_defaults_new_drafts():
    from pathlib import Path
    sql=(Path(__file__).resolve().parents[1]/'migrations/014_store_location.sql').read_text()
    body='\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
    assert 'DEFAULT 1 WITH VALUES' in body
    assert body.index('df_stores_location_confirmed_existing DEFAULT 1') < body.index('df_stores_location_confirmed DEFAULT 0')
    assert all(s not in body.upper() for s in ('UPDATE DBO.USERS','DELETE ','GRANT ','REVOKE ','SET LATITUDE','SET OWNER_ID'))


def test_persisted_decimal_coordinates_have_numeric_idempotent_response(location,monkeypatch):
    svc,db=location;db.state['orders'].clear();original=db.one
    def query(c,sql,**p):
        row=original(c,sql,**p)
        if sql.startswith('SELECT id,latitude,longitude'):
            return {**row,'latitude':Decimal(str(row['latitude'])),'longitude':Decimal(str(row['longitude']))}
        return row
    monkeypatch.setattr(admin,'one',query)
    result=svc.save_store_location(owner(svc),'decimal-move','s',point())
    assert isinstance(result['latitude'],float) and isinstance(result['longitude'],float)
    assert result==svc.save_store_location(owner(svc),'decimal-move','s',point())


def test_readiness_requires_location_schema_marker(location,monkeypatch):
    import foodsave.api as api
    svc,db=location;app.dependency_overrides[service]=lambda:svc
    try:
        def missing(c,sql,**p):
            assert p['version']=='014_store_location.sql'
            return None
        monkeypatch.setattr(api,'one',missing)
        with TestClient(app) as client:
            assert client.get('/health/ready').status_code==503
            monkeypatch.setattr(api,'one',lambda *a,**kw:{'version':'014_store_location.sql'})
            assert client.get('/health/ready').status_code==200
    finally:app.dependency_overrides.clear()
