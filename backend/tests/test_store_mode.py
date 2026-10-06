"""Service control-flow tests, not SQL migration or concurrency execution."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from foodsave.service import Service
from foodsave.admin import AdminService
import foodsave.service as service
import foodsave.admin as admin

USER={'id':'consumer','role':'consumer'}
VENDOR={'id':'vendor','role':'vendor'}


def direct(cls):
    svc=cls();svc.mutate=lambda user,operation,key,payload,action:action(None)
    return svc


def test_information_mode_rejects_tampered_reserve_before_stock_write(monkeypatch):
    result=iter([None,{'store_id':'s'},{'id':'p','store_id':'s'},{'owner_id':'vendor','service_mode':'information'}])
    monkeypatch.setattr(service,'lock_store_mode',lambda c,s:None)
    monkeypatch.setattr(service,'one',lambda *a,**k:next(result))
    monkeypatch.setattr(service,'execute',lambda *a,**k:pytest.fail('information must not change stock'))
    with pytest.raises(HTTPException) as error:direct(Service).reserve(USER,'key','p',1)
    assert error.value.status_code==409


def test_reservation_mode_still_creates_one_opaque_pickup(monkeypatch):
    from datetime import timedelta
    now=datetime(2026,10,3)
    product=dict(id='p',store_id='s',name='QA',original_price_minor=100,sale_price_minor=50,photo_url='https://images.example.invalid/qa',pickup_deadline=now+timedelta(hours=1))
    result=iter([None,{'store_id':'s'},product,{'owner_id':'vendor','service_mode':'reservation','latitude':0,'longitude':0},{'now':now}]);writes=[]
    monkeypatch.setattr(service,'lock_store_mode',lambda c,s:None)
    monkeypatch.setattr(service,'rows',lambda *a,**k:[])
    monkeypatch.setattr(service,'one',lambda *a,**k:next(result))
    monkeypatch.setattr(service,'execute',lambda c,sql,**params:writes.append((sql,params)) or SimpleNamespace(rowcount=1))
    response=direct(Service).reserve(USER,'key','p',1)
    assert len(response['pickup_qr'])==47 and response['quantity']==1
    assert len(writes)==2 and writes[0][1]['q']==1 and 'INSERT INTO dbo.reservations' in writes[1][0]


@pytest.mark.parametrize('old,new,pending,allowed', [('reservation','information',1,False),('reservation','information',0,True),('information','reservation',1,True),('information','reservation',0,True)])
def test_store_mode_hard_gate_no_pending_transition(monkeypatch, old, new, pending, allowed):
    locks=[];writes=[];result=iter([{'id':'s','service_mode':old},{'n':pending}])
    monkeypatch.setattr(admin,'lock_store_mode',lambda c,s:locks.append(s))
    monkeypatch.setattr(admin,'one',lambda *a,**k:next(result))
    monkeypatch.setattr(admin,'execute',lambda c,sql,**params:writes.append((sql,params)))
    if allowed:
        response=direct(AdminService).set_store_mode(VENDOR,'key','s',new)
        assert response['service_mode']==new and response['history_preserved']
        assert len(writes)==1 and writes[0][1]=={'mode':new,'id':'s'}
    else:
        with pytest.raises(HTTPException) as error:direct(AdminService).set_store_mode(VENDOR,'key','s',new)
        assert error.value.status_code==409 and not writes
    assert locks==['s']


def test_other_store_mode_change_denied(monkeypatch):
    monkeypatch.setattr(admin,'lock_store_mode',lambda c,s:None)
    monkeypatch.setattr(admin,'one',lambda *a,**k:None)
    monkeypatch.setattr(admin,'execute',lambda *a,**k:pytest.fail('must not update'))
    with pytest.raises(HTTPException) as error:direct(AdminService).set_store_mode(VENDOR,'key','other','information')
    assert error.value.status_code==404


def test_migration_preserves_old_stores_and_new_stores_default_information():
    root=Path(__file__).resolve().parents[2]
    sql=(root/'backend/migrations/006_store_service_mode.sql').read_text()
    assert sql.index("SET service_mode=''reservation''") < sql.index("DEFAULT ''information''")
    grant=(root/'infra/sqlserver/runtime-grant-006.review.sql').read_text()
    assert grant.count(' GRANT ')==1
    assert 'GRANT UPDATE (service_mode) ON OBJECT::dbo.stores' in grant
    assert 'REPLACE_WITH_APPROVED_APP_ID' in grant
