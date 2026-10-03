"""Server-only SMTP/TLS adapter. No console mailer, token logging or production test mode."""
import os
import json
from datetime import datetime,timezone,timedelta
import re
import smtplib
import ssl
from email.message import EmailMessage
from threading import BoundedSemaphore
from pydantic import ValidationError
from .schemas import EmailRequest


class MailUnavailable(Exception):
    pass


_SLOTS = BoundedSemaphore(2)


def authorization():
    try:
        until=datetime.fromisoformat(os.getenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL','').replace('Z','+00:00'))
        now=datetime.now(timezone.utc)
        valid=until.tzinfo is not None and now<until<=now+timedelta(hours=24)
    except ValueError:
        valid=False
    if os.getenv('FOODSAVE_MAIL_APPROVED')!='true' or not valid:
        raise MailUnavailable()


def validate_recipient(email):
    try:
        EmailRequest(email=email)
    except ValidationError:
        raise MailUnavailable() from None


def bounded_message(payload):
    if len(payload)>4096:
        raise MailUnavailable()


class SmtpAccountMail:
    def __init__(self):
        authorization()
        self.host=os.getenv('FOODSAVE_SMTP_HOST','')
        self.port=os.getenv('FOODSAVE_SMTP_PORT','465')
        self.sender=os.getenv('FOODSAVE_MAIL_FROM','')
        self.username=os.getenv('FOODSAVE_SMTP_USER','')
        self.password=os.getenv('FOODSAVE_SMTP_PASSWORD','')
        if (os.getenv('FOODSAVE_MAIL_APPROVED')!='true' or self.port not in ('465','587') or
            not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',self.host) or
            not re.fullmatch(r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',self.sender) or
            not self.username or not self.password):
            raise MailUnavailable()

    def send_code(self, email, purpose, code):
        authorization()
        validate_recipient(email)
        if purpose not in ('register','reset') or not re.fullmatch(r'[A-Za-z0-9_-]{43}',code):
            raise MailUnavailable()
        message=EmailMessage()
        message['From']=self.sender;message['To']=email
        message['Subject']='FoodSave 食在可惜｜'+('信箱驗證' if purpose=='register' else '重設密碼')
        message.set_content('請回到 FoodSave App，貼上以下一次性驗證碼，再自行設定密碼。\n'
                            '有效期15分鐘；再次要求寄信會使前一封失效。不要分享驗證碼或密碼。\n\n'+code+
                            '\n\n若不是你提出的要求，請忽略此信。此郵件不確認該信箱是否已有帳號。')
        bounded_message(message.as_bytes())
        if not _SLOTS.acquire(timeout=1):
            raise MailUnavailable()
        try:
            context=ssl.create_default_context()
            if self.port=='465':
                connection=smtplib.SMTP_SSL(self.host,465,timeout=8,context=context)
            else:
                connection=smtplib.SMTP(self.host,587,timeout=8)
            with connection as smtp:
                smtp.ehlo()
                if self.port=='587':
                    smtp.starttls(context=context);smtp.ehlo()
                smtp.login(self.username,self.password)
                authorization()
                if smtp.send_message(message):
                    raise MailUnavailable()
        except Exception:
            # Exceptions may contain recipients or provider replies. Never expose them.
            raise MailUnavailable() from None
        finally:
            _SLOTS.release()


class AcsAccountMail:
    """Azure managed identity only; no connection string, account key or CLI fallback.

    Uses SDK NoPolling: HTTP acceptance is NOT delivery confirmation. No background
    thread, provider retry queue, tracking pixel, application retry or token log.
    """
    def __init__(self):
        authorization()
        self.endpoint=os.getenv('FOODSAVE_ACS_EMAIL_ENDPOINT','').rstrip('/')
        self.sender=os.getenv('FOODSAVE_MAIL_FROM','')
        if (os.getenv('FOODSAVE_MAIL_APPROVED')!='true' or
            not re.fullmatch(r'https://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?\.communication\.azure\.com',self.endpoint) or
            not re.fullmatch(r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',self.sender)):
            raise MailUnavailable()

    def send_code(self,email,purpose,code):
        if purpose not in ('register','reset') or not re.fullmatch(r'[A-Za-z0-9_-]{43}',code):
            raise MailUnavailable()
        self._send(email,
                   'FoodSave 食在可惜｜'+('信箱驗證' if purpose=='register' else '重設密碼'),
                   '請回到FoodSave App貼上一次性驗證碼，再自行設定密碼。有效期15分鐘；重送使舊碼失效。勿分享驗證碼或密碼。\n\n'+code+'\n\n非本人操作請忽略；此信不確認是否已有帳號。')

    def _send(self,email,subject,plain_text):
        # Internal transport shared with the reviewed CLI delivery probe; no HTTP route.
        authorization()
        validate_recipient(email)
        if not _SLOTS.acquire(timeout=1):
            raise MailUnavailable()
        try:
            from azure.communication.email import EmailClient
            from azure.identity import ManagedIdentityCredential
            # Only the existing system-assigned App Service identity is used.
            with ManagedIdentityCredential(retry_total=0,connection_timeout=3,read_timeout=5) as credential:
                with EmailClient(self.endpoint,credential,retry_total=0,connection_timeout=3,read_timeout=8,logging_enable=False) as client:
                    message={
                        'senderAddress':self.sender,
                        'recipients':{'to':[{'address':email}]},
                        'content':{'subject':subject,'plainText':plain_text},
                        'userEngagementTrackingDisabled':True,
                    }
                    bounded_message(json.dumps(message,ensure_ascii=False).encode('utf-8'))
                    authorization()
                    result=client.begin_send(message,polling=False,logging_enable=False).result()
                    if not result or result.get('status') not in ('Running','Succeeded'):
                        raise MailUnavailable()
        except Exception:
            raise MailUnavailable() from None
        finally:
            _SLOTS.release()


def configured_mailer():
    provider=os.getenv('FOODSAVE_MAIL_PROVIDER','')
    if provider=='acs':return AcsAccountMail()
    if provider=='smtp':return SmtpAccountMail()
    raise MailUnavailable()
