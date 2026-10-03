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


def test_vendor_deletion_cancels_customer_waiting_once_without_exp(monkeypatch):
    password=secrets.token_urlsafe(24);calls=[];locks=[]
    monkeypatch.setattr(operations,'lock_store_mode',lambda c,s:locks.append(s))
    monkeypatch.setattr(operations,'award',lambda *a,**k:pytest.fail('closure cannot award EXP'))
    def rows(c,sql,**args):
        if 'SELECT id FROM dbo.stores' in sql:return [{'id':'store'}]
        assert 's.owner_id=:u' in sql and "state='waiting'" in sql
        return [{'id':'waiting','product_id':'p','reason':'vendor_closed'},{'id':'already-finished','product_id':'p','reason':'vendor_closed'}]
    def one(c,sql,**args):
        if 'FROM dbo.users' in sql:return {'password_hash':hash_password(password),'active':True}
        if 'FROM dbo.deletion_requests' in sql:return None
        if 'SELECT id FROM dbo.products' in sql:return {'id':'p'}
        if 'FROM dbo.reservations' in sql:return {'quantity':1,'user_id':'customer'} if args['id']=='waiting' else None
        raise AssertionError(sql)
    monkeypatch.setattr(operations,'rows',rows);monkeypatch.setattr(operations,'one',one)
    monkeypatch.setattr(operations,'execute',lambda c,sql,**params:calls.append((sql,params)))
    result=Service(DB()).request_deletion({'id':'vendor','role':'vendor'},password)
    assert result['account_disabled'] and not result['erasure_completed'] and locks==['store']
    assert sum('available_quantity=available_quantity+:q' in sql for sql,p in calls)==1
    reasons=[p for sql,p in calls if "'vendor-closed'" in sql]
    assert len(reasons)==1 and reasons[0]['u']=='customer' and 'vendor_closed' in reasons[0]['response']
    assert any('active=0,revision=revision+1' in sql for sql,p in calls)


def test_product_deadline_cannot_cut_existing_waiting_order(monkeypatch):
    now=datetime(2026,10,3);result=iter([{'id':'s'},{'now':now},{'id':'p','store_id':'s','revision':1},{'expiry':now+timedelta(hours=2)}])
    monkeypatch.setattr(admin,'one',lambda *a,**k:next(result))
    monkeypatch.setattr(admin,'execute',lambda *a,**k:pytest.fail('deadline must not change'))
    svc=AdminService();svc.mutate=lambda u,o,k,p,action:action(None)
    with pytest.raises(HTTPException) as error:svc.save_product({'id':'v','role':'vendor'},'key',{'store_id':'s','pickup_deadline':now+timedelta(hours=1),'revision':1},'p')
    assert error.value.status_code==409


def test_bounded_lazy_expiry_rechecks_state_and_returns_stock_once(monkeypatch):
    calls=[];locks=[];states=iter([{'quantity':1},None])
    monkeypatch.setattr(operations,'lock_store_mode',lambda c,s:locks.append(s))
    monkeypatch.setattr(operations,'rows',lambda *a,**k:[{'id':'order','product_id':'p','store_id':'s'}])
    monkeypatch.setattr(operations,'one',lambda c,sql,**k: {'id':'p'} if 'FROM dbo.products' in sql else next(states))
    monkeypatch.setattr(operations,'execute',lambda c,sql,**k:calls.append((sql,k)))
    svc=Service(DB())
    assert svc.expire_reservations(limit=25)==1
    assert svc.expire_reservations(limit=25)==0
    assert locks==['s','s'] and sum('available_quantity=available_quantity+:q' in sql for sql,p in calls)==1
