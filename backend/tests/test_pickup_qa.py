"""Harness safety checks only; not real SQL acceptance."""
from uuid import uuid4
import json
import subprocess
import sys
from pathlib import Path
import pytest
from qa import pickup_rollback as qa


def test_plan_does_not_require_db_or_execution_dependencies():
    result=subprocess.run([sys.executable,str(Path(qa.__file__))],capture_output=True,text=True,check=True)
    plan=json.loads(result.stdout)
    assert plan['db_access'] is False and plan['commits']==0 and plan['accounts_in_rollback']==3


def test_execute_without_approval_stops_before_sql():
    result=subprocess.run([sys.executable,str(Path(qa.__file__)),'--execute'],capture_output=True,text=True)
    assert result.returncode==2 and 'quiet window' in result.stderr


def test_failing_preflight_rolls_back_and_restores_api_dependencies(monkeypatch):
    from foodsave.api import app
    import foodsave.db as db
    class Tx:
        rolled_back=False
        def rollback(self):self.rolled_back=True
        def commit(self):pytest.fail('harness must never commit')
    class Connection:
        tx=Tx()
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def begin(self):return self.tx
    class Database:
        c=Connection()
        def connect(self):return self.c
    monkeypatch.setattr(db,'execute',lambda *a,**k:None)
    monkeypatch.setattr(db,'one',lambda *a,**k:{'name':'wrong_database'})
    before=dict(app.dependency_overrides);database=Database()
    with pytest.raises(qa.AcceptanceFailure,match='dedicated_database'):qa.suite(database,uuid4())
    assert database.c.tx.rolled_back and app.dependency_overrides==before
