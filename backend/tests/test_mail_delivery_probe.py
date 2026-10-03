"""No SQL/provider calls: probe admission, once-only behavior and fixed payload."""
import importlib.util
from contextlib import contextmanager
from pathlib import Path
import pytest
from fastapi import HTTPException

spec=importlib.util.spec_from_file_location('mail_delivery_probe',Path(__file__).parents[1]/'qa/mail_delivery_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

@pytest.fixture
def configured(monkeypatch):
    # Actual recipient is supplied only in server env; tests replace the approved digest.
    import hashlib
    email='approved@example.test'
    monkeypatch.setattr(probe,'_APPROVED_DIGEST',hashlib.sha256(email.encode()).hexdigest())
    for key,value in {'FOODSAVE_MAIL_PROBE_APPROVED':'true','FOODSAVE_MAIL_PROBE_TO':email,'FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED':'false','FOODSAVE_REGISTRATION_ENABLED':'false','FOODSAVE_MAIL_PROVIDER':'acs'}.items():monkeypatch.setenv(key,value)
    calls=[];buckets={}
    monkeypatch.setattr(probe,'one',lambda *args:{'name':'foodsave'})
    class Svc:
        @contextmanager
        def transaction(self):yield None
        def throttle(self,action,client,limit=10,window_seconds=900):
            calls.append(('quota',action,limit));key=(action,client);buckets[key]=buckets.get(key,0)+1
            if buckets[key]>limit:raise HTTPException(429,'quota')
    class Mail:
        def __init__(self):calls.append(('config',))
        def _send(self,email,subject,body):calls.append(('send',email,subject,body))
    monkeypatch.setattr(probe,'Service',Svc);monkeypatch.setattr(probe,'AcsAccountMail',Mail)
    return calls

@pytest.mark.parametrize('key,value',[
 ('FOODSAVE_MAIL_PROBE_APPROVED','false'),('FOODSAVE_MAIL_PROBE_TO','other@example.test'),
 ('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','true'),('FOODSAVE_REGISTRATION_ENABLED','true'),('FOODSAVE_MAIL_PROVIDER','smtp'),
])
def test_denied_before_quota_or_send(configured,monkeypatch,key,value):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):probe.run()
    assert not configured


def test_once_only_and_same_global_caps(configured):
    assert probe.run()=={'provider_accepted':True,'delivery_confirmed':False,'account_verified':False}
    assert configured[-1]==('send','approved@example.test',probe._SUBJECT,probe._BODY)
    assert len(probe._BODY.encode())<4096 and 'http' not in probe._BODY
    quotas={c[1]:c[2] for c in configured if c[0]=='quota'}
    assert quotas['auth:mail:global:hour']==10 and quotas['auth:mail:global:day']==30 and quotas['auth:mail:global:month']==1000 and quotas['auth:mail:email']==3
    with pytest.raises(HTTPException):probe.run()
    assert sum(c[0]=='send' for c in configured)==1


def test_failure_is_not_retried_and_redacted(configured,monkeypatch,capsys):
    class Mail:
        def _send(self,*args):raise RuntimeError('PRIVATE_PROVIDER_DIAGNOSTIC')
    monkeypatch.setattr(probe,'AcsAccountMail',Mail)
    assert probe.main(['--send-once'])==1
    assert 'PRIVATE_PROVIDER' not in capsys.readouterr().out
    with pytest.raises(HTTPException):probe.run()


def test_no_argument_cannot_send(configured):
    assert probe.main([])==2 and not configured


def test_other_database_blocks_all_writes(configured,monkeypatch):
    monkeypatch.setattr(probe,'one',lambda *args:{'name':'other'})
    with pytest.raises(ValueError):probe.run()
    assert configured==[('config',)]


def test_shared_quota_exhaustion_stops_transport(configured,monkeypatch):
    def exhausted(*args,**kwargs):raise HTTPException(429,'quota')
    monkeypatch.setattr(probe,'account_quota',exhausted)
    with pytest.raises(HTTPException):probe.run()
    assert not any(c[0]=='send' for c in configured)
    with pytest.raises(HTTPException):probe.run()
