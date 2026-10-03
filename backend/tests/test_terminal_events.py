"""Regression tests for dispatch/auth/atomic rollback. SQL scripts still need real SQL QA."""
from contextlib import contextmanager
from pathlib import Path
import json
import pytest
from fastapi import HTTPException
import foodsave.service as svc
import foodsave.admin as admin
from backend.foodsave.erasure import Policy

class DB:
    def __init__(self): self.writes=[]
    @contextmanager
    def begin(self):
        before=list(self.writes)
        try: yield self
        except Exception:
            self.writes=before
            raise

@pytest.mark.parametrize('role,identity,allowed', [('consumer','c',True),('vendor','v',True),('consumer','other',False),('vendor','other',False)])
def test_deleted_order_terminal_is_scoped(monkeypatch,role,identity,allowed):
    monkeypatch.setattr(svc,'one',lambda *a,**k:dict(user_id='c',vendor_id='v',reason='vendor_out_of_stock'))
    action=lambda:svc.Service().terminal_result(None,dict(id=identity,role=role),'order')
    if allowed:
        assert action()==dict(id='order',state='removed',terminal_reason='vendor_out_of_stock')
    else:
        with pytest.raises(HTTPException) as e:action()
        assert e.value.status_code==404

@pytest.mark.parametrize('operation,status', [('reserve',410),('pickup-preview',410),('transition',None),('pickup-confirm',None)])
def test_original_retry_cannot_recreate_deleted_order(monkeypatch,operation,status):
    payload={'id':'order'}; result=dict(id='order',state='removed',terminal_reason='vendor_out_of_stock')
    replies=iter([dict(id='c',role='consumer'),dict(fingerprint=svc.digest(svc.dump(payload)),response=json.dumps(result))])
    monkeypatch.setattr(svc,'one',lambda *a,**k:next(replies))
    action=lambda:svc.Service(DB()).mutate(dict(id='c',role='consumer'),operation,'same-key',payload,lambda c:pytest.fail('must not mutate again'))
    if status:
        with pytest.raises(HTTPException) as e:action()
        assert e.value.status_code==status
    else:assert action()==result

@pytest.mark.parametrize('outcome,status',[('conflict',409),('not_found',404),('applied',None)])
def test_stock_loss_procedure_result_not_ordinary_return(monkeypatch,outcome,status):
    calls=[]; service=admin.AdminService(); service.mutate=lambda u,o,k,p,f:f(None)
    def one(c,sql,**params):
        calls.append((sql,params));return dict(outcome=outcome,cancelled_count=2)
    monkeypatch.setattr(admin,'one',one)
    monkeypatch.setattr(admin,'execute',lambda *a,**k:pytest.fail('no direct stock return'))
    action=lambda:service.report_stock_loss(dict(id='v',role='vendor'),'key','p',dict(expected_revision=7,expected_pending=2,actual_available=0))
    if status:
        with pytest.raises(HTTPException) as e:action()
        assert e.value.status_code==status
    else:assert action()['cancelled_count']==2
    assert calls[0][1]==dict(u='v',p='p',revision=7,pending=2,actual=0)


def test_mutation_failure_rolls_back_and_does_not_cache_success(monkeypatch):
    db=DB()
    def one(c,sql,**p):return dict(id='c',role='consumer') if 'dbo.users' in sql else None
    monkeypatch.setattr(svc,'one',one)
    monkeypatch.setattr(svc,'execute',lambda *a,**k:pytest.fail('must not cache failure'))
    def action(c):
        c.writes.append('terminal')
        raise RuntimeError('notification insert failed')
    with pytest.raises(RuntimeError):svc.Service(db).mutate(dict(id='c',role='consumer'),'transition','key',{},action)
    assert db.writes==[]


def test_inbox_and_read_are_current_user_scoped(monkeypatch):
    calls=[]
    monkeypatch.setattr(svc,'rows',lambda c,sql,**p:calls.append((sql,p)) or [])
    monkeypatch.setattr(svc,'one',lambda c,sql,**p:calls.append((sql,p)) or {'outcome':'not_found'})
    service=svc.Service(DB()); assert service.notifications({'id':'c'})==[]
    with pytest.raises(HTTPException) as e:service.mark_notification_read({'id':'c'},'n')
    assert e.value.status_code==404
    assert 'user_id=:u' in calls[0][0] and calls[0][1]=={'u':'c'}
    assert calls[1][1]=={'u':'c','id':'n'}


def test_pii_grace_cannot_exceed_approved_30_days():
    with pytest.raises(ValueError,match='30 days'):Policy('test',31,0,1,'test only')


def test_procedure_security_contract():
    root=Path(__file__).resolve().parents[1]/'migrations'
    for number in ('008','009','010','011'):
        sql=next(root.glob(number+'*.sql')).read_text().upper()
        assert 'SET XACT_ABORT ON' in sql and '@@TRANCOUNT=0' in sql
        assert 'COMMIT' not in sql and 'EXECUTE AS' not in sql and 'SP_EXECUTESQL' not in sql
    for number in ('008','009','010'):
        sql=next(root.glob(number+'*.sql')).read_text()
        assert sql.index('INSERT dbo.notifications')<sql.index('DELETE r FROM dbo.reservations' if number!='008' else 'DELETE FROM dbo.reservations')
    loss=next(root.glob('010*.sql')).read_text()
    assert 'available_quantity=@actual_available' in loss and 'available_quantity+' not in loss
    assert 'exp_events' not in loss

@pytest.mark.parametrize('actor',['user_id','vendor_id','actor_id'])
def test_stock_loss_client_cannot_supply_actor(actor):
    from pydantic import ValidationError
    from foodsave.schemas import StockLoss
    with pytest.raises(ValidationError):StockLoss(expected_revision=1,expected_pending=1,actual_available=0,confirm='CANCEL_AFFECTED',**{actor:'victim'})


def test_negative_sql_security_contract():
    root=Path(__file__).resolve().parents[1]/'migrations'
    expiry=next(root.glob('008*.sql')).read_text()
    assert "@expiry>SYSUTCDATETIME()" in expiry and "@state NOT IN ('waiting','expired')" in expiry
    assert "CASE WHEN @state='waiting' THEN @qty ELSE 0 END" in expiry
    closure=next(root.glob('009*.sql')).read_text()
    assert "u.active=0 AND d.state='requested'" in closure and 'owner_id=@vendor_id' in closure
    loss=next(root.glob('010*.sql')).read_text()
    assert "s.owner_id=@vendor_id" in loss and "u.role='vendor' AND u.active=1" in loss
    assert '@revision<>@expected_revision' in loss and '<>@expected_pending' in loss
    assert loss.index("SELECT 'conflict'")<loss.index('INSERT dbo.reservation_terminals')
    read=next(root.glob('011*.sql')).read_text()
    assert 'id=@notification_id AND user_id=@user_id' in read
    grants=(root.parents[1]/'infra/sqlserver/runtime-grant-011.review.sql').read_text()
    assert grants.count('GRANT EXECUTE ON OBJECT::')==4
    for line in grants.splitlines():
        if line.strip().startswith('GRANT '):
            assert all(term not in line for term in ('DELETE','INSERT','CONTROL','ALTER','WITH GRANT OPTION'))


def test_schema011_plan_and_refused_execution_without_approval():
    import subprocess,sys
    script=Path(__file__).resolve().parents[1]/'qa/terminal_rollback.py'
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['db_access'] is False
    result=subprocess.run([sys.executable,str(script),'--execute'],capture_output=True,text=True)
    assert result.returncode==2 and 'quiet window' in result.stderr


def test_schema011_preflight_failure_requests_rollback(monkeypatch):
    from qa import terminal_rollback as qa
    from uuid import uuid4
    import foodsave.db as db
    class Tx:
        rolled=False
        def rollback(self):self.rolled=True
    class C:
        tx=Tx()
        def begin(self):return self.tx
        def __enter__(self):return self
        def __exit__(self,*a):pass
    class Database:
        c=C()
        def connect(self):return self.c
    monkeypatch.setattr(db,'execute',lambda *a,**k:None)
    monkeypatch.setattr(db,'one',lambda *a,**k:{'name':'wrong'})
    database=Database()
    with pytest.raises(qa.AcceptanceFailure):qa.suite(database,uuid4())
    assert database.c.tx.rolled


def test_schema011_qa_counts_only_granted_columns():
    source=(Path(__file__).resolve().parents[1]/'qa/terminal_rollback.py').read_text()
    assert 'SELECT COUNT(id) AS n FROM dbo.notifications WHERE event_key=:k' in source
    assert 'SELECT COUNT({col}) AS n FROM dbo.{table} WHERE {col} IN' in source
    assert 'SELECT COUNT(*) AS n FROM dbo.notifications' not in source
    assert "SELECT COUNT(*) AS n FROM dbo.{table} WHERE {col} IN" not in source


def test_migration007_builds_quoted_constraint_statement_before_exec():
    sql=(Path(__file__).resolve().parents[1]/'migrations/007_notifications_and_terminal_ledger.sql').read_text()
    assert sql.count('EXEC(@statement);')==2
    assert "SET @statement=N'ALTER TABLE dbo.favorites DROP CONSTRAINT '+QUOTENAME(@fk);" in sql
    assert "SET @statement=N'ALTER TABLE dbo.favorites DROP CONSTRAINT '+QUOTENAME(@pk);" in sql
    assert "EXEC(N'ALTER TABLE dbo.favorites DROP CONSTRAINT '+QUOTENAME" not in sql
