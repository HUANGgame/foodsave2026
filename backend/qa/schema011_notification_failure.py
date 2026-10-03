"""Owner-only notification UNIQUE failure injection: two fresh outer rollbacks.
No commits, DDL, triggers or grants. Does NOT prove restricted-runtime permissions.
Closure de-duplicates notifications and is explicitly not covered by this method.
"""
import argparse
import json
import secrets
from uuid import UUID
from qa.schema011_fixture import make_manifest, preflight, seed
from qa.schema011_cleanup import SCOPES, FORBIDDEN, parameters


class InjectionFailure(Exception):
    pass


def suite(database, run):
    from foodsave.db import execute, one
    from sqlalchemy.exc import DBAPIError
    manifest = make_manifest(run)
    checks = []
    for kind,case in (('expired','expiry-loss-left'),('vendor_out_of_stock','cancel-loss-right')):
        ids = manifest['batches'][case]
        with database.connect() as c:
            tx = c.begin()
            try:
                preflight(c,owner=True)
                seed(c,ids,case,secrets.token_urlsafe(32))
                execute(c,"INSERT dbo.notifications(id,user_id,event_key,kind,body,related_vendor_id) VALUES(:id,:u,:k,:kind,N'Synthetic conflict only',:v)",id=ids['audit'],u=ids['consumer-a'],k=kind+':'+ids['order-seed'],kind=kind,v=ids['vendor'])
                try:
                    if kind=='expired':
                        one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=ids['order-seed'])
                    else:
                        one(c,'EXEC dbo.report_stock_loss @vendor_id=:v,@product_id=:p,@expected_revision=1,@expected_pending=1,@actual_available=0',v=ids['vendor'],p=ids['product'])
                except DBAPIError as error:
                    # Inspect driver code privately; NEVER emit the SQL/error text.
                    if not any(f'({code})' in str(error.orig) for code in (2601,2627)):
                        raise InjectionFailure('wrong_sql_failure') from None
                    if one(c,'SELECT XACT_STATE() AS n')['n'] != -1:
                        raise InjectionFailure('failed_transaction_not_doomed')
                    checks.append(kind+':unique_failure_requires_rollback')
                else:
                    raise InjectionFailure('notification_failure_not_injected')
            finally:
                if tx.is_active:
                    tx.rollback()
        with database.connect() as c:
            for table,predicate in {**SCOPES,**FORBIDDEN}.items():
                if one(c,f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {predicate}',**parameters(ids))['n']:
                    raise InjectionFailure('rollback_residual')
            checks.append(kind+':all_scoped_rows_rolled_back')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--approved-quiet-window',action='store_true')
    parser.add_argument('--run-id',type=UUID)
    parser.add_argument('--server')
    parser.add_argument('--database',choices=['foodsave'])
    parser.add_argument('--driver',choices=['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'])
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'plan','db_access':False,'commits':0,'ddl':False,'identity':'existing owner only','cases':['expired','vendor_out_of_stock'],'not_covered':['vendor_closed injection','runtime grant boundary','HTTP']}));return
    if not all((args.approved_quiet_window,args.run_id,args.server,args.database,args.driver)):
        parser.error('Fresh UUID4, quiet window and existing owner connection required')
    make_manifest(args.run_id)
    database = None
    try:
        from owner_migrate import owner_database
        database = owner_database(args.server,args.driver)
        checks = suite(database,args.run_id)
        print(json.dumps({'status':'passed','assertions':checks,'commits':0,'ddl':False,'scope':'owner-only rollback, not runtime permission acceptance'}))
    except Exception as error:
        print(json.dumps({'status':'failed','error_class':type(error).__name__,'failed_assertion':str(error) if isinstance(error,InjectionFailure) else None,'rollback_requested':True,'details':'withheld; investigate privately'}))
        raise SystemExit(1)
    finally:
        if database is not None:
            database.dispose()

if __name__=='__main__':
    main()
