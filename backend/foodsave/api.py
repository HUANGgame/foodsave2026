import os
import json
from html import escape
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import DBAPIError, IntegrityError
from .admin import AdminService
from .db import one
from . import schemas as S
from . import demo_prizes
from .ranking import RankingService
from .service import require, require_vendor
from .accounts import AccountService
from .account_mail import configured_mailer, MailUnavailable
from .security import PasswordCapacityError

app = FastAPI(title='FoodSave API', version='0.2.0-core', docs_url=None, redoc_url=None, openapi_url=None)
origins = [x.strip() for x in os.getenv('FOODSAVE_ALLOWED_ORIGINS', '').split(',') if x.strip()]
if origins:
    if '*' in origins:
        raise RuntimeError('Explicit CORS origins required')
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=['GET','POST','PUT'], allow_headers=['Authorization','Content-Type','Idempotency-Key'])


def service():
    return AdminService()


bearer = HTTPBearer(auto_error=False)


def token(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not auth or auth.scheme.lower() != 'bearer' or len(auth.credentials) > 256:
        raise HTTPException(401, '請先登入')
    return auth.credentials


def current_user(value=Depends(token), svc=Depends(service)):
    return svc.authenticate(value)


def request_key(value: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_.:-]+$')]):
    return value


User = Annotated[dict, Depends(current_user)]
Svc = Annotated[AdminService, Depends(service)]
Key = Annotated[str, Depends(request_key)]


@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo submitted password/token/body in validation failures.
    return JSONResponse(status_code=422, content={'detail': '欄位格式不正確', 'fields': [list(e['loc']) for e in exc.errors()]})


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={'detail': '資料已變更或重複，請重新載入'})


@app.exception_handler(DBAPIError)
async def unavailable(request, exc):
    # Includes deadlock victim/connection recovery; no automatic mutation replay.
    # Client must retry the original operation with its original idempotency key.
    detail='帳號操作結果尚未確認；若剛提交新密碼，請先嘗試新密碼登入。' if request.url.path.startswith('/auth/') else '資料服務暫時無法使用，請保留原重試識別碼後重試'
    return JSONResponse(status_code=503, headers={'Retry-After': '20'}, content={'detail':detail})


@app.get('/health/live')
def live():
    return {'status': 'alive'}


@app.get('/privacy')
def privacy():
    policy=json.loads((Path(__file__).parent/'static'/'privacy-policy.json').read_text())
    defaults = {'operator': 'HUANG', 'contact': '413637629@o365.tku.edu.tw', 'retention': policy['summary']}
    fields = {name: os.getenv(variable) or defaults[name] for name, variable in {
        'operator': 'FOODSAVE_OPERATOR_NAME', 'contact': 'FOODSAVE_PRIVACY_CONTACT',
        'retention': 'FOODSAVE_RETENTION_SUMMARY'}.items()}
    return {**fields, 'status': 'configured' if all(fields.values()) and os.getenv('FOODSAVE_PRIVACY_POLICY_COMPLETE') == 'true' else 'draft',
            'deletion_page': '/account', 'request_is_erasure': False,'policy':policy,'policy_page':'/privacy-policy'}


@app.get('/privacy-policy',response_class=HTMLResponse)
def privacy_policy_page():
    data=privacy();policy=data['policy']
    content='<h1>FoodSave 隱私與帳號刪除說明</h1><p>已定案的低流量測試政策；開放狀態以App即時檢查為準。</p>'
    content+='<p>營運者：'+escape(data['operator'])+'；聯絡：'+escape(data['contact'])+'</p>'
    for section in policy['sections']:
        content+='<h2>'+escape(section['title'])+'</h2>'
        content+=''.join('<p>'+escape(p)+'</p>' for p in section['paragraphs'])
    content+=''.join('<p><a href="'+escape(link['url'],quote=True)+'" rel="noreferrer">'+escape(link['label'])+'</a></p>' for link in policy['links'])
    content+='<p><a href="/account">提出或查詢刪除申請</a></p>'
    return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FoodSave 隱私說明</title><link rel="stylesheet" href="/admin.css"></head><body><main>'+content+'</main></body></html>'


@app.post('/admin/maintenance')
def maintenance(user: User, svc: Svc):
    require(user, 'admin')
    svc.throttle('maintenance', user['id'])
    # Synchronous, bounded work. No background task that could be lost to F1 sleep.
    # SQL transaction / settlement record make a repeated call safe.
    expired = svc.expire_reservations(limit=100)
    ranking = RankingService(svc.database).settle_previous_week()
    return {'expired': expired, 'ranking': ranking}


@app.get('/health/ready')
def ready(svc: Svc):
    for attempt in range(2):
        try:
            with svc.transaction() as c:
                version="012_account_lifecycle.sql" if os.getenv("FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED")=="true" else "011_mark_notification_read.sql"
                found = one(c, "SELECT version FROM dbo.schema_migrations WHERE version=:version",version=version)
                if not found:
                    raise HTTPException(503, '資料庫尚未初始化')
            return {'status': 'ready'}
        except DBAPIError as exc:
            if attempt == 0 and '40613' in str(exc.orig):
                time.sleep(1)  # bounded read-only retry for Azure serverless resume
                continue
            raise
        except RuntimeError:
            raise HTTPException(503, '資料庫尚未配置')


def account_service():
    return AccountService()


def mail_service():
    return configured_mailer()


AccountSvc = Annotated[AccountService, Depends(account_service)]


def lifecycle_enabled():
    if os.getenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED')!='true':
        raise HTTPException(503,'帳號驗證服務尚未開放')


def registration_enabled():
    lifecycle_enabled()
    if os.getenv('FOODSAVE_REGISTRATION_ENABLED')!='true' or privacy()['status']!='configured':
        raise HTTPException(503,'公開註冊尚未開放')


def account_quota(svc, request, email, action, sending=False):
    ip=request.client.host if request.client else 'unknown'
    # Socket peer is an aggregate proxy guard, never a trusted end-user IP.
    # Mail guards stay unchanged; hash-entry peer budget matches global admission.
    svc.throttle('auth:'+action+':ip',ip,limit=10 if sending else 20,window_seconds=900 if sending else 60)
    svc.throttle('auth:'+action+':email',email,limit=3 if sending else 10,window_seconds=900)
    if sending:
        svc.throttle('auth:mail:global:minute','all',limit=5,window_seconds=60)
        svc.throttle('auth:mail:global:hour','all',limit=10,window_seconds=3600)
        svc.throttle('auth:mail:global:day','all',limit=30,window_seconds=86400)
        svc.throttle('auth:mail:global:month',datetime.now(timezone.utc).strftime('%Y-%m'),limit=1000,window_seconds=2678400)
    else:
        password_quota(svc)


def password_quota(svc):
    # Shared SQL budget across instances; one admission can verify and rehash.
    svc.throttle('auth:password:global','all',20,60)


@app.exception_handler(MailUnavailable)
async def mail_unavailable(request, exc):
    return JSONResponse(status_code=503,content={'detail':'寄信服務未就緒或結果尚未確認，請稍後再試；不代表郵件已送達。'})


@app.exception_handler(PasswordCapacityError)
async def password_capacity(request, exc):
    return JSONResponse(status_code=503,content={'detail':'帳號服務忙碌，請稍後再試'})


@app.get('/auth/options')
def auth_options():
    enabled=os.getenv('FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED')=='true'
    try:
        mail_service()
    except MailUnavailable:
        enabled=False
    return {'recovery_enabled':enabled,'registration_enabled':enabled and os.getenv('FOODSAVE_REGISTRATION_ENABLED')=='true' and privacy()['status']=='configured'}


@app.post('/auth/register',status_code=202)
def register(body:S.EmailRequest,request:Request,svc:AccountSvc):
    registration_enabled()
    mailer=mail_service()
    account_quota(svc,request,body.email,'mail',sending=True)
    return svc.request_code(body.email,'register',mailer)


@app.post('/auth/verify-email')
def verify_email(body:S.FinishAccount,request:Request,svc:AccountSvc):
    registration_enabled()
    account_quota(svc,request,body.email,'finish')
    return svc.finish(body.email,'register',body.code,body.password)


@app.post('/auth/forgot-password',status_code=202)
def forgot_password(body:S.EmailRequest,request:Request,svc:AccountSvc):
    lifecycle_enabled()
    mailer=mail_service()
    account_quota(svc,request,body.email,'mail',sending=True)
    return svc.request_code(body.email,'reset',mailer)


@app.post('/auth/reset-password')
def reset_password(body:S.FinishAccount,request:Request,svc:AccountSvc):
    lifecycle_enabled()
    account_quota(svc,request,body.email,'finish')
    return svc.finish(body.email,'reset',body.code,body.password)


@app.post('/auth/change-password')
def change_password(body:S.ChangePassword,user:User,svc:AccountSvc,value=Depends(token)):
    lifecycle_enabled()
    svc.throttle('auth:change',user['id'],limit=5,window_seconds=900)
    password_quota(svc)
    return svc.change_password(user,value,body.current_password,body.password)


@app.post('/auth/login')
def login(body:S.Credentials,request:Request,svc:Svc):
    svc.throttle('login',request.client.host if request.client else 'unknown',20,60)
    svc.throttle('login:email',body.email)
    password_quota(svc)
    return svc.login(body.email,body.password)


@app.post('/auth/logout')
def logout(user: User, svc: Svc, value=Depends(token)):
    return svc.logout(value)


@app.get('/me')
def me(user: User, svc: Svc):
    return svc.account(user)


@app.get('/products')
def products(svc: Svc):
    return svc.list_products()


@app.get('/prizes')
def prizes(svc: Svc):
    return svc.public_prizes()


@app.get('/stores')
def stores(user: User,svc: Svc):
    return svc.stores(user)


@app.get('/notifications')
def notifications(user: User,svc: Svc):
    return svc.notifications(user)


@app.post('/notifications/{identity}/read')
def read_notification(identity: str,user: User,svc: Svc):
    return svc.mark_notification_read(user,identity)


@app.get('/favorites')
def favorites(user: User, svc: Svc):
    return svc.favorites(user)


@app.get('/stores/{identity}/reviews')
def reviews(identity: str, svc: Svc):
    return svc.store_reviews(identity)


@app.post('/vendor/store', status_code=201)
def own_store_create(body: S.OwnStore, user: User, svc: Svc, key: Key):
    return svc.create_own_store(user, key, body.model_dump())


@app.get('/vendor/catalog')
def catalog(user: User, svc: Svc):
    return svc.vendor_catalog(user)


@app.post('/account/deletion-requests', status_code=202)
def deletion(body: S.DeleteAccount, user: User, svc: Svc):
    svc.throttle('delete', user['id'])
    password_quota(svc)
    return svc.request_deletion(user, body.password)


def deletion_throttle(request, svc, email):
    svc.throttle('deletion-public-ip', request.client.host if request.client else 'unknown',20,60)
    svc.throttle('deletion-public-account', email)
    password_quota(svc)


@app.post('/account/deletion-status')
def deletion_status(body: S.Credentials, request: Request, svc: Svc):
    deletion_throttle(request, svc, body.email)
    return svc.deletion_with_credentials(body.email, body.password)


@app.post('/account/deletion-request', status_code=202)
def public_deletion(body: S.PublicDeleteAccount, request: Request, svc: Svc):
    deletion_throttle(request, svc, body.email)
    return svc.deletion_with_credentials(body.email, body.password, submit=True)


@app.get('/account')
def account_page():
    return FileResponse(Path(__file__).parent / 'static' / 'account.html')


@app.get('/account.js')
def account_script():
    return FileResponse(Path(__file__).parent / 'static' / 'account.js', media_type='text/javascript')


@app.post('/reservations', status_code=201)
def reserve(body: S.Reservation, user: User, svc: Svc, key: Key):
    require(user, 'consumer', 'vendor')
    svc.throttle('reserve', user['id'], limit=30, window_seconds=60)
    return svc.reserve(user, key, body.product_id, body.quantity)


@app.get('/reservations')
def reservations(user: User, svc: Svc):
    return svc.history(user, 'reservations')


@app.post('/reservations/{identity}/cancel')
def cancel(identity: str, user: User, svc: Svc, key: Key):
    return svc.transition(user, key, identity, 'cancelled')


@app.post('/vendor/reservations/{identity}/complete')
def complete(identity: str, body: S.Pickup, user: User, svc: Svc, key: Key):
    svc.throttle('pickup', user['id'])
    return svc.transition(user, key, identity, 'completed', body.code)


@app.post('/vendor/pickups/preview')
def pickup_preview(body: S.PickupPreview, user: User, svc: Svc, key: Key):
    require_vendor(user)
    # Camera scanning is not fulfillment. Bound requests per authenticated vendor.
    svc.throttle('pickup-preview', user['id'], limit=60, window_seconds=60)
    if not body.credential.startswith('FS1.'):
        svc.throttle('pickup-manual', user['id'])
    return svc.preview_pickup(user, key, body.credential)


@app.post('/vendor/pickups/confirm')
def pickup_confirm(body: S.PickupConfirmation, user: User, svc: Svc, key: Key):
    require_vendor(user)
    return svc.confirm_pickup(user, key, body.review_key, body.review_token)


@app.get('/vendor/reservations')
def vendor_orders(user: User, svc: Svc):
    return svc.vendor_orders(user)


@app.post('/draws', status_code=201)
def draw(user: User, svc: Svc, key: Key):
    return svc.draw(user, key)


@app.get('/draws')
def draws(user: User, svc: Svc):
    return svc.history(user, 'draws')


@app.put('/favorites/{vendor_id}')
def favorite(vendor_id: str, body: S.Favorite, user: User, svc: Svc, key: Key):
    return svc.favorite(user, key, vendor_id, body.enabled)


@app.post('/reservations/{identity}/review', status_code=201)
def review(identity: str, body: S.Review, user: User, svc: Svc, key: Key):
    return svc.review(user, key, identity, body.rating, body.body)


@app.post('/vendor/products', status_code=201)
def product_create(body: S.Product, user: User, svc: Svc, key: Key):
    return svc.save_product(user, key, body.model_dump())


@app.put('/vendor/products/{identity}')
def product_update(identity: str, body: S.Product, user: User, svc: Svc, key: Key):
    return svc.save_product(user, key, body.model_dump(), identity)


@app.put('/vendor/stores/{identity}/mode')
def store_mode(identity: str, body: S.StoreMode, user: User, svc: Svc, key: Key):
    return svc.set_store_mode(user, key, identity, body.service_mode)


@app.post('/vendor/stores/{identity}/expire')
def expire_store(identity: str, user: User, svc: Svc, key: Key):
    return svc.expire_store_orders(user, key, identity)


@app.get('/vendor/products/{identity}/stock-loss-preview')
def stock_loss_preview(identity: str,user: User,svc: Svc):
    return svc.stock_loss_preview(user,identity)


@app.post('/vendor/products/{identity}/stock-loss')
def stock_loss(identity: str,body: S.StockLoss,user: User,svc: Svc,key: Key):
    return svc.report_stock_loss(user,key,identity,body.model_dump())


@app.post('/vendor/products/{identity}/stock')
def adjust_stock(identity: str, body: S.StockAdjustment, user: User, svc: Svc, key: Key):
    return svc.adjust_stock(user, key, identity, body.delta)


@app.post('/admin/stores', status_code=201)
def store_create(body: S.Store, user: User, svc: Svc, key: Key):
    return svc.create_store(user, key, body.model_dump())


@app.post('/admin/prizes', status_code=201)
def prize_create(body: S.Prize, user: User, svc: Svc, key: Key):
    return svc.create_prize(user, key, body.model_dump())


@app.post('/admin/spin-grants', status_code=201)
def grant(body: S.Grant, user: User, svc: Svc, key: Key):
    return svc.grant_spins(user, key, body.model_dump())


@app.put('/admin/exp-rules')
def exp_rule(body: S.ExpRule, user: User, svc: Svc, key: Key):
    return svc.configure_exp(user, key, **body.model_dump())


@app.get('/admin/data/{table}')
def data(table: str, user: User, svc: Svc, page: Annotated[int, Query(ge=1, le=10000)] = 1):
    return svc.view_database(user, table, page)


@app.put('/admin/ranking-rules')
def ranking_rules(body: S.RankingRules, user: User, svc: Svc, key: Key):
    return svc.configure_ranking(user, key, [r.model_dump() for r in body.rules])


@app.get('/admin')
def admin_page():
    return FileResponse(Path(__file__).parent / 'static' / 'admin.html')


@app.get('/admin.js')
def admin_script():
    return FileResponse(Path(__file__).parent / 'static' / 'admin.js', media_type='text/javascript')


@app.get('/admin.css')
def admin_style():
    return FileResponse(Path(__file__).parent / 'static' / 'admin.css', media_type='text/css')


@app.get('/demo-prizes')
def demo_pool():
    if not demo_prizes.enabled():
        return {'enabled': False}
    return demo_prizes.public(demo_prizes.read())


@app.get('/admin/demo-prizes')
def demo_pool_admin(user: User):
    require(user, 'admin')
    return demo_prizes.read()


@app.put('/admin/demo-prizes')
def demo_pool_edit(body: demo_prizes.DemoPoolUpdate, user: User):
    require(user, 'admin')
    return demo_prizes.update(body)


@app.post('/demo-draws')
def demo_draw(body: demo_prizes.DemoDrawRequest, user: User):
    require(user, 'consumer', 'vendor')
    result = demo_prizes.draw(body.revision)
    return JSONResponse(status_code=409, content=result) if result.get('code')=='pool_changed' else result
