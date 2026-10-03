"""Offline safety tests only; never evidence of successful T-SQL execution."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
import pytest
from qa import schema011_cleanup as cleanup
from qa.schema011_fixture import CASES, RACE_CASES, INJECTION_CASES, NAMES, email, make_manifest, marker, read_private, validate_manifest, write_private


def fixture(case='reserve-mode-left'):
    manifest=make_manifest(uuid4()); ids=manifest['batches'][case]
    data={table:[] for table in cleanup.SCOPES}
    data['users']=[dict(id=ids[n],email=email(ids,n),role='vendor' if n=='vendor' else 'consumer',active=True) for n in NAMES[:3]]
    data['stores']=[dict(id=ids['store'],owner_id=ids['vendor'],name=marker(ids),latitude=0,longitude=0,service_mode='reservation')]
    data['products']=[dict(id=ids['product'],store_id=ids['store'],name=marker(ids),photo_url='https://images.example.invalid/qa.png',original_price_minor=100,sale_price_minor=50,active=True,available_quantity=1,revision=1)]
    return manifest,ids,data


def test_manifest_exact_ten_distinct_bounded_batches():
    value=make_manifest(uuid4())
    assert validate_manifest(value)==value
    assert len(value['batches'])==10
    assert len(RACE_CASES)==8 and len(INJECTION_CASES)==2
    all_ids=[i for batch in value['batches'].values() for i in batch.values()]
    assert len(set(all_ids))==90
    for mutation in ('id','case','scope','extra'):
        bad=deepcopy(value)
        if mutation=='id':bad['batches'][CASES[0]]['product']=str(uuid4())
        elif mutation=='case':del bad['batches'][CASES[0]]
        elif mutation=='scope':bad['scope']='legacy005'
        else:bad['unbounded']=True
        with pytest.raises(ValueError):validate_manifest(bad)


def test_manifest_private_durable_exclusive_and_symlink_rejection(tmp_path):
    tmp_path.chmod(0o700); path=tmp_path/'manifest.json';value=make_manifest(uuid4())
    write_private(path,value)
    assert path.stat().st_mode & 0o777==0o600
    assert read_private(path)==value
    with pytest.raises(FileExistsError):write_private(path,value)
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(OSError):read_private(link)
    path.chmod(0o644)
    with pytest.raises(ValueError):read_private(path)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):write_private(tmp_path/'other',value)


@pytest.mark.parametrize('case',RACE_CASES)
def test_cleanup_accepts_seed_or_bounded_partial_batch(case):
    _,ids,data=fixture(case)
    assert cleanup.validate_rows(case,ids,data)['users']==3


@pytest.mark.parametrize('target',['users','stores','products','reservations','reservation_terminals','notifications','request_results','deletion_requests','audit_logs'])
def test_cleanup_rejects_foreign_reference_in_every_cleaned_table(target):
    _,ids,data=fixture()
    # A real / unrelated reference is not an excuse to expand the cleanup scope.
    row=dict(id=str(uuid4()),user_id=str(uuid4()),owner_id=str(uuid4()),vendor_id=ids['vendor'],product_id=ids['product'],reservation_id=ids['order-new'],actor_id=str(uuid4()),target_id=ids['store'])
    data[target].append(row)
    with pytest.raises((ValueError,KeyError)):
        cleanup.validate_rows(CASES[0],ids,data)


def test_cleanup_validates_terminal_notice_pair_and_foreign_user():
    case='cancel-loss-right';_,ids,data=fixture(case)
    data['products'][0].update(available_quantity=0,revision=2)
    data['reservation_terminals']=[dict(reservation_id=ids['order-seed'],user_id=ids['consumer-a'],vendor_id=ids['vendor'],reason='vendor_out_of_stock',previous_state='waiting',released_quantity=0)]
    data['notifications']=[dict(id=str(uuid4()),user_id=ids['consumer-a'],event_key='vendor_out_of_stock:'+ids['order-seed'],kind='vendor_out_of_stock',related_vendor_id=ids['vendor'],read_at=None)]
    cleanup.validate_rows(case,ids,data)
    data['notifications'][0]['user_id']=str(uuid4())
    with pytest.raises(ValueError):cleanup.validate_rows(case,ids,data)


def test_cleanup_rejects_unapproved_closure():
    case=RACE_CASES[0];_,ids,data=fixture(case)
    data['users'][2]['active']=False
    with pytest.raises(ValueError):cleanup.validate_rows(case,ids,data)
    assert not any('close' in case for case in CASES)


class Transaction:
    is_active=True
    committed=False
    def rollback(self):self.is_active=False
    def commit(self):self.committed=True;self.is_active=False
class Connection:
    def __init__(self):self.tx=Transaction()
    def execution_options(self,**kwargs):assert kwargs=={'isolation_level':'SERIALIZABLE'};return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def begin(self):return self.tx
class Database:
    def __init__(self):self.c=Connection()
    def connect(self):return self.c


def test_preview_stale_digest_and_validation_failures_never_delete(monkeypatch):
    manifest,ids,data=fixture();counts=cleanup.validate_rows(CASES[0],ids,data)
    monkeypatch.setattr(cleanup,'inspect',lambda *args:(data,counts,'reviewed'))
    import foodsave.db as db
    monkeypatch.setattr(db,'execute',lambda *a,**k:pytest.fail('no mutation permitted'))
    database=Database()
    assert cleanup.cleanup(database,manifest,CASES[0])['committed'] is False
    assert not database.c.tx.is_active
    database=Database()
    with pytest.raises(ValueError,match='preview_changed'):
        cleanup.cleanup(database,manifest,CASES[0],'stale')
    assert not database.c.tx.is_active and not database.c.tx.committed
    def fail(*args):raise ValueError('unexpected_reference_stop')
    monkeypatch.setattr(cleanup,'inspect',fail)
    database=Database()
    with pytest.raises(ValueError):cleanup.cleanup(database,manifest,CASES[0],'reviewed')
    assert not database.c.tx.is_active and not database.c.tx.committed


def test_apply_exact_keys_only_and_failure_rolls_back(monkeypatch):
    manifest,ids,data=fixture();counts=cleanup.validate_rows(CASES[0],ids,data)
    monkeypatch.setattr(cleanup,'inspect',lambda *args:(data,counts,'reviewed'))
    import foodsave.db as db
    calls=[]
    class Result:rowcount=1
    def execute(c,sql,**params):
        assert ' WHERE id=:id' in sql and set(params)=={'id'}
        assert params['id'] in ids.values()
        calls.append(sql);return Result()
    monkeypatch.setattr(db,'execute',execute)
    monkeypatch.setattr(db,'one',lambda *a,**k:{'n':0})
    database=Database()
    assert cleanup.cleanup(database,manifest,CASES[0],'reviewed')['remaining']==0
    assert database.c.tx.committed and len(calls)==5
    def error(*args,**kwargs):raise RuntimeError('simulated interrupted deletion')
    monkeypatch.setattr(db,'execute',error)
    database=Database()
    with pytest.raises(RuntimeError):cleanup.cleanup(database,manifest,CASES[0],'reviewed')
    assert not database.c.tx.is_active and not database.c.tx.committed


def test_request_key_or_fingerprint_substitution_rejected():
    from qa.schema011_fixture import expected_requests
    manifest,ids,data=fixture()
    identity,fingerprint=next(iter(expected_requests(CASES[0],ids).items()))
    data['request_results']=[dict(user_id=identity[0],operation=identity[1],request_key=identity[2],fingerprint=fingerprint,response=json.dumps({'id':ids['order-new']}))]
    cleanup.validate_rows(CASES[0],ids,data)
    for field in ('user_id','request_key','fingerprint'):
        changed=deepcopy(data);changed['request_results'][0][field]='substituted'
        with pytest.raises(ValueError):cleanup.validate_rows(CASES[0],ids,changed)


def test_no_ddl_grants_or_http_in_new_qa_scripts():
    import ast
    base=Path(__file__).parents[1]/'qa'
    for name in ('schema011_fixture.py','schema011_races.py','schema011_cleanup.py','schema011_notification_failure.py'):
        tree=ast.parse((base/name).read_text())
        strings=[n.value.upper().strip() for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        assert not any(s.startswith(('GRANT ','DENY ','REVOKE ','CREATE TRIGGER','ALTER ','DROP ')) for s in strings)
    source=(base/'schema011_notification_failure.py').read_text()
    assert '.commit(' not in source


def test_notification_injection_plan_no_database(monkeypatch,capsys):
    from qa import schema011_notification_failure as failure
    monkeypatch.setattr('sys.argv',['qa'])
    failure.main()
    assert json.loads(capsys.readouterr().out)['commits']==0


def test_runtime_notification_projection_respects_column_grants():
    source=(Path(__file__).parents[1]/'qa/schema011_races.py').read_text()
    query=next(line for line in source.splitlines() if 'FROM dbo.notifications' in line)
    assert 'related_vendor_id' not in query and 'SELECT *' not in query


def test_actual_worker_gate_requires_distinct_connections_and_busy_probe(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from qa.schema011_races import Connections
    import foodsave.db as db
    _,ids,_=fixture()
    committed=[]
    class FakeDatabase:
        counter=0
        @contextmanager
        def begin(self):
            self.counter+=1;connection=self.counter
            yield connection
            committed.append(connection)
    monkeypatch.setattr(db,'execute',lambda *args,**kwargs:None)
    def one(c,sql,**kwargs):
        return {'n':c} if '@@SPID' in sql else {'result':-1}
    monkeypatch.setattr(db,'one',one)
    wrapper=Connections(FakeDatabase(),ids)
    def worker(side):
        wrapper.local.side=side
        with wrapper.begin():pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,side) for side in ('leader','follower')]
        for future in futures:future.result(timeout=2)
    assert len(set(wrapper.spids.values()))==2 and len(committed)==2 and wrapper.contended.is_set()
    wrapper=Connections(FakeDatabase(),ids);wrapper.local.side='follower';wrapper.ready.set()
    monkeypatch.setattr(db,'one',lambda c,sql,**k:{'n':c} if '@@SPID' in sql else {'result':0})
    with pytest.raises(Exception,match='real_lock_contention'):
        with wrapper.begin():pytest.fail('action must not run without contention')


@pytest.mark.parametrize('diagnostic',[
    {'error_number':2627,'xact_state':-1,'transaction_count':1},
    {'error_number':1205,'xact_state':0,'transaction_count':0},
    {'error_number':2627,'xact_state':0,'transaction_count':0},
    {'error_number':0,'xact_state':1,'transaction_count':1},
    None,
])
def test_notification_same_batch_and_residual_checks_even_on_failure(monkeypatch,tmp_path,diagnostic):
    from qa import schema011_notification_failure as failure
    from sqlalchemy.exc import DBAPIError
    import foodsave.db as db
    connections=[];residual=[]
    tmp_path.chmod(0o700);path=tmp_path/'manifest';manifest=make_manifest(uuid4())
    write_private(path,manifest)
    class FakeDatabase:
        def connect(self):
            c=Connection();connections.append(c);return c
    monkeypatch.setattr(failure,'preflight',lambda *a,**k:None)
    monkeypatch.setattr(failure,'seed',lambda *a,**k:None)
    monkeypatch.setattr(db,'execute',lambda *a,**k:None)
    def one(c,sql,**kwargs):
        if 'sp_getapplock' in sql:return {'result':0}
        if sql.startswith('BEGIN TRY '):
            assert 'ERROR_NUMBER()' in sql and '@@TRANCOUNT' in sql and 'BEGIN CATCH' in sql
            catch=sql.split('BEGIN CATCH ',1)[1]
            capture='DECLARE @qa_error int=ERROR_NUMBER(),@qa_state int=XACT_STATE(),@qa_count int=@@TRANCOUNT;'
            rollback='IF XACT_STATE()<>0 ROLLBACK TRANSACTION;'
            report='SELECT @qa_error AS error_number,@qa_state AS xact_state,@qa_count AS transaction_count;'
            assert catch.index(capture)<catch.index(rollback)<catch.index(report)<catch.index('END CATCH')
            if diagnostic is None:raise DBAPIError(None,None,Exception('(1205) withheld'))
            return diagnostic
        if c is connections[-1] and len(connections)>1:residual.append(sql)
        return {'n':0}
    monkeypatch.setattr(db,'one',one)
    if diagnostic and diagnostic['error_number']==2627 and diagnostic['xact_state']==-1:
        assert len(failure.suite(FakeDatabase(),manifest,INJECTION_CASES[0],path))==2
    else:
        with pytest.raises((failure.InjectionFailure,DBAPIError)):
            failure.suite(FakeDatabase(),manifest,INJECTION_CASES[0],path)
    assert len(residual)==len(cleanup.SCOPES)+len(cleanup.FORBIDDEN)
    assert not connections[0].tx.is_active and not connections[0].tx.committed
    assert Path(str(path)+'.'+INJECTION_CASES[0]+'.started').exists()
    before=len(connections)
    with pytest.raises(FileExistsError):failure.suite(FakeDatabase(),manifest,INJECTION_CASES[0],path)
    assert len(connections)==before


def test_notification_checks_all_scopes_after_nonzero_residual(monkeypatch):
    from qa.schema011_notification_failure import verify_zero,InjectionFailure
    import foodsave.db as db
    checks=[]
    def one(c,sql,**kwargs):checks.append(sql);return {'n':1}
    monkeypatch.setattr(db,'one',one)
    with pytest.raises(InjectionFailure):verify_zero(Database(),make_manifest(uuid4())['batches'][INJECTION_CASES[0]])
    assert len(checks)==len(cleanup.SCOPES)+len(cleanup.FORBIDDEN)


def test_foreign_non_fk_references_are_in_stop_scope():
    assert "RIGHT(event_key,36) IN (:a,:b,:v,:o,:n)" in cleanup.FORBIDDEN['exp_events']
    assert "JSON_VALUE(response,'$.snapshot.store_id')=:s" in cleanup.SCOPES['request_results']
    assert 'related_vendor_id IN (:a,:b,:v)' in cleanup.SCOPES['notifications']


def test_cleanup_refuses_while_race_run_holds_guard(monkeypatch):
    import foodsave.db as db
    manifest,_,_=fixture()
    monkeypatch.setattr(cleanup,'preflight',lambda *a,**k:None)
    def one(c,sql,**params):
        assert 'sp_getapplock' in sql and params['resource']=='foodsave:qa011:'+manifest['run_id']
        return {'result':-1}
    monkeypatch.setattr(db,'one',one)
    monkeypatch.setattr(db,'rows',lambda *a,**k:pytest.fail('no scan/delete while workers running'))
    with pytest.raises(ValueError,match='race_still_running'):
        cleanup.inspect(None,manifest,CASES[0])
