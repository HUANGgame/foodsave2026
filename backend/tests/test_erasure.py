"""Control-flow/SQL-plan tests with a transactional fake, NOT SQL integration."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from copy import deepcopy
import pytest
from backend.foodsave import erasure as m

NOW = datetime(2026, 10, 3)


class Database:
    def __init__(self):
        self.data = {'request': {'id': 'request-fixture', 'user_id': 'user-fixture', 'approved_for_erasure': True, 'requested_at': NOW-timedelta(days=4), 'pii_cleared_at': None, 'purge_after': None, 'policy_version': None}, 'receipt': False, 'writes': []}
        self.fail_on = None
        self.active = False
        self.waiting = False
        self.name = 'foodsave'

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def begin(self):
        before = deepcopy(self.data)
        try:
            yield self
        except Exception:
            self.data = before
            raise

    def read(self, sql, **params):
        if 'DB_NAME' in sql: return {'name': self.name}
        if 'schema_migrations' in sql: return {'version': '004_erasure.sql'}
        if 'erasure_receipts' in sql: return {'request_id': 'request-fixture'} if self.data['receipt'] else None
        if 'deletion_requests' in sql: return self.data['request']
        if 'dbo.users' in sql: return {'id': 'user-fixture', 'email': 'fixture@example.test', 'active': self.active}
        if 'SYSUTCDATETIME() AS now' in sql: return {'now': NOW}
        if 'r.state=' in sql: return {'id': 'waiting'} if self.waiting else None
        raise AssertionError(sql)

    def write(self, sql, **params):
        if self.fail_on and self.fail_on in sql: raise RuntimeError('injected interruption')
        self.data['writes'].append(sql)
        if sql.startswith('UPDATE dbo.deletion_requests'):
            self.data['request'].update(pii_cleared_at=params['now'], purge_after=params['purge'], policy_version=params['v'])
        if sql.startswith('DELETE FROM dbo.deletion_requests'): self.data['request'] = None
        if sql.startswith('INSERT INTO dbo.erasure_receipts'): self.data['receipt'] = True


@pytest.fixture
def context(monkeypatch):
    db = Database()
    monkeypatch.setattr(m, 'one', lambda c, sql, **p: c.read(sql, **p))
    monkeypatch.setattr(m, 'execute', lambda c, sql, **p: c.write(sql, **p))
    monkeypatch.setattr(m, 'rows', lambda c, sql, **p: [{'id': 'request-fixture'}])
    # Values are arbitrary test fixtures, not approved production policy.
    return db, m.Eraser(db, m.Policy('fixture', 2, 0, 3, 'fixture-only', True))


def test_disabled_policy_stops_before_connect(context):
    db, _ = context
    worker = m.Eraser(None, m.Policy('fixture', 2, 0, 3, 'fixture-only'))
    with pytest.raises(ValueError, match='disabled'): worker.run(apply=True)
    assert db.data['writes'] == []


@pytest.mark.parametrize('change', [{'grace_days': None}, {'business_retention_days': -1}, {'receipt_days': 0}, {'enabled': 'true'}, {'external_procedure': ''}])
def test_no_implicit_or_infinite_policy(change):
    values = dict(version='fixture', grace_days=2, business_retention_days=0, receipt_days=3, external_procedure='fixture-only')
    with pytest.raises(ValueError): m.Policy(**(values | change))


def test_dry_run_is_read_only(context):
    db, worker = context
    assert worker.run()[0]['phase'] == 'clear_pii'
    assert db.data['writes'] == []


def test_two_phase_and_receipt_retry(context):
    db, worker = context
    assert worker.process('request-fixture', apply=True)['state'] == 'pii_cleared_business_retained'
    statements = '\n'.join(db.data['writes'])
    assert 'password_hash=' in statements and 'DELETE FROM dbo.sessions' in statements
    assert "'$.snapshot.name'" in statements and "'$.owner_id'" in statements
    assert 'DELETE FROM dbo.users' not in statements
    assert 'DELETE FROM dbo.notifications WHERE user_id=:u' in statements
    assert 'DELETE FROM dbo.reservation_terminals WHERE user_id=:u' in statements
    assert 'related_vendor_id=NULL' in statements and 'vendor_id=NULL' in statements
    assert worker.process('request-fixture', apply=True)['state'] == 'sql_completed'
    count = len(db.data['writes'])
    assert worker.process('request-fixture', apply=True)['external_erasure_verified'] is False
    # A lock statement is allowed; data mutations are not repeated.
    assert len(db.data['writes']) == count+1
    assert db.data['request'] is None
    statements = db.data['writes']
    assert statements.index('DELETE FROM dbo.coupons WHERE user_id=:u') < statements.index('DELETE FROM dbo.draws WHERE user_id=:u')


@pytest.mark.parametrize('failure', ['UPDATE dbo.stores', 'DELETE FROM dbo.users'])
def test_atomic_phase_recovers_after_failure(context, failure):
    db, worker = context
    if failure.startswith('DELETE'): worker.process('request-fixture', apply=True)
    before = deepcopy(db.data)
    db.fail_on = failure
    assert worker.run(apply=True)[0]['state'] == 'failed_retryable'
    # run also performs bounded expired-receipt housekeeping after the rollback.
    assert db.data['request'] == before['request'] and db.data['receipt'] == before['receipt']
    assert db.data['writes'][:-3] == before['writes']
    assert all('DELETE TOP (100)' in sql and 'expires_at<=' in sql for sql in db.data['writes'][-3:])
    db.fail_on = None
    assert worker.process('request-fixture', apply=True)['state'] in ('sql_completed', 'pii_cleared_business_retained')


def test_retention_and_policy_change_block_purge(context):
    db, worker = context
    worker.policy = m.Policy('fixture', 2, 30, 3, 'fixture-only', True)
    worker.process('request-fixture', apply=True)
    assert worker.process('request-fixture', apply=True)['state'] == 'waiting_retention'
    worker.policy = m.Policy('changed', 2, 0, 3, 'fixture-only', True)
    assert worker.process('request-fixture', apply=True)['state'] == 'policy_mismatch'


@pytest.mark.parametrize('condition', ['active', 'wrong_database', 'waiting'])
def test_unsafe_accounts_block(context, condition):
    db, worker = context
    if condition == 'waiting':
        db.waiting = True
        assert worker.process('request-fixture', apply=True)['state'] == 'blocked_waiting_orders'
    else:
        if condition == 'active': db.active = True
        else: db.name = 'another_database'
        with pytest.raises(ValueError): worker.process('request-fixture', apply=True)
    assert db.data['writes'] == [] or all('sp_getapplock' in s for s in db.data['writes'])


def test_request_needs_individual_operator_review(context):
    db, worker = context
    db.data['request']['approved_for_erasure'] = False
    assert worker.process('request-fixture', apply=True)['state'] == 'pending_operator_review'
    assert all('sp_getapplock' in s for s in db.data['writes'])
