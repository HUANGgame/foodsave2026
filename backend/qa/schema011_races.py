"""Ten controlled, real two-connection schema011 races. One approved batch per invocation.
No HTTP, owner cleanup, new grants, DDL, real accounts or public-CI execution.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import threading
from unittest.mock import patch
from uuid import UUID
from qa.schema011_fixture import CASES, expected_requests, key, make_manifest, preflight, read_private, seed, write_private


class RaceFailure(Exception):
    pass


def require(value, name):
    if not value:
        raise RaceFailure(name)


class Connections:
    """Leader completes its real operation but retains transaction locks. Follower
    proves the same store applock is busy on a distinct SPID, then runs its real
    operation while the leader commits. No timing sleeps / fake DB / SQL retry.
    """
    def __init__(self, database, ids):
        self.database, self.ids = database, ids
        self.ready, self.contended = threading.Event(), threading.Event()
        self.spids = {}
        self.local = threading.local()

    @contextmanager
    def begin(self):
        from foodsave.db import execute, one
        side = self.local.side
        with self.database.begin() as c:
            execute(c, 'SET LOCK_TIMEOUT 10000')
            self.spids[side] = one(c, 'SELECT @@SPID AS n')['n']
            if side == 'follower':
                require(self.ready.wait(15), 'leader_did_not_reach_commit_gate')
                probe = one(c, "DECLARE @r int; EXEC @r=sp_getapplock @Resource=:resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=0; SELECT @r AS result", resource='foodsave:store-mode:'+self.ids['store'])
                require(probe['result'] == -1, 'follower_must_observe_real_lock_contention')
                self.contended.set()
            yield c
            if side == 'leader':
                self.ready.set()
                require(self.contended.wait(15), 'follower_did_not_probe_lock')

    def identity(self):
        # Only replace the random ID allocator in this isolated harness process.
        # SQL, transactions, business methods, clocks and authorization are real.
        try:
            return next(self.local.identities)
        except StopIteration:
            raise RaceFailure('unexpected_id_allocation') from None


def action(wrapper, ids, case, operation, password):
    from foodsave.admin import AdminService
    from foodsave.db import one
    service = AdminService(wrapper)
    consumer = {'id':ids['consumer-a'],'role':'consumer'}
    vendor = {'id':ids['vendor'],'role':'vendor'}
    if operation == 'reserve':
        return service.reserve({'id':ids['consumer-b'],'role':'consumer'},key(ids,'reserve'),ids['product'],1)
    if operation == 'mode':
        return service.set_store_mode(vendor,key(ids,'mode'),ids['store'],'information')
    if operation == 'loss':
        return service.report_stock_loss(vendor,key(ids,'loss'),ids['product'],dict(expected_revision=1,expected_pending=int(not case.startswith('reserve-')),actual_available=0))
    if operation == 'cancel':
        return service.transition(consumer,key(ids,'cancel'),ids['order-seed'],'cancelled')
    if operation == 'expiry':
        with wrapper.begin() as c:
            return dict(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=ids['order-seed']))
    if operation == 'close':
        return service.request_deletion(vendor,password)
    raise RaceFailure('unknown_operation')


EXPECTED = {
    'reserve-mode-left': (201,409,0,'waiting',None),
    'reserve-mode-right': (409,200,1,None,None),
    'reserve-loss-left': (201,409,0,'waiting',None),
    'reserve-loss-right': (409,200,0,None,None),
    'cancel-loss-left': (200,409,1,'cancelled',None),
    'cancel-loss-right': (200,200,0,None,'vendor_out_of_stock'),
    'expiry-loss-left': (200,409,1,None,'expired'),
    'expiry-loss-right': (200,200,0,None,'vendor_out_of_stock'),
    'reserve-close-left': (201,200,None,None,'vendor_closed'),
    'reserve-close-right': (404,200,None,None,None),
}


def verify(c, ids, case, results):
    from foodsave.db import one, rows
    left,right,stock,state,reason = EXPECTED[case]
    require([r['status'] for r in results] == [left,right], 'exact_operation_statuses')
    orders = rows(c,'SELECT id,state,user_id,quantity FROM dbo.reservations WHERE product_id=:p OR id IN (:o,:n)',p=ids['product'],o=ids['order-seed'],n=ids['order-new'])
    require(len(orders)==int(state is not None), 'exact_remaining_orders')
    if state:
        rid, user = (ids['order-new'],ids['consumer-b']) if case.startswith('reserve-') else (ids['order-seed'],ids['consumer-a'])
        require(dict(orders[0])==dict(id=rid,state=state,user_id=user,quantity=1), 'remaining_order_identity_state')
    product = one(c,'SELECT available_quantity,revision FROM dbo.products WHERE id=:p',p=ids['product'])
    require((product is None) if stock is None else product is not None and product['available_quantity']==stock and product['revision']==(1 if case=='reserve-mode-right' else 2), 'stock_and_revision')
    store = one(c,'SELECT service_mode FROM dbo.stores WHERE id=:s',s=ids['store'])
    require((store is None) if stock is None else store is not None and store['service_mode']==('information' if case=='reserve-mode-right' else 'reservation'), 'store_state')
    terminals = rows(c,'SELECT reservation_id,user_id,vendor_id,reason,released_quantity FROM dbo.reservation_terminals WHERE user_id IN (:a,:b) OR vendor_id=:v',a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'])
    require(len(terminals)==int(reason is not None), 'terminal_count')
    if reason:
        rid, user = (ids['order-new'],ids['consumer-b']) if case.startswith('reserve-') else (ids['order-seed'],ids['consumer-a'])
        require(dict(terminals[0])==dict(reservation_id=rid,user_id=user,vendor_id=ids['vendor'],reason=reason,released_quantity=int(reason=='expired')), 'terminal_release_once')
    notices = rows(c,'SELECT user_id,event_key,kind FROM dbo.notifications WHERE user_id IN (:a,:b,:v)',a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'])
    require(len(notices)==int(reason is not None), 'notification_count')
    if reason:
        require(dict(notices[0])==dict(user_id=user,event_key=reason+':'+(ids['vendor'] if reason=='vendor_closed' else rid),kind=reason), 'notification_recipient_and_key')
    require(one(c,'SELECT COUNT(*) AS n FROM dbo.exp_events WHERE user_id IN (:a,:b,:v)',a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'])['n']==0, 'no_exp_or_penalty')
    receipts = rows(c,'SELECT user_id,operation,request_key,fingerprint FROM dbo.request_results WHERE user_id IN (:a,:b,:v)',a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'])
    allowed = expected_requests(case,ids)
    expected_count = sum(r['status']<300 and op not in ('expiry','close') for r,op in zip(results,case.rsplit('-',1)[0].split('-')))
    require(len(receipts)==expected_count and all(allowed.get((r['user_id'],r['operation'],r['request_key']))==r['fingerprint'] for r in receipts), 'exact_request_receipts')
    if case=='expiry-loss-left':
        require(results[0]['outcome']=='expired', 'expiry_wins')
    if case=='expiry-loss-right':
        require(results[0]['outcome']=='absent', 'expiry_after_loss_no_return')
    if case=='cancel-loss-right':
        require(results[0]['terminal_reason']=='vendor_out_of_stock', 'late_cancel_no_return')
    if case.startswith('reserve-close'):
        require(not one(c,'SELECT active FROM dbo.users WHERE id=:v',v=ids['vendor'])['active'], 'closure_disables_only_vendor')
        require(one(c,'SELECT id FROM dbo.deletion_requests WHERE user_id=:v',v=ids['vendor'])['id']==ids['deletion'], 'exact_deletion_request')
    return ['two_distinct_sql_connections','real_store_lock_contention','exact_operation_statuses','exact_remaining_orders','stock_and_revision','store_state','terminal_release_once','notification_recipient_and_key','no_exp_or_penalty','exact_request_receipts']


def run_case(database, manifest, case, manifest_path):
    from fastapi import HTTPException
    from foodsave.db import execute, one
    ids = manifest['batches'][case]
    password = secrets.token_urlsafe(32)
    # A durable exclusive start marker prevents retrying a cleaned or ambiguous
    # batch. Preserve this file together with the immutable recovery manifest.
    write_private(Path(str(manifest_path)+'.'+case+'.started'), {'case':case,'run_id':manifest['run_id']})
    # Session-owned guard is QA-run-specific and does not alter business locking.
    with database.connect() as guard:
        preflight(guard)
        resource = 'foodsave:qa011:'+manifest['run_id']
        lock = one(guard,"DECLARE @r int; EXEC @r=sp_getapplock @Resource=:r,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @r AS result",r=resource)
        require(lock['result']>=0,'another_batch_running')
        try:
            with database.begin() as c:
                preflight(c)
                for other in manifest['batches'].values():
                    require(one(c,'SELECT COUNT(*) AS n FROM dbo.users WHERE id IN (:a,:b,:v)',a=other['consumer-a'],b=other['consumer-b'],v=other['vendor'])['n']==0,'previous_batch_must_be_cleaned')
                seed(c,ids,case,password)
            wrapper = Connections(database,ids)
            operations = case.rsplit('-',1)[0].split('-')
            leader_index = 0 if case.endswith('-left') else 1
            def worker(index):
                wrapper.local.side = 'leader' if index==leader_index else 'follower'
                op = operations[index]
                wrapper.local.identities = iter([ids['order-new']] if op=='reserve' else [ids['deletion'],ids['audit']] if op=='close' else [])
                try:
                    result = action(wrapper,ids,case,op,password)
                    return {'status':201 if op=='reserve' else 200,'outcome':result.get('outcome'),'terminal_reason':result.get('terminal_reason')}
                except HTTPException as error:
                    return {'status':error.status_code}
            with patch('foodsave.service.uid',wrapper.identity):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(worker,index) for index in range(2)]
                    results = [future.result(timeout=45) for future in futures]
            require(len(set(wrapper.spids.values()))==2,'two_distinct_sql_connections')
            with database.connect() as c:
                checks = verify(c,ids,case,results)
            return {'status':'passed','case':case,'assertions':checks,'committed_fixtures_remaining':True,'cleanup_required':True}
        finally:
            execute(guard,"EXEC sp_releaseapplock @Resource=:r,@LockOwner='Session'",r=resource)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('plan','create-manifest','execute'),default='plan')
    parser.add_argument('--run-id',type=UUID)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--case',choices=CASES)
    parser.add_argument('--approved-quiet-window',action='store_true')
    parser.add_argument('--approved-committed-fixtures',action='store_true')
    args = parser.parse_args()
    if args.mode=='plan':
        print(json.dumps({'mode':'plan','db_access':False,'cases':CASES,'per_batch':{'users':3,'stores':1,'products':1,'orders_max':2},'cleanup':'separate owner schema011 preview/apply after EVERY batch','not_covered':['HTTP','Android','uncontrolled scheduling','notification injection']}));return
    if not args.manifest:
        parser.error('Private manifest required')
    database = None
    try:
        if args.mode=='create-manifest':
            if not args.run_id:
                parser.error('Fresh UUID4 required')
            write_private(args.manifest,make_manifest(args.run_id))
            print(json.dumps({'mode':'manifest_created','db_access':False,'cases':10}));return
        if not args.case or not args.approved_quiet_window or not args.approved_committed_fixtures:
            parser.error('Exact case, approved quiet window and committed fixtures required')
        manifest = read_private(args.manifest)
        from foodsave.db import engine
        database = engine()
        print(json.dumps(run_case(database,manifest,args.case,args.manifest),sort_keys=True))
    except Exception as error:
        print(json.dumps({'status':'failed','error_class':type(error).__name__,'failed_assertion':str(error) if isinstance(error,RaceFailure) else None,'committed_fixtures_may_remain':args.mode=='execute','details':'do not rerun; preserve private manifest and start marker; inspect then owner preview'}))
        raise SystemExit(1)
    finally:
        if database is not None:
            database.dispose()

if __name__=='__main__':
    main()
