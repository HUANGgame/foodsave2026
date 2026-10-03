"""Verified consumer enrollment and one-use recovery. No plaintext secret persistence."""
import secrets
from .db import one, execute
from .service import Service, fail, uid
from .security import digest, hash_password, verify_password

GENERIC='若此信箱可完成此操作，請查看信件並依指示繼續。驗證碼15分鐘內有效。'
INVALID='驗證碼無效、已使用或已過期，請重新申請。'


def email_key(email):
    return digest('account-email:'+email.casefold())


def challenge_key(purpose, email, code):
    return digest('account-code:'+purpose+':'+email.casefold()+':'+code)


def lock_email(c, email):
    result=one(c,"DECLARE @r int; EXEC @r=sp_getapplock @Resource=:resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=5000; SELECT @r AS result",resource='foodsave:account:'+email_key(email))
    if not result or result['result']<0:
        fail(503,'帳號服務忙碌，請稍後再試')


class AccountService(Service):
    def request_code(self, email, purpose, mailer):
        if purpose not in ('register','reset'):
            raise ValueError('Invalid purpose')
        # Deliberately no account-existence lookup: same SQL/mail work and response.
        code=secrets.token_urlsafe(32)
        with self.transaction() as c:
            lock_email(c,email)
            execute(c,'DELETE TOP (100) FROM dbo.account_challenges WHERE expires_at<DATEADD(day,-1,SYSUTCDATETIME())')
            execute(c,'DELETE FROM dbo.account_challenges WHERE email_key=:e AND purpose=:purpose',e=email_key(email),purpose=purpose)
            execute(c,"INSERT dbo.account_challenges(token_hash,email_key,purpose,expires_at) VALUES(:token,:e,:purpose,DATEADD(minute,15,SYSUTCDATETIME()))",token=challenge_key(purpose,email,code),e=email_key(email),purpose=purpose)
        # Commit before sending. On mail failure never retry or pretend sent; an
        # ambiguous provider acknowledgement does not invalidate a delivered code.
        mailer.send_code(email,purpose,code)
        return {'detail':GENERIC}

    def finish(self, email, purpose, code, password):
        encoded=hash_password(password)
        with self.transaction() as c:
            lock_email(c,email)
            ticket=one(c,'SELECT token_hash FROM dbo.account_challenges WITH(UPDLOCK,HOLDLOCK) WHERE token_hash=:token AND email_key=:e AND purpose=:purpose AND expires_at>SYSUTCDATETIME()',token=challenge_key(purpose,email,code),e=email_key(email),purpose=purpose)
            if not ticket:
                fail(400,INVALID)
            user=one(c,'SELECT id,password_hash,active FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE email=:email',email=email)
            if purpose=='register':
                if user:
                    fail(400,INVALID)
                execute(c,"INSERT dbo.users(id,email,password_hash,role,email_verified_at) VALUES(:id,:email,:password,'consumer',SYSUTCDATETIME())",id=uid(),email=email,password=encoded)
            elif purpose=='reset':
                if not user or not user['active']:
                    fail(400,INVALID)
                result=one(c,'EXEC dbo.apply_account_password @user_id=:u,@expected_hash=:old,@new_hash=:new,@verify_email=1',u=user['id'],old=user['password_hash'],new=encoded)
                if not result or result['changed']!=1:
                    fail(400,INVALID)
            else:
                raise ValueError('Invalid purpose')
            # All codes for this email are consumed atomically with the change.
            execute(c,'DELETE FROM dbo.account_challenges WHERE email_key=:e',e=email_key(email))
        return {'detail':'已完成。請使用新密碼重新登入。','sessions_revoked':True}

    def change_password(self, user, token, current_password, password):
        encoded=hash_password(password)
        with self.transaction() as c:
            lock_email(c,user['email'])
            current=one(c,'SELECT id,email,password_hash,active FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id=:u',u=user['id'])
            # Revalidate inside the transaction; a reset may revoke the dependency's
            # session between HTTP authentication and this write.
            session=one(c,'SELECT token_hash FROM dbo.sessions WHERE token_hash=:token AND user_id=:u AND expires_at>SYSUTCDATETIME()',token=digest(token),u=user['id'])
            if not current or not current['active'] or not session or not verify_password(current_password,current['password_hash']):
                fail(401,'身分確認失敗，請重新登入')
            if password==current_password or password.casefold()==current['email'].casefold():
                fail(422,'請選擇不同的新密碼')
            result=one(c,'EXEC dbo.apply_account_password @user_id=:u,@expected_hash=:old,@new_hash=:new,@verify_email=0',u=user['id'],old=current['password_hash'],new=encoded)
            if not result or result['changed']!=1:
                fail(401,'身分確認失敗，請重新登入')
            execute(c,'DELETE FROM dbo.account_challenges WHERE email_key=:e',e=email_key(current['email']))
        return {'detail':'密碼已更新，所有裝置已登出。請重新登入。','sessions_revoked':True}
