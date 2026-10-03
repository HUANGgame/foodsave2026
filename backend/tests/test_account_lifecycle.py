"""In-memory transaction/API safety contracts. NOT SQL Server or real SMTP evidence."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import base64
import hashlib
import secrets
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import foodsave.accounts as accounts
import foodsave.api as api_module
import foodsave.service as service_module
from foodsave.account_mail import MailUnavailable,SmtpAccountMail
from foodsave.schemas import EmailRequest,FinishAccount,NewPassword
from foodsave.security import hash_password,verify_password,digest

EMAIL='owner@example.test'
PASSWORD=secrets.token_urlsafe(24)
OTHER=secrets.token_urlsafe(24)


class DB:
    def __init__(self):
        self.now=datetime(2026,10,3);self.state={'tickets':{},'users':{},'sessions':{}};self.sql=[]
    @contextmanager
    def begin(self):
        before=deepcopy(self.state)
        try:yield self
        except Exception:self.state=before;raise


class Mail:
    def __init__(self):self.sent=[]
    def send_code(self,email,purpose,code):self.sent.append((email,purpose,code))


@pytest.fixture
def lifecycle(monkeypatch):
    db=DB();mail=Mail()
    def one(c,sql,**p):
        c.sql.append(sql)
        if 'sp_getapplock' in sql:return {'result':0}
        if 'FROM dbo.account_challenges' in sql:
            row=c.state['tickets'].get(p['token'])
            return row if row and row['email_key']==p['e'] and row['purpose']==p['purpose'] and row['expires_at']>c.now else None
        if 'FROM dbo.sessions s JOIN dbo.users' in sql:
            session=c.state['sessions'].get(p['h']);user=c.state['users'].get(session['user_id']) if session else None
            return user if user and user['active'] else None
        if 'FROM dbo.users' in sql:
            return next((u for u in c.state['users'].values() if u.get('email')==p.get('email',p.get('e')) or u['id']==p.get('u')),None)
        if 'FROM dbo.sessions' in sql:
            row=c.state['sessions'].get(p['token']);return row if row and row['user_id']==p['u'] else None
        if 'EXEC dbo.apply_account_password' in sql:
            user=c.state['users'].get(p['u']);changed=user and user['active'] and user['password_hash']==p['old']
            if changed:
                user['password_hash']=p['new'];user['email_verified_at']=c.now if '@verify_email=1' in sql else user.get('email_verified_at')
                c.state['sessions']={k:v for k,v in c.state['sessions'].items() if v['user_id']!=p['u']}
            return {'changed':int(bool(changed))}
        raise AssertionError(sql)
    def execute(c,sql,**p):
        c.sql.append(sql)
        if 'INSERT INTO dbo.sessions' in sql:
            c.state['sessions'][p['h']]={'user_id':p['u']};return
        if 'DELETE FROM dbo.sessions WHERE token_hash' in sql:
            c.state['sessions'].pop(p['h'],None);return
        if 'DELETE TOP (100)' in sql:
            c.state['tickets']={k:v for k,v in c.state['tickets'].items() if v['expires_at']>=c.now-timedelta(days=1)};return
        if sql.startswith('DELETE FROM dbo.account_challenges'):
            c.state['tickets']={k:v for k,v in c.state['tickets'].items() if v['email_key']!=p['e'] or ('purpose' in p and v['purpose']!=p['purpose'])};return
        if 'INSERT dbo.account_challenges' in sql:
            c.state['tickets'][p['token']]={'token_hash':p['token'],'email_key':p['e'],'purpose':p['purpose'],'expires_at':c.now+timedelta(minutes=15)};return
        if 'INSERT dbo.users' in sql:
            c.state['users'][p['id']]={'id':p['id'],'email':p['email'],'password_hash':p['password'],'role':'consumer','active':True,'email_verified_at':c.now};return
        raise AssertionError(sql)
    monkeypatch.setattr(accounts,'one',one);monkeypatch.setattr(accounts,'execute',execute)
    monkeypatch.setattr(service_module,'one',one);monkeypatch.setattr(service_module,'execute',execute)
    return accounts.AccountService(db),db,mail


def code(svc,mail,email=EMAIL,purpose='register'):
    svc.request_code(email,purpose,mail);return mail.sent[-1][2]


def enroll(svc,db,mail):
    token=code(svc,mail);svc.finish(EMAIL,'register',token,PASSWORD);return next(iter(db.state['users'].values()))


def test_verified_enrollment_only_hashes_persist_and_existing_account_not_overwritten(lifecycle):
    svc,db,mail=lifecycle;token=code(svc,mail)
    assert db.state['users']=={} and token not in repr(db.state) and EMAIL not in repr(db.state)
    svc.finish(EMAIL,'register',token,PASSWORD);user=next(iter(db.state['users'].values()))
    assert user['role']=='consumer' and user['email_verified_at']==db.now
    assert user['password_hash'].startswith('scrypt-v2$') and PASSWORD not in repr(db.state)
    assert verify_password(PASSWORD,user['password_hash'])
    with pytest.raises(HTTPException):svc.finish(EMAIL,'register',token,PASSWORD)
    new=code(svc,mail);before=deepcopy(db.state)
    with pytest.raises(HTTPException):svc.finish(EMAIL,'register',new,OTHER)
    assert db.state==before and verify_password(PASSWORD,user['password_hash'])


@pytest.mark.parametrize('kind',['expired','wrong_email','wrong_purpose','superseded','unknown'])
def test_invalid_codes_cannot_create_or_change_accounts(lifecycle,kind):
    svc,db,mail=lifecycle;token=code(svc,mail);email=EMAIL;purpose='register'
    if kind=='expired':db.now+=timedelta(minutes=15)
    elif kind=='wrong_email':email='someone@example.test'
    elif kind=='wrong_purpose':purpose='reset'
    elif kind=='superseded':code(svc,mail)
    else:token=secrets.token_urlsafe(32)
    before=deepcopy(db.state)
    with pytest.raises(HTTPException) as error:svc.finish(email,purpose,token,OTHER)
    assert error.value.detail==accounts.INVALID and db.state==before


def test_reset_revokes_all_sessions_and_all_codes_without_automatic_login(lifecycle):
    svc,db,mail=lifecycle;user=enroll(svc,db,mail)
    db.state['sessions']={'old-1':{'user_id':user['id']},'old-2':{'user_id':user['id']},'other-user':{'user_id':'other'}}
    code(svc,mail);token=code(svc,mail,purpose='reset')
    result=svc.finish(EMAIL,'reset',token,OTHER)
    assert result['sessions_revoked'] and 'access_token' not in result
    assert db.state['sessions']=={'other-user':{'user_id':'other'}} and not db.state['tickets']
    assert verify_password(OTHER,user['password_hash']) and not verify_password(PASSWORD,user['password_hash'])
    with pytest.raises(HTTPException):svc.finish(EMAIL,'reset',token,PASSWORD)


@pytest.mark.parametrize('disabled',[True,False])
def test_unknown_or_disabled_reset_does_not_create_or_reactivate(lifecycle,disabled):
    svc,db,mail=lifecycle
    if disabled:enroll(svc,db,mail)['active']=False
    token=code(svc,mail,purpose='reset');before=deepcopy(db.state)
    with pytest.raises(HTTPException):svc.finish(EMAIL,'reset',token,OTHER)
    assert db.state==before


def test_request_response_and_work_do_not_branch_on_account_existence(lifecycle):
    svc,db,mail=lifecycle
    first=svc.request_code(EMAIL,'reset',mail);work=list(db.sql);db.sql=[]
    db.state['users']['old']={'id':'old','email':EMAIL,'active':True}
    second=svc.request_code(EMAIL,'reset',mail)
    assert first==second=={'detail':accounts.GENERIC} and work==db.sql
    assert len(mail.sent)==2 and all('FROM dbo.users' not in s for s in work)


def test_mail_failure_never_returns_success_and_delayed_mail_expires(lifecycle):
    svc,db,mail=lifecycle
    class Reject:
        def send_code(self,*args):raise MailUnavailable()
    with pytest.raises(MailUnavailable):svc.request_code(EMAIL,'register',Reject())
    token=code(svc,mail);db.now+=timedelta(hours=1)
    with pytest.raises(HTTPException):svc.finish(EMAIL,'register',token,PASSWORD)
    assert db.state['users']=={}


def test_password_change_requires_current_session_password_and_revokes_every_device(lifecycle):
    svc,db,mail=lifecycle;user=enroll(svc,db,mail);raw=secrets.token_urlsafe(32)
    db.state['sessions']={digest(raw):{'user_id':user['id']},'second':{'user_id':user['id']}}
    before=deepcopy(db.state)
    for session,current in [('revoked-session',PASSWORD),(raw,OTHER)]:
        with pytest.raises(HTTPException):svc.change_password(user,session,current,OTHER)
        assert db.state==before
    code(svc,mail,purpose='reset');svc.change_password(user,raw,PASSWORD,OTHER)
    assert not db.state['sessions'] and not db.state['tickets'] and verify_password(OTHER,db.state['users'][user['id']]['password_hash'])


def test_transaction_failure_does_not_consume_code_or_partially_reset(lifecycle,monkeypatch):
    svc,db,mail=lifecycle;enroll(svc,db,mail);token=code(svc,mail,purpose='reset');before=deepcopy(db.state)
    original=accounts.execute
    def fail_after_update(c,sql,**kwargs):
        if sql=='DELETE FROM dbo.account_challenges WHERE email_key=:e':raise RuntimeError('synthetic failure')
        return original(c,sql,**kwargs)
    monkeypatch.setattr(accounts,'execute',fail_after_update)
    with pytest.raises(RuntimeError):svc.finish(EMAIL,'reset',token,OTHER)
    assert db.state==before


def test_legacy_scrypt_remains_valid_and_new_cost_is_explicit():
    salt=secrets.token_bytes(16);key=hashlib.scrypt(PASSWORD.encode(),salt=salt,n=16384,r=8,p=1)
    legacy='scrypt$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(key).decode()
    assert verify_password(PASSWORD,legacy) and not verify_password(OTHER,legacy)
    strong=hash_password(PASSWORD);assert strong.startswith('scrypt-v2$') and verify_password(PASSWORD,strong)
    assert not verify_password(PASSWORD,'scrypt-v2$!!!!$!!!!')


@pytest.mark.parametrize('email',['a..b@example.test','a@-bad.test','a@bad..test','a\r\nBcc:b@example.test','@example.test'])
def test_email_headers_and_malformed_addresses_rejected(email):
    with pytest.raises(ValidationError):EmailRequest(email=email)


def test_new_password_policy_and_role_injection():
    for password in ['short','passwordpassword','1'*20,' '+PASSWORD]:
        with pytest.raises(ValidationError):NewPassword(password=password)
    with pytest.raises(ValidationError):FinishAccount(email=EMAIL,password=PASSWORD,code=secrets.token_urlsafe(32),role='admin')


@pytest.fixture
def http(monkeypatch,lifecycle):
    svc,db,mail=lifecycle;limits={}
    def throttle(action,client,limit=10,window_seconds=900):
        key=(action,client);limits[key]=limits.get(key,0)+1
        if limits[key]>limit:raise HTTPException(429,'嘗試次數過多')
    monkeypatch.setattr(svc,'throttle',throttle)
    monkeypatch.setattr(api_module,'mail_service',lambda:mail)
    monkeypatch.setenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','true');monkeypatch.setenv('FOODSAVE_REGISTRATION_ENABLED','true');monkeypatch.setenv('FOODSAVE_PRIVACY_POLICY_COMPLETE','true')
    api_module.app.dependency_overrides[api_module.account_service]=lambda:svc
    api_module.app.dependency_overrides[api_module.service]=lambda:svc
    with TestClient(api_module.app) as client:yield client,svc,db,mail,limits
    api_module.app.dependency_overrides.clear()


def test_http_registration_requires_valid_code_no_enumeration_or_secret_response(http):
    client,svc,db,mail,_=http
    assert client.get('/auth/options').json()['registration_enabled']
    r=client.post('/auth/register',json={'email':EMAIL});assert r.status_code==202
    raw=mail.sent[-1][2];assert raw not in r.text and not db.state['users']
    r=client.post('/auth/verify-email',json={'email':EMAIL,'password':PASSWORD,'code':raw});assert r.status_code==200
    assert PASSWORD not in r.text and raw not in r.text and 'access_token' not in r.json()
    r=client.post('/auth/verify-email',json={'email':EMAIL,'password':PASSWORD,'code':raw});assert r.status_code==400
    r=client.post('/auth/reset-password',json={'email':EMAIL,'password':PASSWORD,'code':'bad-code'});assert r.status_code==422 and PASSWORD not in r.text and 'bad-code' not in r.text
    assert r.headers['Cache-Control']=='no-store' and r.headers['Referrer-Policy']=='no-referrer'


def test_mail_quota_shared_between_register_and_reset(http):
    client,_,db,mail,_=http
    for path in ['/auth/register','/auth/forgot-password','/auth/register']:
        assert client.post(path,json={'email':EMAIL}).status_code==202
    assert client.post('/auth/forgot-password',json={'email':EMAIL}).status_code==429
    assert len(mail.sent)==3


def test_global_mail_quota_blocks_before_issue_or_send(http):
    client,_,db,mail,limits=http;limits[('auth:mail:global:day','all')]=30
    assert client.post('/auth/register',json={'email':EMAIL}).status_code==429
    assert not mail.sent and not db.state['tickets']


def test_disabled_flags_and_provider_failure_remain_closed(http,monkeypatch):
    client,_,db,mail,_=http;monkeypatch.setenv('FOODSAVE_PRIVACY_POLICY_COMPLETE','false')
    assert client.post('/auth/register',json={'email':EMAIL}).status_code==503
    monkeypatch.setenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','false')
    assert client.post('/auth/forgot-password',json={'email':EMAIL}).status_code==503
    assert not mail.sent and not db.state['tickets']
    monkeypatch.setenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','true')
    def unavailable():raise MailUnavailable()
    monkeypatch.setattr(api_module,'mail_service',unavailable)
    assert client.post('/auth/forgot-password',json={'email':EMAIL}).status_code==503
    assert not client.get('/auth/options').json()['recovery_enabled']


def test_smtp_requires_explicit_approval_tls_and_rejects_provider_failure(monkeypatch):
    import foodsave.account_mail as module
    monkeypatch.delenv('FOODSAVE_MAIL_APPROVED',raising=False)
    with pytest.raises(MailUnavailable):SmtpAccountMail()
    settings={'FOODSAVE_MAIL_APPROVED':'true','FOODSAVE_MAIL_AUTHORIZED_UNTIL':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'FOODSAVE_SMTP_HOST':'smtp.example.test','FOODSAVE_SMTP_PORT':'587','FOODSAVE_MAIL_FROM':'noreply@example.test','FOODSAVE_SMTP_USER':'test-only','FOODSAVE_SMTP_PASSWORD':secrets.token_urlsafe(24)}
    for k,v in settings.items():monkeypatch.setenv(k,v)
    calls=[]
    class SMTP:
        def __init__(self,*args,**kwargs):calls.append('connect')
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):calls.append('ehlo')
        def starttls(self,context):assert context.check_hostname;calls.append('tls')
        def login(self,*args):assert 'tls' in calls;calls.append('login')
        def send_message(self,message):calls.append('send');return {'redacted':'rejected'}
    monkeypatch.setattr(module.smtplib,'SMTP',SMTP)
    with pytest.raises(MailUnavailable):SmtpAccountMail().send_code(EMAIL,'reset',secrets.token_urlsafe(32))
    assert calls.index('tls')<calls.index('login')<calls.index('send')


def test_schema_and_grants_are_additive_candidates_without_password_update_grant():
    root=Path(__file__).parents[2]
    migration=(root/'backend/migrations/012_account_lifecycle.sql').read_text()
    assert 'email_verified_at datetime2 NULL' in migration and 'DELETE dbo.sessions WHERE user_id=@user_id' in migration
    grants=(root/'infra/sqlserver/runtime-grant-012.review.sql').read_text()
    assert 'GRANT EXECUTE ON OBJECT::dbo.apply_account_password' in grants and 'GRANT UPDATE' not in grants
    rollback=(root/'backend/rollback/012_account_lifecycle.review.sql').read_text();assert 'Account changes exist' in rollback


@pytest.mark.parametrize('status',['Running','Succeeded','Failed','Canceled',None])
def test_acs_mi_only_bounded_acceptance_not_delivery_and_provider_failure(monkeypatch,status):
    from datetime import timezone
    from foodsave.account_mail import AcsAccountMail
    import azure.communication.email
    import azure.identity
    settings={'FOODSAVE_MAIL_APPROVED':'true','FOODSAVE_ACS_EMAIL_ENDPOINT':'https://fixture.communication.azure.com','FOODSAVE_MAIL_FROM':'noreply@example.test','FOODSAVE_MAIL_AUTHORIZED_UNTIL':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    for k,v in settings.items():monkeypatch.setenv(k,v)
    calls=[]
    class Credential:
        def __init__(self,**kwargs):assert kwargs['retry_total']==0;calls.append('mi')
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Client:
        def __init__(self,endpoint,credential,**kwargs):assert isinstance(credential,Credential);assert kwargs['retry_total']==0 and not kwargs['logging_enable']
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def begin_send(self,message,**kwargs):
            assert kwargs=={'polling':False,'logging_enable':False}
            assert message['userEngagementTrackingDisabled'] and len(message['recipients']['to'])==1
            calls.append('send');return self
        def result(self):return {'status':status} if status else None
    monkeypatch.setattr(azure.identity,'ManagedIdentityCredential',Credential)
    monkeypatch.setattr(azure.communication.email,'EmailClient',Client)
    if status in ('Running','Succeeded'):AcsAccountMail().send_code(EMAIL,'reset',secrets.token_urlsafe(32))
    else:
        with pytest.raises(MailUnavailable):AcsAccountMail().send_code(EMAIL,'reset',secrets.token_urlsafe(32))
    assert calls==['mi','send']
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL',(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    with pytest.raises(MailUnavailable):AcsAccountMail()


def test_auth_login_locks_user_against_concurrent_password_reset():
    import inspect
    from foodsave.service import Service
    assert 'WITH(UPDLOCK,HOLDLOCK)' in inspect.getsource(Service.login)


def test_http_full_account_lifecycle_revokes_previous_bearer_sessions(http):
    client,svc,db,mail,limits=http
    assert client.post('/auth/register',json={'email':EMAIL}).status_code==202
    token=mail.sent[-1][2]
    assert client.post('/auth/verify-email',json={'email':EMAIL,'code':token,'password':PASSWORD}).status_code==200
    session=client.post('/auth/login',json={'email':EMAIL,'password':PASSWORD})
    assert session.status_code==200;old=session.json()['access_token']
    assert old not in repr(db.state)
    assert client.post('/auth/forgot-password',json={'email':EMAIL}).status_code==202
    token=mail.sent[-1][2]
    assert client.post('/auth/reset-password',json={'email':EMAIL,'code':token,'password':OTHER}).status_code==200
    assert client.post('/auth/logout',headers={'Authorization':'Bearer '+old}).status_code==401
    assert client.post('/auth/login',json={'email':EMAIL,'password':PASSWORD}).status_code==401
    session=client.post('/auth/login',json={'email':EMAIL,'password':OTHER});assert session.status_code==200
    newer=session.json()['access_token']
    assert client.post('/auth/change-password',headers={'Authorization':'Bearer '+newer},json={'current_password':OTHER,'password':PASSWORD}).status_code==200
    assert client.post('/auth/logout',headers={'Authorization':'Bearer '+newer}).status_code==401
    assert client.post('/auth/login',json={'email':EMAIL,'password':PASSWORD}).status_code==200


def test_legacy_login_upgrades_cost_revokes_old_sessions_without_claiming_email_verified(lifecycle,monkeypatch):
    svc,db,mail=lifecycle;salt=secrets.token_bytes(16)
    legacy='scrypt$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(hashlib.scrypt(PASSWORD.encode(),salt=salt,n=16384,r=8,p=1)).decode()
    db.state['users']['legacy']={'id':'legacy','email':EMAIL,'password_hash':legacy,'active':True,'role':'consumer','email_verified_at':None}
    db.state['sessions']['old']={'user_id':'legacy'};monkeypatch.setenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','true')
    response=svc.login(EMAIL,PASSWORD)
    assert db.state['users']['legacy']['password_hash'].startswith('scrypt-v2$')
    assert db.state['users']['legacy']['email_verified_at'] is None
    assert 'old' not in db.state['sessions'] and digest(response['access_token']) in db.state['sessions']


def test_cli_invalid_password_does_not_echo_secret(monkeypatch,capsys):
    import foodsave.cli as cli
    private='short-secret'
    monkeypatch.setattr('sys.argv',['foodsave','create-user','--email',EMAIL])
    monkeypatch.setattr(cli.getpass,'getpass',lambda prompt:private)
    class NoWrite:
        def register(self,*args):pytest.fail('must not create account')
    monkeypatch.setattr(cli,'AdminService',NoWrite)
    with pytest.raises(SystemExit):cli.main()
    captured=capsys.readouterr();assert private not in captured.err+captured.out


def test_invalid_ticket_does_not_perform_password_hash(lifecycle,monkeypatch):
    svc,db,mail=lifecycle
    def expensive(*args):raise AssertionError('Invalid ticket reached scrypt')
    monkeypatch.setattr(accounts,'hash_password',expensive)
    with pytest.raises(HTTPException) as exc:
        svc.finish(EMAIL,'reset',secrets.token_urlsafe(32),PASSWORD)
    assert exc.value.status_code==400


def test_mail_bound_and_expired_authorization_before_send(monkeypatch):
    from foodsave.account_mail import AcsAccountMail,bounded_message
    monkeypatch.setenv('FOODSAVE_MAIL_APPROVED','true')
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    monkeypatch.setenv('FOODSAVE_ACS_EMAIL_ENDPOINT','https://fixture.communication.azure.com')
    monkeypatch.setenv('FOODSAVE_MAIL_FROM','noreply@example.test')
    mail=AcsAccountMail()
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL',(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    with pytest.raises(MailUnavailable):mail.send_code(EMAIL,'reset',secrets.token_urlsafe(32))
    with pytest.raises(MailUnavailable):bounded_message(b'x'*4097)


def test_shared_password_and_mail_budgets():
    from types import SimpleNamespace
    calls=[]
    svc=SimpleNamespace(throttle=lambda *args,**kwargs:calls.append((args,kwargs)))
    request=SimpleNamespace(client=SimpleNamespace(host='fixture'))
    api_module.account_quota(svc,request,EMAIL,'mail',sending=True)
    quotas={args[0]:kwargs.get('limit') for args,kwargs in calls}
    assert quotas['auth:mail:global:hour']==10 and quotas['auth:mail:global:day']==30 and quotas['auth:mail:global:month']==1000
    calls.clear();api_module.account_quota(svc,request,EMAIL,'finish')
    assert (('auth:password:global','all',20,60),{}) in calls


def test_mail_recipient_uses_same_email_contract():
    from foodsave.account_mail import validate_recipient
    for address in ("o'connor@example.com",'a!b=c@example.com'):
        assert EmailRequest(email=address).email==address
        validate_recipient(address)
    with pytest.raises(MailUnavailable):validate_recipient('victim@example.com\r\nBcc:other@example.com')


@pytest.mark.parametrize('path,body',[
 ('/auth/login',{'email':EMAIL,'password':PASSWORD}),
 ('/auth/verify-email',{'email':EMAIL,'password':PASSWORD,'code':secrets.token_urlsafe(32)}),
 ('/auth/reset-password',{'email':EMAIL,'password':PASSWORD,'code':secrets.token_urlsafe(32)}),
 ('/auth/change-password',{'current_password':PASSWORD,'password':OTHER}),
 ('/account/deletion-status',{'email':EMAIL,'password':PASSWORD}),
 ('/account/deletion-request',{'email':EMAIL,'password':PASSWORD,'confirm':'DELETE'}),
 ('/account/deletion-requests',{'password':PASSWORD,'confirm':'DELETE'}),
])
def test_exhausted_global_budget_stops_every_http_password_entry(http,monkeypatch,path,body):
    client,svc,db,mail,limits=http
    limits[('auth:password:global','all')]=20
    api_module.app.dependency_overrides[api_module.current_user]=lambda:{'id':'fixture','email':EMAIL,'role':'consumer'}
    def forbidden(*args,**kwargs):raise AssertionError('Exhausted password budget reached expensive operation')
    for module in (accounts,service_module):
        monkeypatch.setattr(module,'hash_password',forbidden)
        monkeypatch.setattr(module,'verify_password',forbidden)
    for method in ('login','finish','change_password','deletion_with_credentials','request_deletion'):
        monkeypatch.setattr(svc,method,forbidden)
    result=client.post(path,json=body,headers={'Authorization':'Bearer '+secrets.token_urlsafe(32)})
    assert result.status_code==429
    assert not db.sql and not mail.sent


@pytest.mark.parametrize('endpoint,accepted',[
 ('https://fixture.asiapacific.communication.azure.com',True),
 ('https://fixture.communication.azure.com',True),
 ('http://fixture.asiapacific.communication.azure.com',False),
 ('https://fixture.communication.azure.com.evil.test',False),
 ('https://fixture.asiapacific.communication.azure.com@evil.test',False),
])
def test_acs_accepts_regional_endpoint_only_under_expected_https_host(monkeypatch,endpoint,accepted):
    from foodsave.account_mail import AcsAccountMail
    monkeypatch.setenv('FOODSAVE_MAIL_APPROVED','true')
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    monkeypatch.setenv('FOODSAVE_ACS_EMAIL_ENDPOINT',endpoint)
    monkeypatch.setenv('FOODSAVE_MAIL_FROM','noreply@example.test')
    if accepted:assert AcsAccountMail().endpoint==endpoint
    else:
        with pytest.raises(MailUnavailable):AcsAccountMail()
