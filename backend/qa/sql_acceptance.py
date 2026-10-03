"""Real SQL acceptance harness. Default plan only; no HTTP, mocks or auto cleanup.
Run from backend with its installed requirements and existing runtime MI settings.
"""
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import threading
from uuid import UUID, uuid4, uuid5


def identifiers(run_id):
    return {name: str(uuid5(run_id, name)) for name in ('consumer-a', 'consumer-b', 'vendor', 'store', 'product', 'expiry', 'prize', 'grant', 'request')}


class Pinned:
    """Real connection; service methods share its outer rollback-only transaction."""
    def __init__(self, connection): self.connection = connection
    @contextmanager
    def begin(self): yield self.connection


class Concurrent:
    def __init__(self, database, barrier, sessions):
        self.database, self.barrier, self.sessions = database, barrier, sessions
    @contextmanager
    def begin(self):
        from foodsave.db import execute, one
        with self.database.begin() as c:
            execute(c, 'SET LOCK_TIMEOUT 10000')
            self.sessions.append(one(c, 'SELECT @@SPID AS id')['id'])
            self.barrier.wait(timeout=15)
            yield c


def check(condition, name, results):
    if not condition: raise AssertionError(name)
    results.append(name)


def preflight(c):
    from foodsave.db import execute, one
    execute(c, 'SET LOCK_TIMEOUT 10000')
    if one(c, 'SELECT DB_NAME() AS name')['name'] != 'foodsave': raise ValueError('wrong_database')
    if not one(c, "SELECT version FROM dbo.schema_migrations WHERE version='005_deletion_request_procedure.sql'"):
        raise ValueError('migration_005_required')
    rights = one(c, "SELECT HAS_PERMS_BY_NAME('dbo.users','OBJECT','DELETE') AS erase_users,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS control_db,HAS_PERMS_BY_NAME('dbo.submit_deletion_request','OBJECT','EXECUTE') AS submit")
    if rights['erase_users'] != 0 or rights['control_db'] != 0 or rights['submit'] != 1:
        raise ValueError('use_existing_restricted_runtime_identity')


def seed(c, run_id, ids):
    from foodsave.db import execute, one
    from foodsave.security import hash_password
    # Parameterized fixed UUIDs. No pre-existing row may be reused or updated.
    for name in ('consumer-a', 'consumer-b', 'vendor'):
        if one(c, 'SELECT id FROM dbo.users WHERE id=:id OR email=:email', id=ids[name], email=f'qa+{run_id.hex}.{name}@example.invalid'):
            raise ValueError('fixture_collision_do_not_rerun')
        execute(c, 'INSERT INTO dbo.users(id,email,password_hash,role) VALUES(:id,:email,:password,:role)', id=ids[name], email=f'qa+{run_id.hex}.{name}@example.invalid', password=hash_password(secrets.token_urlsafe(32)), role='vendor' if name=='vendor' else 'consumer')
    execute(c, 'INSERT INTO dbo.stores(id,owner_id,name,latitude,longitude) VALUES(:id,:owner,:name,0,0)', id=ids['store'], owner=ids['vendor'], name='foodsave-qa:'+run_id.hex)
    now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
    execute(c, 'INSERT INTO dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active) VALUES(:id,:store,:name,:photo,100,50,1,:deadline,1)', id=ids['product'], store=ids['store'], name='foodsave-qa:'+run_id.hex, photo='https://images.example.invalid/qa.png', deadline=now+timedelta(minutes=10))
    return now


def count(c, table, user_id):
    from foodsave.db import one
    assert table in ('draws', 'coupons', 'request_results', 'reservations', 'exp_events')
    return one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE user_id=:u', u=user_id)['n']


def expected_http(operation, status, name, results):
    from fastapi import HTTPException
    try: operation()
    except HTTPException as error:
        check(error.status_code == status, name, results)
    else: raise AssertionError(name)


def rejected_sql(c, statement, params, codes, name, results):
    from foodsave.db import execute
    from sqlalchemy.exc import DBAPIError
    try: execute(c, statement, **params)
    except DBAPIError as error:
        # Never print database exception text/SQL parameters to job logs.
        check(any(f'({code})' in str(error.orig) for code in codes), name, results)
    else: raise AssertionError(name)


def rollback_suite(database, run_id, ids):
    from foodsave.db import execute, one
    from foodsave.security import digest
    from foodsave.service import Service, dump
    results = []
    with database.connect() as c:
        tx = c.begin()
        try:
            preflight(c)
            execute(c, 'SET XACT_ABORT OFF')
            # Range-lock eligible prizes: a draw must NEVER pick an existing prize.
            # Short operator-approved quiet window required; rollback releases locks.
            existing = one(c, 'SELECT COUNT(*) AS n FROM dbo.prizes WITH(HOLDLOCK) WHERE enabled=1 AND remaining>0 AND expires_at>SYSUTCDATETIME()')['n']
            if existing: raise ValueError('eligible_real_prizes_exist_skip_entire_suite')
            now = seed(c, run_id, ids)
            svc = Service(Pinned(c))
            a, b, vendor = ({'id':ids[n], 'role':'vendor' if n=='vendor' else 'consumer'} for n in ('consumer-a','consumer-b','vendor'))
            stock = lambda: one(c, 'SELECT available_quantity AS n FROM dbo.products WHERE id=:id', id=ids['product'])['n']
            r = svc.reserve(a, 'qa-reserve-cancel', ids['product'], 1)
            expected_http(lambda:svc.transition(b,'qa-cross-cancel',r['id'],'cancelled'),404,'cross_account_cancel_rejected',results)
            first = svc.transition(a,'qa-cancel-repeat',r['id'],'cancelled')
            repeat = svc.transition(a,'qa-cancel-repeat',r['id'],'cancelled')
            check(first==repeat and stock()==1,'cancel_replay_returns_stock_once',results)
            expected_http(lambda:svc.transition(a,'qa-cancel-new-key',r['id'],'cancelled'),409,'second_cancel_new_key_rejected',results)
            r = svc.reserve(a,'qa-reserve-pickup',ids['product'],1)
            expected_http(lambda:svc.transition(vendor,'qa-pickup-wrong',r['id'],'completed','WRONG'),400,'wrong_pickup_code_rejected',results)
            first = svc.transition(vendor,'qa-pickup-repeat',r['id'],'completed',r['pickup_code'])
            events = count(c,'exp_events',a['id'])
            repeat = svc.transition(vendor,'qa-pickup-repeat',r['id'],'completed',r['pickup_code'])
            check(first==repeat and stock()==0 and count(c,'exp_events',a['id'])==events,'pickup_replay_no_duplicate_exp_or_stock',results)
            expected_http(lambda:svc.transition(vendor,'qa-pickup-new-key',r['id'],'completed',r['pickup_code']),409,'second_pickup_new_key_rejected',results)
            # Fresh past-expiry fixture INSERT, never UPDATE a real expiry/EXP rule.
            execute(c, "INSERT INTO dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,'waiting',1,:s,:h,:expiry)", id=ids['expiry'],u=b['id'],p=ids['product'],s=dump({'name':'QA expiry','sale_price_minor':50}),h=digest(secrets.token_hex(6)),expiry=now-timedelta(seconds=1))
            first=svc.transition(b,'qa-expiry-repeat',ids['expiry'],'cancelled')
            repeat=svc.transition(b,'qa-expiry-repeat',ids['expiry'],'cancelled')
            check(first==repeat and first['state']=='expired' and stock()==1,'expiry_transition_returns_stock_once',results)
            expected_http(lambda:svc.transition(b,'qa-expiry-new-key',ids['expiry'],'cancelled'),409,'second_expiry_new_key_rejected',results)
            execute(c, "INSERT INTO dbo.prizes(id,name,kind,weight,remaining,enabled,expires_at,terms,discount_percent) VALUES(:id,'QA fixture','coupon',1,1,1,:end,'Synthetic fixture only; no redemption',20)", id=ids['prize'],end=now+timedelta(minutes=10))
            execute(c, 'INSERT INTO dbo.spin_grants(id,user_id,source_key,remaining,expires_at) VALUES(:id,:u,:source,1,:end)', id=ids['grant'],u=a['id'],source='foodsave-qa:'+run_id.hex,end=now+timedelta(minutes=10))
            first=svc.draw(a,'qa-draw-repeat');repeat=svc.draw(a,'qa-draw-repeat')
            remaining=one(c,'SELECT remaining FROM dbo.spin_grants WHERE id=:id',id=ids['grant'])['remaining']
            prize_remaining=one(c,'SELECT remaining FROM dbo.prizes WHERE id=:id',id=ids['prize'])['remaining']
            check(first==repeat and remaining==0 and prize_remaining==0 and count(c,'draws',a['id'])==1 and count(c,'coupons',a['id'])==1,'draw_same_key_deducts_once',results)
            # Positive ownership-chain EXECUTE and negative runtime boundary.
            execute(c,'EXEC dbo.submit_deletion_request @request_id=:r,@user_id=:u',r=ids['request'],u=a['id'])
            check(one(c,'SELECT state FROM dbo.deletion_requests WHERE id=:id',id=ids['request'])['state']=='requested','restricted_procedure_insert_succeeds',results)
            rejected_sql(c,'EXEC dbo.submit_deletion_request @request_id=:r,@user_id=:u,@approved_for_erasure=1',{'r':str(uuid4()),'u':b['id']},[8144],'procedure_rejects_owner_parameter',results)
            rejected_sql(c,'SELECT approved_for_erasure FROM dbo.deletion_requests WHERE id=:id',{'id':ids['request']},[229,230],'owner_field_read_denied',results)
            rejected_sql(c,'UPDATE dbo.deletion_requests SET approved_for_erasure=1 WHERE id=:id',{'id':ids['request']},[229,230],'owner_approval_write_denied',results)
            rejected_sql(c,'INSERT INTO dbo.deletion_requests(id,user_id) VALUES(:r,:u)',{'r':str(uuid4()),'u':b['id']},[229,230],'base_insert_denied',results)
        finally:
            tx.rollback()  # Even negative permissions/procedure errors never commit.
    with database.connect() as c:
        check(one(c,'SELECT COUNT(*) AS n FROM dbo.users WHERE id IN (:a,:b,:v)',a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'])['n']==0,'fixture_accounts_rolled_back',results)
    return results


def concurrent_suite(database, run_id, ids, manifest):
    from foodsave.db import one
    from foodsave.service import Service
    from fastapi import HTTPException
    results=[]
    # Persist recovery identifiers BEFORE committing. Never store credentials.
    # Caller approval required: this suite intentionally leaves its fixtures for owner cleanup.
    with open(manifest,'x',encoding='utf-8') as f:
        os.chmod(manifest,0o600)
        json.dump({'format':1,'run_id':str(run_id),'ids':ids,'scope':'committed_concurrency_fixture'},f)
    with database.begin() as c:
        preflight(c);seed(c,run_id,ids)
    barrier=threading.Barrier(2);sessions=[]
    wrapper=Concurrent(database,barrier,sessions)
    def reserve(name):
        try:
            Service(wrapper).reserve({'id':ids[name],'role':'consumer'},'qa-concurrent-stock',ids['product'],1)
            return 201
        except HTTPException as e: return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(reserve,'consumer-a');b=pool.submit(reserve,'consumer-b')
        statuses=sorted([a.result(timeout=40),b.result(timeout=40)])
    check(len(sessions)==2 and len(set(sessions))==2,'two_distinct_sql_connections',results)
    check(statuses==[201,409],'last_item_exactly_one_success',results)
    with database.connect() as c:
        stock=one(c,'SELECT available_quantity AS n FROM dbo.products WHERE id=:id',id=ids['product'])['n']
        orders=one(c,'SELECT COUNT(*) AS n FROM dbo.reservations WHERE product_id=:id',id=ids['product'])['n']
        check(stock==0 and orders==1,'stock_zero_and_one_committed_order',results)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['plan','rollback','concurrency'],default='plan')
    parser.add_argument('--run-id',type=UUID)
    parser.add_argument('--approved-quiet-window',action='store_true')
    parser.add_argument('--approved-committed-fixtures',action='store_true')
    parser.add_argument('--manifest',type=Path)
    args=parser.parse_args()
    if args.mode=='plan':
        print(json.dumps({'mode':'plan','db_access':False,'rollback_accounts':3,'concurrency_accounts':3,'admin_accounts':0,'cleanup':'owner approval required; never automatic','conditions':['restricted existing runtime identity','foodsave migrations001-005','approved quiet window','zero eligible real prizes for rollback suite','concurrency requires approved committed fixtures and private recovery manifest']},ensure_ascii=False));return
    if not args.run_id or not args.approved_quiet_window: parser.error('Explicit run UUID and approved quiet window required')
    if args.mode=='concurrency' and (not args.approved_committed_fixtures or not args.manifest): parser.error('Committed-fixture approval and recovery manifest required')
    from foodsave.db import engine
    database=engine()
    try:
        results=rollback_suite(database,args.run_id,identifiers(args.run_id)) if args.mode=='rollback' else concurrent_suite(database,args.run_id,identifiers(args.run_id),args.manifest)
        print(json.dumps({'status':'passed','mode':args.mode,'assertion_count':len(results),'assertions':results,'committed_fixtures_remaining':args.mode=='concurrency'},ensure_ascii=False))
    except Exception as error:
        # No SQL text, token, password, email, pickup/coupon code or exception dump.
        print(json.dumps({'status':'failed','mode':args.mode,'error_class':type(error).__name__,'details':'withheld; investigate privately','committed_fixtures_may_remain':args.mode=='concurrency'}))
        raise SystemExit(1)
    finally: database.dispose()


if __name__=='__main__':main()
