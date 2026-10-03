import json
from uuid import uuid4, uuid5
import pytest
from qa import owner_cleanup as cleanup


def manifest():
    run = uuid4()
    return {'format': 1, 'run_id': str(run), 'scope': 'committed_concurrency_fixture', 'ids': {n: str(uuid5(run, n)) for n in cleanup.NAMES}}


def test_manifest_rejects_substituted_id_and_wrong_scope():
    data = manifest()
    cleanup.validate_manifest(data)
    data['ids']['product'] = str(uuid4())
    with pytest.raises(ValueError): cleanup.validate_manifest(data)
    data = manifest(); data['scope'] = 'rollback'
    with pytest.raises(ValueError): cleanup.validate_manifest(data)


class Transaction:
    is_active = True
    committed = False
    def rollback(self): self.is_active = False
    def commit(self): self.committed = True; self.is_active = False


class Connection:
    def __init__(self): self.tx = Transaction()
    def execution_options(self, **kwargs):
        assert kwargs == {'isolation_level': 'SERIALIZABLE'}
        return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def begin(self): return self.tx
    def execute(self, *args): raise AssertionError('must not delete')


class Database:
    def __init__(self): self.c = Connection()
    def connect(self): return self.c


def test_preview_rolls_back_and_changed_preview_never_deletes(monkeypatch):
    monkeypatch.setattr(cleanup, 'inspect', lambda *args: ({'counts': {'users': 3}}, 'reviewed-digest'))
    db = Database()
    assert cleanup.cleanup(db, manifest())['committed'] is False
    assert not db.c.tx.is_active and not db.c.tx.committed
    db = Database()
    with pytest.raises(ValueError, match='preview_changed'):
        cleanup.cleanup(db, manifest(), 'stale-digest')
    assert not db.c.tx.is_active and not db.c.tx.committed


def test_validation_failure_rolls_back(monkeypatch):
    def reject(*args): raise ValueError('unexpected_fixture_activity')
    monkeypatch.setattr(cleanup, 'inspect', reject)
    db = Database()
    with pytest.raises(ValueError, match='unexpected_fixture_activity'):
        cleanup.cleanup(db, manifest(), 'reviewed-digest')
    assert not db.c.tx.is_active and not db.c.tx.committed
