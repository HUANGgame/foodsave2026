"""Private real-SQL + in-process ASGI acceptance. Default plan only; always rollback.
No network HTTP client, public URL probe, owner identity, grants or committed QA.
"""
import argparse
from contextlib import contextmanager
from datetime import timedelta
import json
import secrets
from uuid import UUID, uuid4, uuid5


class AcceptanceFailure(Exception):
    """Only fixed assertion names may enter this exception."""


class Pinned:
    def __init__(self, connection): self.connection = connection
    @contextmanager
    def begin(self): yield self.connection


def identifiers(run):
    return {n: str(uuid5(run, 'pickup:'+n)) for n in ('consumer','vendor','other-vendor','store','product','expired','expired-review')}


def suite(database, run):
    # These test-only dependencies must already exist in the private runner venv.
    # Import before opening SQL. They are deliberately not added to runtime ZIP.
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient
    from foodsave.api import app, service
    from foodsave.admin import AdminService
    from foodsave.db import execute, one
    from foodsave.security import hash_password, digest
    from foodsave.service import dump
    ids=identifiers(run);results=[];password=secrets.token_urlsafe(32)
    def check(value, name):
        if not value: raise AcceptanceFailure(name)
        results.append(name)
    with database.connect() as c:
        tx=c.begin()
        overrides=dict(app.dependency_overrides)
        try:
            execute(c,'SET LOCK_TIMEOUT 10000')
            check(one(c,'SELECT DB_NAME() AS name')['name']=='foodsave','dedicated_database')
            rights=one(c,"SELECT HAS_PERMS_BY_NAME('dbo.users','OBJECT','DELETE') AS erase,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS owner,HAS_PERMS_BY_NAME('dbo.submit_deletion_request','OBJECT','EXECUTE') AS submit")
            check(rights['erase']==0 and rights['owner']==0 and rights['submit']==1,'restricted_runtime_identity')
            check(bool(one(c,"SELECT version FROM dbo.schema_migrations WHERE version='005_deletion_request_procedure.sql'")),'schema005_present')
            now=one(c,'SELECT SYSUTCDATETIME() AS now')['now']
            for name in ('consumer','vendor','other-vendor'):
                email=f'qa+{run.hex}.{name}@example.invalid'
                if one(c,'SELECT id FROM dbo.users WHERE id=:id OR email=:email',id=ids[name],email=email): raise ValueError('fixture_collision')
                execute(c,'INSERT INTO dbo.users(id,email,password_hash,role) VALUES(:id,:email,:password,:role)',id=ids[name],email=email,password=hash_password(password),role='consumer' if name=='consumer' else 'vendor')
            marker='foodsave-qa:'+run.hex
            execute(c,'INSERT INTO dbo.stores(id,owner_id,name,latitude,longitude) VALUES(:s,:v,:name,0,0)',s=ids['store'],v=ids['vendor'],name=marker)
            execute(c,"INSERT INTO dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active) VALUES(:p,:s,:name,'https://images.example.invalid/qa.png',100,50,1,:expiry,1)",p=ids['product'],s=ids['store'],name=marker,expiry=now+timedelta(minutes=10))
            svc=AdminService(Pinned(c));app.dependency_overrides[service]=lambda:svc
            stock=lambda:one(c,'SELECT available_quantity AS n FROM dbo.products WHERE id=:p',p=ids['product'])['n']
            exp=lambda:one(c,'SELECT COUNT(*) AS n FROM dbo.exp_events WHERE user_id=:u',u=ids['consumer'])['n']
            with TestClient(app,raise_server_exceptions=False,client=('qa-'+run.hex,50000)) as client:
                tokens={}
                for name in ('consumer','vendor','other-vendor'):
                    login=client.post('/auth/login',json={'email':f'qa+{run.hex}.{name}@example.invalid','password':password})
                    if login.status_code!=200: raise AcceptanceFailure('fixture_login')
                    tokens[name]=login.json()['access_token']
                check(True,'real_sql_login_all_three_roles')
                def post(name,path,body,key=None):
                    return client.post(path,json=body,headers={'Authorization':'Bearer '+tokens[name],'Idempotency-Key':key or str(uuid4())})
                check(client.post('/vendor/pickups/preview',json={'credential':'A'*12},headers={'Idempotency-Key':str(uuid4())}).status_code==401,'unauthenticated_preview_denied')
                reserve_key=str(uuid4())
                r=post('consumer','/reservations',{'product_id':ids['product'],'quantity':1},reserve_key)
                check(r.status_code==201,'reserve_http201')
                order=r.json();qr=order['pickup_qr'];code=order['pickup_code']
                check(qr.startswith('FS1.') and len(qr)==47 and '@' not in qr and ids['consumer'] not in qr,'opaque_qr_no_identity')
                replay=post('consumer','/reservations',{'product_id':ids['product'],'quantity':1},reserve_key)
                check(replay.status_code==201 and replay.json()==order and stock()==0,'reserve_same_key_once')
                check(post('consumer','/reservations',{'product_id':ids['product'],'quantity':1}).status_code==409 and stock()==0,'new_key_duplicate_hold_denied')
                check(post('consumer','/vendor/pickups/preview',{'credential':qr}).status_code==403,'consumer_cannot_preview')
                check(post('other-vendor','/vendor/pickups/preview',{'credential':qr}).status_code==404,'other_store_qr_denied')
                malformed=post('vendor','/vendor/pickups/preview',{'credential':'https://example.invalid/not-a-pickup'})
                check(malformed.status_code==422 and 'https://' not in malformed.text,'untrusted_qr_format_redacted')
                review_key=str(uuid4());before=(stock(),exp())
                r=post('vendor','/vendor/pickups/preview',{'credential':qr},review_key)
                check(r.status_code==200,'qr_preview_http200')
                review=r.json()
                state=one(c,'SELECT state FROM dbo.reservations WHERE id=:id',id=order['id'])['state']
                check(state=='waiting' and (stock(),exp())==before,'preview_does_not_fulfill_or_change_stock_exp')
                check(review['name']==marker and review['quantity']==1 and review['total_price_minor']==50 and 'user_id' not in review,'preview_exact_snapshot_without_customer_identity')
                check(post('vendor','/vendor/pickups/preview',{'credential':code}).status_code==200,'manual_code_preview_still_requires_confirmation')
                body={'review_key':review_key,'review_token':review['review_token']}
                check(post('other-vendor','/vendor/pickups/confirm',body).status_code==404,'review_bound_to_vendor')
                check(post('vendor','/vendor/pickups/confirm',{**body,'review_token':secrets.token_urlsafe(32)}).status_code==404,'wrong_review_token_denied')
                confirm_key=str(uuid4());r=post('vendor','/vendor/pickups/confirm',body,confirm_key)
                check(r.status_code==200 and r.json()['state']=='completed','explicit_confirm_fulfills')
                exp_after=exp();replay=post('vendor','/vendor/pickups/confirm',body,confirm_key)
                check(replay.status_code==200 and replay.json()==r.json() and exp()==exp_after and stock()==0,'lost_reply_same_key_recovers_without_double_exp_stock')
                check(post('vendor','/vendor/pickups/confirm',body).status_code==409,'new_key_second_delivery_denied')
                check(post('vendor','/vendor/pickups/preview',{'credential':qr}).status_code==409,'spent_qr_denied')
                # No global rule updates. Existing enabled/disabled policy is respected.
                rule=one(c,"SELECT amount,enabled FROM dbo.exp_rules WHERE event='pickup'")
                check(exp_after==(1 if rule and rule['enabled'] else 0),'existing_exp_policy_respected_once')
                stock_key=str(uuid4());r=post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':1},stock_key)
                replay=post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':1},stock_key)
                check(r.status_code==200 and replay.json()==r.json() and stock()==1,'stock_plus_retry_once')
                check(post('other-vendor',f"/vendor/products/{ids['product']}/stock",{'delta':1}).status_code==404,'other_store_stock_denied')
                check(post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':-1}).status_code==200 and stock()==0,'stock_minus_once')
                check(post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':-1}).status_code==409 and stock()==0,'stock_negative_denied')
                check(post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':2}).status_code==422,'stock_delta_bound')
                # Scoped temporary UPDATE is allowed on product quantity; rollback only.
                execute(c,'UPDATE dbo.products SET available_quantity=1000000 WHERE id=:p',p=ids['product'])
                check(post('vendor',f"/vendor/products/{ids['product']}/stock",{'delta':1}).status_code==409 and stock()==1000000,'stock_upper_bound')
                execute(c,'UPDATE dbo.products SET available_quantity=0 WHERE id=:p',p=ids['product'])
                # Fresh past-expiry INSERT; never UPDATE protected reservation expiry.
                expired_code=secrets.token_hex(6).upper()
                execute(c,"INSERT INTO dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,'waiting',1,:snapshot,:hash,:expiry)",id=ids['expired'],u=ids['consumer'],p=ids['product'],snapshot=dump({'name':marker,'sale_price_minor':50}),hash=digest(expired_code),expiry=now-timedelta(seconds=1))
                check(post('vendor','/vendor/pickups/preview',{'credential':expired_code}).status_code==409,'expired_manual_code_denied')
                expiry_key=str(uuid4());r=post('consumer',f"/reservations/{ids['expired']}/cancel",{},expiry_key)
                replay=post('consumer',f"/reservations/{ids['expired']}/cancel",{},expiry_key)
                check(r.status_code==200 and r.json()['state']=='expired' and replay.json()==r.json() and stock()==1 and exp()==exp_after,'expiry_release_once_without_exp')
                # Expired review fixture INSERT verifies the time boundary without sleep.
                expired_key='expired-review-'+str(uuid4());expired_token=secrets.token_urlsafe(32)
                execute(c,"INSERT INTO dbo.request_results(user_id,operation,request_key,fingerprint,response) VALUES(:u,'pickup-preview',:key,:hash,:response)",u=ids['vendor'],key=expired_key,hash=digest('fixture'),response=dump({'id':order['id'],'review_token':expired_token,'review_expires_at':now-timedelta(seconds=1)}))
                check(post('vendor','/vendor/pickups/confirm',{'review_key':expired_key,'review_token':expired_token}).status_code==409,'expired_review_denied')
                # Two prior manual previews consumed quota; the rest are wrong guesses.
                attempts=0
                while attempts<12:
                    r=post('vendor','/vendor/pickups/preview',{'credential':secrets.token_hex(6).upper()})
                    attempts+=1
                    if r.status_code==429:break
                    if r.status_code!=404:raise AcceptanceFailure('unexpected_guess_result')
                check(r.status_code==429 and attempts==9,'manual_guess_rate_limit_after_ten_attempts')
                check(stock()==1 and exp()==exp_after,'failed_guesses_leave_order_stock_exp_unchanged')
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(overrides)
            tx.rollback()
    with database.connect() as c:
        params={'a':ids['consumer'],'b':ids['vendor'],'v':ids['other-vendor'],'s':ids['store'],'p':ids['product']}
        for table,predicate in (('users','id IN (:a,:b,:v)'),('stores','id=:s'),('products','id=:p'),('reservations','user_id IN (:a,:b,:v)'),('request_results','user_id IN (:a,:b,:v)'),('sessions','user_id IN (:a,:b,:v)'),('exp_events','user_id IN (:a,:b,:v)')):
            check(one(c,f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {predicate}',**params)['n']==0,'rollback_zero_'+table)
        for name in ('consumer','vendor','other-vendor'):
            for action in ('reserve','pickup-preview','pickup-manual'):
                check(one(c,'SELECT COUNT(*) AS n FROM dbo.rate_limits WHERE bucket=:b',b=digest(action+':'+ids[name]))['n']==0,'rollback_zero_rate_'+name+'_'+action)
        check(one(c,'SELECT COUNT(*) AS n FROM dbo.rate_limits WHERE bucket=:b',b=digest('login:qa-'+run.hex))['n']==0,'rollback_zero_login_rate')
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--approved-quiet-window',action='store_true')
    parser.add_argument('--run-id',type=UUID)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'plan','db_access':False,'accounts_in_rollback':3,'store_count':1,'product_count':1,'commits':0,'http':'in-process ASGI only; no public URL/network','requires':['deployed 7824868 pickup API or later compatible build','existing restricted runtime MI','private runner with httpx 0.28.1','approved quiet window and fresh UUID'],'not_covered':['real deployed network HTTP/TLS/CORS','Android-to-Azure','physical camera','two-connection concurrency']}));return
    if not args.approved_quiet_window or not args.run_id:parser.error('Explicit approved quiet window and fresh run UUID required')
    import httpx  # fail before SQL if test dependency is unavailable
    from foodsave.db import engine
    database=engine()
    try:
        results=suite(database,args.run_id)
        print(json.dumps({'status':'passed','mode':'rollback','transport':'in-process ASGI with real SQL','assertion_count':len(results),'assertions':results,'committed_fixtures_remaining':False}))
    except Exception as error:
        print(json.dumps({'status':'failed','error_class':type(error).__name__,'failed_assertion':str(error) if isinstance(error,AcceptanceFailure) else None,'details':'withheld; inspect privately; outer rollback requested','committed_fixture_writes_requested':False}))
        raise SystemExit(1)
    finally:database.dispose()


if __name__=='__main__':main()
