"""Private recovery records and failure-safe read-only QA reporting."""
import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('auth_erasure_qa', Path(__file__).parents[1] / 'qa/auth_erasure_rollback.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def test_manifest_private_exclusive_and_no_overwrite(tmp_path):
    path = tmp_path / 'recovery.json'
    data = {'marker': 'synthetic', 'users': ['id'], 'tickets': ['hash'], 'buckets': ['hash']}
    qa.write_manifest(path, data)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == data
    with pytest.raises(FileExistsError):
        qa.write_manifest(path, {})
    assert json.loads(path.read_text()) == data


def test_safe_error_excludes_driver_message_and_params():
    exc = RuntimeError('password-secret', {'token': 'secret'})
    exc.orig = Exception('42000', 'secret SQL parameters')
    assert qa.safe_error(exc) == {'error_class': 'RuntimeError', 'sqlstate': '42000'}
    assert qa.safe_error(Exception('secret')) == {'error_class': 'Exception'}


def test_all_residual_tables_attempted_after_failure(monkeypatch):
    import foodsave.db
    calls = []
    class Connection:
        connection = SimpleNamespace(driver_connection=SimpleNamespace(timeout=0))
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class DB:
        def connect(self): return Connection()
    def one(c, sql, **params):
        calls.append(sql)
        if 'dbo.users ' in sql: raise RuntimeError('secret')
        return {'n': 0}
    monkeypatch.setattr(foodsave.db, 'one', one)
    monkeypatch.setattr(foodsave.db, 'execute', lambda *args: None)
    result = qa.residual_checks(DB(), {'users': ['uuid'], 'tickets': ['hash'], 'buckets': ['hash']})
    assert len(calls) == 3
    assert result == {'users': {'error_class': 'RuntimeError'}, 'account_challenges': {'residual': 0}, 'rate_limits': {'residual': 0}}
