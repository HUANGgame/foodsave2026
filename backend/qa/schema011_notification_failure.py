"""Owner-only notification UNIQUE failure injection: two fresh outer rollbacks.
No commits, DDL, triggers or grants. Does NOT prove restricted-runtime permissions.
Closure de-duplicates notifications and is explicitly not covered by this method.
"""
import argparse
import json
import secrets
from pathlib import Path
from qa.schema011_fixture import INJECTION_CASES, preflight, seed, read_private, write_private, validate_manifest
from qa.schema011_cleanup import SCOPES, FORBIDDEN, parameters


class InjectionFailure(Exception):
    pass


def verify_zero(database, ids):
    from foodsave.db import one
    problems = []
    with database.connect() as c:
        for table,predicate in {**SCOPES,**FORBIDDEN}.items():
            try:
                if one(c,f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {predicate}',**parameters(ids))['n']:
                    problems.append(table)
            except Exception:
                problems.append(table)
    if problems:
        raise InjectionFailure('rollback_residual_or_verification_failed')


def suite(database, manifest, case, manifest_path):
    from foodsave.db import execute, one
    validate_manifest(manifest)
    if case not in INJECTION_CASES:
        raise ValueError('approved_notification_case_required')
    ids = manifest['batches'][case]
    write_private(Path(str(manifest_path)+'.'+case+'.started'), {'case':case,'run_id':manifest['run_id']})
    kind = 'expired' if case=='notification-expiry' else 'vendor_out_of_stock'
    seed_case = 'expiry-loss-left' if kind=='expired' else 'cancel-loss-right'
    checks = []
    seed_attempted = False
    # The existing owner engine uses NullPool. This session guard survives outer
    # rollback and is held through the independent residual check; close releases it.
    with database.connect() as c:
        tx = c.begin()
        try:
            try:
                preflight(c,owner=True)
                gate = one(c, "DECLARE @r int; EXEC @r=sp_getapplock @Resource=:resource,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @r AS result", resource='foodsave:qa011:'+manifest['run_id'])
                if gate['result'] < 0:
                    raise InjectionFailure('another_batch_running')
                for other in manifest['batches'].values():
                    if one(c,'SELECT COUNT(*) AS n FROM dbo.users WHERE id IN (:a,:b,:v)',a=other['consumer-a'],b=other['consumer-b'],v=other['vendor'])['n']:
                        raise InjectionFailure('previous_batch_must_be_cleaned')
                seed_attempted = True
                seed(c,ids,seed_case,secrets.token_urlsafe(32))
                execute(c,"INSERT dbo.notifications(id,user_id,event_key,kind,body,related_vendor_id) VALUES(:id,:u,:k,:kind,N'Synthetic conflict only',:v)",id=ids['audit'],u=ids['consumer-a'],k=kind+':'+ids['order-seed'],kind=kind,v=ids['vendor'])
                statement = ('EXEC dbo.expire_reservation @reservation_id=:id;' if kind=='expired' else
                             'EXEC dbo.report_stock_loss @vendor_id=:v,@product_id=:p,@expected_revision=1,@expected_pending=1,@actual_available=0;')
                # Capture diagnostics before rollback, then roll back INSIDE
                # CATCH so a doomed transaction cannot escape the batch (3998).
                result = one(c, "BEGIN TRY " + statement +
                             " SELECT 0 AS error_number,XACT_STATE() AS xact_state,@@TRANCOUNT AS transaction_count; END TRY "
                             "BEGIN CATCH DECLARE @qa_error int=ERROR_NUMBER(),@qa_state int=XACT_STATE(),@qa_count int=@@TRANCOUNT; "
                             "IF XACT_STATE()<>0 ROLLBACK TRANSACTION; "
                             "SELECT @qa_error AS error_number,@qa_state AS xact_state,@qa_count AS transaction_count; END CATCH",
                             id=ids['order-seed'],v=ids['vendor'],p=ids['product'])
                if not result or result.get('error_number') not in (2601,2627):
                    raise InjectionFailure('expected_notification_unique_failure_not_observed')
                if result['xact_state'] != -1 or result['transaction_count'] < 1:
                    raise InjectionFailure('caught_transaction_not_doomed')
                checks.append(kind+':unique_failure_captured_in_same_sql_batch')
            finally:
                if tx.is_active:
                    tx.rollback()
        finally:
            # Unexpected SQL/diagnostics/seed errors STILL require all zero checks.
            if seed_attempted:
                verify_zero(database,ids)
                checks.append(kind+':all_scoped_rows_rolled_back')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--approved-quiet-window',action='store_true')
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--case',choices=INJECTION_CASES)
    parser.add_argument('--server')
    parser.add_argument('--database',choices=['foodsave'])
    parser.add_argument('--driver',choices=['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'])
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'plan','db_access':False,'commits':0,'ddl':False,'identity':'existing owner only','cases':INJECTION_CASES,'shared_total_batch_limit':10,'not_covered':['vendor_closed injection','runtime grant boundary','HTTP']}));return
    if not all((args.approved_quiet_window,args.manifest,args.case,args.server,args.database,args.driver)):
        parser.error('Shared private manifest, one approved case, quiet window and existing owner connection required')
    database = None
    try:
        manifest = read_private(args.manifest)
        from owner_migrate import owner_database
        database = owner_database(args.server,args.driver)
        checks = suite(database,manifest,args.case,args.manifest)
        print(json.dumps({'status':'passed','assertions':checks,'commits':0,'ddl':False,'scope':'owner-only rollback, not runtime permission acceptance'}))
    except Exception as error:
        print(json.dumps({'status':'failed','error_class':type(error).__name__,'failed_assertion':str(error) if isinstance(error,InjectionFailure) else None,'rollback_requested':True,'details':'withheld; investigate privately'}))
        raise SystemExit(1)
    finally:
        if database is not None:
            database.dispose()

if __name__=='__main__':
    main()
