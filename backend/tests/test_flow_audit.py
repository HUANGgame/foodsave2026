"""Focused safety regression doubles; no real users, SQL or permanent deletion."""
from contextlib import contextmanager
import secrets
from datetime import datetime,timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from foodsave.service import Service
from foodsave.admin import AdminService
from foodsave.security import hash_password
import foodsave.service as operations
import foodsave.admin as admin

class DB:
    @contextmanager
    def begin(self):yield None


def test_vendor_deletion_disables_before_atomic_business_procedure(monkeypatch):
    password=secrets.token_urlsafe(24);calls=[]
    def one(c,sql,**args):
        if 'FROM dbo.users' in sql:return {'password_hash':hash_password(password),'active':True}
        if 'FROM dbo.deletion_requests' in sql:return None
        if 'close_vendor_business' in sql:
            assert any('UPDATE dbo.users SET active=0' in x for x,p in calls)
            assert any('submit_deletion_request' in x for x,p in calls)
            calls.append((sql,args));return {'outcome':'closed'}
        raise AssertionError(sql)
    monkeypatch.setattr(operations,'one',one);monkeypatch.setattr(operations,'rows',lambda *a,**k:[])
    monkeypatch.setattr(operations,'execute',lambda c,sql,**params:calls.append((sql,params)))
    result=Service(DB()).request_deletion({'id':'vendor','role':'vendor'},password)
    assert result['account_disabled'] and not result['erasure_completed']
    assert sum('close_vendor_business' in sql for sql,p in calls)==1
    assert not any('available_quantity+' in sql for sql,p in calls)


def test_product_deadline_cannot_cut_existing_waiting_order(monkeypatch):
    monkeypatch.setattr(admin,'lock_store_mode',lambda *a:None)
    now=datetime(2026,10,3);result=iter([{'id':'s'},{'now':now},{'id':'p','store_id':'s','revision':1},{'expiry':now+timedelta(hours=2)}])
    monkeypatch.setattr(admin,'one',lambda *a,**k:next(result))
    monkeypatch.setattr(admin,'execute',lambda *a,**k:pytest.fail('deadline must not change'))
    svc=AdminService();svc.mutate=lambda u,o,k,p,action:action(None)
    with pytest.raises(HTTPException) as error:svc.save_product({'id':'v','role':'vendor'},'key',{'store_id':'s','pickup_deadline':now+timedelta(hours=1),'revision':1},'p')
    assert error.value.status_code==409


def test_bounded_lazy_expiry_uses_idempotent_procedure(monkeypatch):
    calls=[];outcomes=iter(['expired','absent'])
    monkeypatch.setattr(operations,'rows',lambda *a,**k:[{'id':'order'}])
    def proc(c,sql,**args):
        assert sql=='EXEC dbo.expire_reservation @reservation_id=:id'
        calls.append(args);return {'outcome':next(outcomes)}
    monkeypatch.setattr(operations,'one',proc)
    monkeypatch.setattr(operations,'execute',lambda *a,**k:pytest.fail('no direct expiry writes'))
    svc=Service(DB())
    assert svc.expire_reservations(limit=25)==1 and svc.expire_reservations(limit=25)==0
    assert calls==[{'id':'order'},{'id':'order'}]
