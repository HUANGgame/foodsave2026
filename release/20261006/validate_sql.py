"""Plan by default. Existing empty validation DB only; ALL changes rolled back.
No resource creation, COMMIT, grants, production access, mail or secret logging.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, sys
from contextlib import contextmanager
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
DATABASE='foodsave-validation-20261006'
SOURCE='e5290df728a85a2b50b228a3d8ef1b601971f9f0'
MANIFEST=Path(__file__).with_name('source-hashes.json')
class CheckFailed(Exception):pass
def check(ok,name):
    if not ok:raise CheckFailed(name)
def validate_connection(connection):
    # Parse values, not substrings: semicolons inside {braces} belong to the
    # value; }} is an escaped closing brace. Refuse ambiguous duplicate aliases.
    check(isinstance(connection,str) and bool(connection),'validation_connection_required')
    options={};i=0
    while i<len(connection):
        while i<len(connection) and (connection[i].isspace() or connection[i]==';'):i+=1
        if i==len(connection):break
        start=i
        while i<len(connection) and connection[i] not in '=;':i+=1
        check(i<len(connection) and connection[i]=='=','connection_key_syntax')
        key=connection[start:i].strip().lower();i+=1
        while i<len(connection) and connection[i].isspace():i+=1
        value=''
        if i<len(connection) and connection[i]=='{':
            i+=1;closed=False
            while i<len(connection):
                if connection[i]=='}':
                    if i+1<len(connection) and connection[i+1]=='}':value+='}';i+=2;continue
                    closed=True;i+=1;break
                value+=connection[i];i+=1
            check(closed,'connection_unclosed_brace')
            while i<len(connection) and connection[i].isspace():i+=1
            check(i==len(connection) or connection[i]==';','connection_brace_suffix')
        else:
            start=i
            while i<len(connection) and connection[i]!=';':i+=1
            value=connection[start:i].strip()
            check('{' not in value and '}' not in value,'connection_unquoted_brace')
        check(key not in options,'connection_duplicate_key')
        check(key in {'driver','server','database','encrypt','trustservercertificate','authentication','uid','pwd','connection timeout'},'connection_unsupported_key')
        options[key]=value
        if i<len(connection):i+=1
    check(options.get('database')==DATABASE,'validation_catalog_only_before_connect')
    check(options.get('encrypt','').lower() in ('yes','mandatory'),'TLS_encrypt_required')
    check(options.get('trustservercertificate','').lower()=='no','TLS_certificate_verification_required')
    check(options.get('driver') in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'),'installed_SQL_Server_driver_required')
    check(bool(re.fullmatch(r'(?:tcp:)?[a-zA-Z0-9-]+\.database\.windows\.net(?:,1433)?',options.get('server',''))),'Azure_SQL_server_required')
    if 'connection timeout' in options:check(options['connection timeout'].isdigit() and 1<=int(options['connection timeout'])<=30,'bounded_connection_timeout')
    if 'authentication' in options:check(options['authentication'] in ('ActiveDirectoryInteractive','ActiveDirectoryIntegrated','ActiveDirectoryPassword','ActiveDirectoryServicePrincipal','ActiveDirectoryMsi','SqlPassword'),'supported_existing_authentication_required')
    return options

def sql_files():
    manifest=json.loads(MANIFEST.read_text());check(manifest['commit']==SOURCE,'source_commit')
    for name,digest in manifest['files'].items():
        check(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'source_hash:'+name)
    result=[]
    for p in sorted((ROOT/'backend/migrations').glob('*.sql')):
        sql=p.read_text();check(not re.search(r'^\s*GO(?:\s+\d+)?\s*(?:--.*)?$',sql,re.M|re.I),'no_GO:'+p.name)
        if p.name=='012_account_lifecycle.sql':
            old="IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;"
            check(sql.count(old)==1,'012_exact_guard');sql=sql.replace(old,"IF DB_NAME()<>N'foodsave-validation-20261006' THROW 51000,'Validation database required',1;")
        result.append((p.name,sql))
    check([n[:3] for n,s in result]==[f'{n:03}' for n in range(1,15)],'exact_migration_set')
    return result
class Pinned:
    def __init__(self,c):self.c=c
    @contextmanager
    def begin(self):yield self.c

def suite(c):
    from foodsave.db import execute,one,rows
    from foodsave.admin import AdminService
    from fastapi import HTTPException
    service=AdminService(Pinned(c));checks=[]
    def ok(value,name):check(value,name);checks.append(name)
    def denied(fn,status,name):
        try:fn()
        except HTTPException as e:ok(e.status_code==status,name)
        else:raise CheckFailed(name)
    owner={'id':str(uuid4()),'role':'consumer','is_vendor':True};customer={'id':str(uuid4()),'role':'consumer'}
    for u in [owner,customer]:execute(c,'INSERT dbo.users(id,email,password_hash,role) VALUES(:id,:email,:pw,:role)',id=u['id'],email=u['id']+'@example.invalid',pw='validation-only-not-a-login-hash',role=u['role'])
    draft=service.create_own_store(owner,str(uuid4()),dict(name='validation store',latitude=25,longitude=121));sid=draft['id']
    ok(draft['location_confirmed'] is False,'draft_unpublished')
    denied(lambda:service.create_own_store(owner,str(uuid4()),dict(name='duplicate',latitude=25,longitude=121)),409,'one_store_per_owner')
    body=dict(latitude=25,longitude=121,expected_revision=1,confirm='SAVE_LOCATION');key=str(uuid4())
    saved=service.save_store_location(owner,key,sid,body);ok(saved['location_revision']==2,'save_revision')
    ok(service.save_store_location(owner,key,sid,body)==saved,'same_key_same_result')
    denied(lambda:service.save_store_location(owner,str(uuid4()),sid,body),409,'stale_revision')
    denied(lambda:service.save_store_location({**customer,'is_vendor':True},str(uuid4()),sid,body),404,'cross_store_denied')
    service.set_store_mode(owner,str(uuid4()),sid,'reservation')
    products=[str(uuid4()) for _ in range(305)]
    for pid in products:execute(c,"INSERT dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline) VALUES(:id,:sid,'validation item','https://example.invalid/item',100,50,2,DATEADD(hour,1,SYSUTCDATETIME()))",id=pid,sid=sid)
    denied(lambda:service.reserve(owner,str(uuid4()),products[0],1),403,'self_reserve_denied')
    order=service.reserve(customer,str(uuid4()),products[0],1)
    snapshot=json.loads(one(c,'SELECT snapshot FROM dbo.reservations WHERE id=:id',id=order['id'])['snapshot'])
    ok(snapshot['location_revision']==2 and float(snapshot['latitude'])==25,'pickup_snapshot')
    move=dict(latitude=25.001,longitude=121,expected_revision=2,confirm='SAVE_LOCATION')
    denied(lambda:service.save_store_location(owner,str(uuid4()),sid,move),409,'waiting_blocks_move')
    execute(c,"UPDATE dbo.reservations SET state='expired' WHERE id=:id",id=order['id'])
    denied(lambda:service.save_store_location(owner,str(uuid4()),sid,move),409,'expired_unsettled_blocks_move')
    execute(c,"UPDATE dbo.reservations SET state='waiting' WHERE id=:id",id=order['id'])
    service.transition(customer,str(uuid4()),order['id'],'cancelled')
    ok(service.save_store_location(owner,str(uuid4()),sid,move)['location_revision']==3,'settled_allows_move')
    found=[];cursor=None;seen=set()
    while True:
        page=service.nearby_products(25,121,100,cursor,sid);found.extend(x['id'] for x in page['items']);cursor=page['next_cursor']
        if cursor is None:break
        ok(cursor not in seen,'new_cursor');seen.add(cursor)
    ok(set(found)==set(products) and len(found)==305,'real_TSQL_full_305_product_pagination')
    ok(any(x['id']==sid for x in service.nearby_stores(25,121,100)['items']),'near_store_included')
    ok(not service.nearby_products(0,0,100,None,sid)['items'],'far_store_excluded')
    loss=service.report_stock_loss(owner,str(uuid4()),products[1],dict(expected_revision=1,expected_pending=0,actual_available=0))
    ok(loss['cancelled_count']==0,'013_consumer_owner_stock_loss')
    ok(one(c,'EXEC dbo.close_vendor_business @vendor_id=:u',u=owner['id'])['outcome']=='deletion_required','013_close_requires_deletion')
    return checks

def run(files):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from sqlalchemy.pool import NullPool
    import pyodbc
    from foodsave.db import one,execute
    connection=os.environ.get('FOODSAVE_VALIDATION_ODBC_CONNECTION')
    options=validate_connection(connection)
    check(options['driver'] in pyodbc.drivers(),'selected_driver_installed')
    pyodbc.pooling=False
    engine=create_engine(URL.create('mssql+pyodbc',query={'odbc_connect':connection}),poolclass=NullPool,hide_parameters=True,connect_args={'timeout':15})
    checks=[];rollback_verified=False
    try:
        with engine.connect() as c:
            c.connection.driver_connection.timeout=30
            check(one(c,'SELECT DB_NAME() AS db')['db']==DATABASE,'validation_database_only')
            check(one(c,"SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS allowed")['allowed']==1,'existing_owner_control_required')
            check(one(c,'SELECT COUNT(*) AS n FROM sys.objects WHERE is_ms_shipped=0')['n']==0,'strict_empty_database_required')
            c.rollback() # Finish metadata-only preflight before explicit test transaction.
            tx=c.begin()
            try:
                c.exec_driver_sql('SET XACT_ABORT ON; SET ANSI_NULLS ON; SET QUOTED_IDENTIFIER ON; SET ANSI_PADDING ON; SET ANSI_WARNINGS ON; SET CONCAT_NULL_YIELDS_NULL ON; SET ARITHABORT ON; SET NUMERIC_ROUNDABORT OFF; SET LOCK_TIMEOUT 10000; IF @@TRANCOUNT=0 BEGIN TRANSACTION;')
                c.exec_driver_sql("DECLARE @r int; EXEC @r=sp_getapplock @Resource='foodsave:validation-migrate',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; IF @r<0 THROW 51000,'Migration lock unavailable',1;")
                c.exec_driver_sql('CREATE TABLE dbo.schema_migrations(version varchar(80) PRIMARY KEY,applied_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME())')
                for iteration in range(2):
                    applied=0
                    for name,sql in files:
                        if one(c,'SELECT version FROM dbo.schema_migrations WHERE version=:v',v=name):continue
                        c.exec_driver_sql(sql) # whole file, isolated batch; no prepended statements
                        execute(c,'INSERT dbo.schema_migrations(version) VALUES(:v)',v=name);applied+=1
                    check(applied==(14 if iteration==0 else 0),'migration_rerun_count');checks.append('migrations_applied:'+str(applied))
                index=one(c,"SELECT is_unique,is_disabled,is_hypothetical,type,filter_definition FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.stores') AND name='ux_stores_single_owner'")
                check(index and index['is_unique']==1 and index['is_disabled']==0 and index['is_hypothetical']==0 and index['type']==2,'006_index_properties')
                keys=list(c.exec_driver_sql("SELECT COL_NAME(object_id,column_id) FROM sys.index_columns WHERE object_id=OBJECT_ID('dbo.stores') AND index_id=(SELECT index_id FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.stores') AND name='ux_stores_single_owner') AND key_ordinal>0 ORDER BY key_ordinal").scalars())
                check(keys==['owner_id'] and re.sub(r'[\s\[\]()]','',index['filter_definition'] or '').lower()=='owner_idisnotnull','006_exact_index_shape');checks.append('006_exact_index_shape')
                check(one(c,"SELECT COUNT(*) AS n FROM sys.columns WHERE object_id=OBJECT_ID('dbo.stores') AND name IN ('location_revision','location_confirmed')")['n']==2,'014_columns')
                checks.extend(suite(c));check(one(c,'SELECT XACT_STATE() AS s')['s']==1,'transaction_committable_before_rollback')
            finally:tx.rollback()
        with engine.connect() as c:
            check(one(c,'SELECT DB_NAME() AS db')['db']==DATABASE,'verify_same_validation_database')
            check(one(c,'SELECT COUNT(*) AS n FROM sys.objects WHERE is_ms_shipped=0')['n']==0,'rollback_zero_objects')
            rollback_verified=True
        return dict(status='passed',checks=checks,rollback_verified=rollback_verified,runtime_permissions_tested=False,concurrency_tested=False)
    finally:engine.dispose()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-rollback',action='store_true');args=parser.parse_args()
    try:
        files=sql_files()
        if not args.run_rollback:
            print(json.dumps(dict(mode='plan',database=DATABASE,commit=SOURCE,connects=False,batches=[dict(name=n,adapted_sha256=hashlib.sha256(s.encode()).hexdigest()) for n,s in files],transactions='one outer rollback',not_covered=['runtime principal permissions','two-connection races','deployed HTTP','Android']),indent=2));return
        sys.path.insert(0,str(ROOT/'backend'));print(json.dumps(run(files)))
    except Exception as e:
        # Driver errors may contain server/credentials/SQL arguments. Never echo them.
        print(json.dumps(dict(status='failed',error_type=type(e).__name__,check=str(e) if isinstance(e,CheckFailed) else None,rollback_verified=False)));sys.exit(1)
if __name__=='__main__':main()
