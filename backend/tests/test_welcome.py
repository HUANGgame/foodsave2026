"""Transactional fake tests; not SQL Server concurrency evidence."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
import pytest
from fastapi import HTTPException
from foodsave import service, welcome, demo_prizes
from foodsave.admin import AdminService

class DB:
    def __init__(self):
        self.lock=RLock(); self.grants={}; self.sessions={}; self.fail_session=False
    @contextmanager
    def begin(self):
        with self.lock:
            before=deepcopy((self.grants,self.sessions))
            try: yield self
            except Exception:
                self.grants,self.sessions=before
                raise

@pytest.fixture
def setup(monkeypatch):
    db=DB()
    monkeypatch.setenv('FOODSAVE_WELCOME_SPIN_ENABLED','true')
    monkeypatch.setattr(service,'verify_password',lambda password,hashed:password=='valid')
    def one(c,sql,**p):
        if 'FROM dbo.users' in sql:return {'id':p['e'],'email':p['e'],'role':'consumer','password_hash':'fixture'}
        if 'FROM dbo.spin_grants' in sql:return c.grants.get(p['key'])
        raise AssertionError(sql)
    def execute(c,sql,**p):
        if 'INSERT INTO dbo.spin_grants' in sql:
            c.grants.setdefault(p['key'],{'remaining':1,'user_id':p['u']});return
        if 'INSERT INTO dbo.sessions' in sql:
            if c.fail_session:raise RuntimeError('synthetic session failure')
            c.sessions[p['h']]=p['u'];return
        if 'DELETE FROM dbo.sessions' in sql:c.sessions.pop(p['h'],None);return
        raise AssertionError(sql)
    monkeypatch.setattr(service,'one',one);monkeypatch.setattr(service,'execute',execute)
    monkeypatch.setattr(welcome,'one',one);monkeypatch.setattr(welcome,'execute',execute)
    return service.Service(db),db

def test_first_repeat_logout_new_client_and_consumed_not_reset(setup):
    svc,db=setup
    token=svc.login('a','valid')['access_token']
    assert welcome.status(db,'a')=={'welcome_spin_awarded':True,'welcome_spin_available':1}
    svc.logout(token);service.Service(db).login('a','valid')
    assert len(db.grants)==1
    db.grants[welcome.PREFIX+'a']['remaining']=0
    svc.login('a','valid')
    assert welcome.status(db,'a')['welcome_spin_available']==0
    svc.login('b','valid');assert len(db.grants)==2

def test_bad_password_and_disabled_flag_never_grant(setup,monkeypatch):
    svc,db=setup
    with pytest.raises(HTTPException) as error:svc.login('a','bad')
    assert error.value.status_code==401 and not db.grants and not db.sessions
    monkeypatch.delenv('FOODSAVE_WELCOME_SPIN_ENABLED')
    svc.login('a','valid');assert not db.grants and len(db.sessions)==1

def test_concurrent_logins_serialized_fake_transaction(setup):
    svc,db=setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:svc.login('a','valid'),range(16)))
    assert len(db.grants)==1 and len(db.sessions)==16
    assert len({r['access_token'] for r in results})==16
    assert db.grants[welcome.PREFIX+'a']['remaining']==1

def test_session_failure_rolls_back_grant_then_retry_succeeds(setup):
    svc,db=setup;db.fail_session=True
    with pytest.raises(RuntimeError):svc.login('a','valid')
    assert not db.grants and not db.sessions
    db.fail_session=False;svc.login('a','valid')
    assert len(db.grants)==len(db.sessions)==1

def test_demo_draw_does_not_consume_welcome_or_create_session(setup,monkeypatch,tmp_path):
    svc,db=setup;svc.login('a','valid');before=deepcopy((db.grants,db.sessions))
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZES_ENABLED','true')
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZE_STORE',str(tmp_path/'demo-prizes.json'))
    result=demo_prizes.draw(1)
    assert result['consumes_real_spin'] is False and result['redeemable'] is False
    assert 'coupon_code' not in result and (db.grants,db.sessions)==before

@pytest.mark.parametrize('prefix',['welcome:','WELCOME:',' Welcome:'])
def test_admin_cannot_forge_welcome_source(prefix):
    with pytest.raises(HTTPException) as error:
        AdminService().grant_spins({'role':'admin'},'test',{'source_key':prefix+'first-login:v1:a'})
    assert error.value.status_code==422
