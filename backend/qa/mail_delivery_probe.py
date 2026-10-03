"""Explicit one-attempt CLI delivery probe; no registration, challenge or password."""
import hashlib
import os
import sys
from types import SimpleNamespace
from foodsave.account_mail import AcsAccountMail
from foodsave.api import account_quota
from foodsave.schemas import EmailRequest
from foodsave.service import Service
from foodsave.db import one

_APPROVED_DIGEST='dd998e8b074b0137f22ea136960b607fa582c7fbe86a7efa1d1a991fd67dc03a'
_SUBJECT='FoodSave 食在可惜｜寄信連線測試'
_BODY='這是經你同意寄送的 FoodSave 寄信測試通知。此信沒有驗證碼、密碼或連結，不會建立帳號、驗證信箱或重設密碼。若確實收到，請只回覆「已收到 FoodSave 測試通知」，不要傳送密碼或任何驗證碼。'


def run():
    if (os.getenv('FOODSAVE_MAIL_PROBE_APPROVED')!='true' or
        os.getenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED')!='false' or
        os.getenv('FOODSAVE_REGISTRATION_ENABLED')!='false' or
        os.getenv('FOODSAVE_MAIL_PROVIDER')!='acs'):
        raise ValueError('Probe configuration not authorized')
    email=EmailRequest(email=os.getenv('FOODSAVE_MAIL_PROBE_TO','')).email
    if hashlib.sha256(email.encode('utf-8')).hexdigest()!=_APPROVED_DIGEST:
        raise ValueError('Recipient not authorized')
    mail=AcsAccountMail()  # Checks existing approval/deadline before any SQL.
    svc=Service()
    with svc.transaction() as connection:
        if one(connection,"SELECT DB_NAME() AS name")["name"]!="foodsave":
            raise ValueError("Dedicated database required")
    # Committed first, even failed/ambiguous attempts cannot be automatically retried.
    # Stable bucket across processes/restarts; no reset flag or caller-supplied key.
    svc.throttle('auth:mail:probe:once:v1',email,limit=1,window_seconds=3155760000)
    account_quota(svc,SimpleNamespace(client=SimpleNamespace(host='local-approved-mail-probe')),email,'mail',sending=True)
    mail._send(email,_SUBJECT,_BODY)
    return {'provider_accepted':True,'delivery_confirmed':False,'account_verified':False}


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv)!=['--send-once']:
        print('No email sent. Explicit --send-once and approved server configuration required.')
        return 2
    try:
        run()
    except Exception:
        # Never serialize SQL/provider exceptions, recipients, configuration or headers.
        print('PROBE_NOT_CONFIRMED: no delivery claim; do not automatically retry. Keep account flags off.')
        return 1
    print('ACS_ACCEPTED_ONLY: delivery and account verification are NOT confirmed. Ask the user to confirm receipt; no secrets.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
