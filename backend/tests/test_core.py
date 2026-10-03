"""Unit/API contract tests. These intentionally do NOT prove SQL concurrency."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import pytest
import secrets
PASSWORD = secrets.token_urlsafe(24)
SESSION = secrets.token_urlsafe(24)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from foodsave.api import app, service
from foodsave.admin import AdminService
from foodsave.service import Service
from foodsave.security import hash_password, verify_password, weighted_choice
from foodsave import schemas as S
import foodsave.service as operations

USER = {'id': '11111111-1111-1111-1111-111111111111', 'email': 'a@example.com', 'role': 'consumer'}


def test_password_salts_verification_and_invalid_encoding():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password('wrong', first)
    assert not verify_password(PASSWORD, 'broken')


def test_weighted_selection_boundaries_not_client_randomness():
    prizes = [{'id': 'a', 'weight': 1}, {'id': 'b', 'weight': 3}]
    assert [weighted_choice(prizes, lambda n, i=i: i)['id'] for i in range(4)] == ['a','b','b','b']
    with pytest.raises(ValueError):
        weighted_choice([])


@pytest.mark.parametrize('quantity', [0, -1, 11, 1.5, True])
def test_invalid_stock_requests(quantity):
    with pytest.raises(ValidationError):
        S.Reservation(product_id=USER['id'], quantity=quantity)


def test_timezone_and_coupon_constraints():
    good = dict(name='Authorized fixture coupon', kind='coupon', weight=1, remaining=1,
                terms='Test terms only; not a real coupon.', discount_percent=20, expires_at='2027-01-01T08:00:00+08:00')
    assert S.Prize(**good).expires_at == datetime(2027,1,1)
    for changes in ({'expires_at': '2027-01-01T08:00:00'}, {'discount_percent': 10}, {'discount_percent': None}, {'kind': 'physical'}):
        with pytest.raises(ValidationError):
            S.Prize(**{**good, **changes})


class AuthOnly(AdminService):
    def authenticate(self, token):
        if token != SESSION:
            raise HTTPException(401, 'Expired')
        return USER

    def transaction(self):
        raise AssertionError('Unauthorized request reached the database')


@pytest.fixture
def client():
    app.dependency_overrides[service] = lambda: AuthOnly()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_admin_and_vendor_access_is_rejected_before_database(client):
    assert client.get('/admin/data/users').status_code == 401
    headers = {'Authorization': f'Bearer {SESSION}'}
    assert client.get('/admin/data/users', headers=headers).status_code == 403
    assert client.get('/vendor/reservations', headers=headers).status_code == 403
    assert client.get('/admin/data/users', headers={'Authorization':f'Bearer {secrets.token_urlsafe(24)}'}).status_code == 401


def test_registration_role_injection_and_secret_redaction(client):
    password = PASSWORD
    response = client.post('/auth/register', json={'email': 'test@example.com', 'password': password, 'role': 'admin'})
    assert response.status_code == 422
    assert password not in response.text
    assert response.headers['cache-control'] == 'no-store'


def test_write_requires_valid_idempotency_key(client):
    headers = {'Authorization': f'Bearer {SESSION}'}
    assert client.post('/draws', headers=headers).status_code == 422
    assert client.post('/draws', headers={**headers, 'Idempotency-Key': 'short'}).status_code == 422


def test_admin_shell_serves_no_data_and_has_csp(client):
    response = client.get('/admin')
    assert response.status_code == 200
    assert 'frame-ancestors' in response.headers['content-security-policy']
    assert 'password_hash' not in response.text
    assert client.get('/health/live').json() == {'status': 'alive'}


class MemoryTransaction:
    """A test double for transaction *control flow*, not a SQL database."""
    def __init__(self):
        self.state = {'results': {}, 'effects': 0}

    @contextmanager
    def begin(self):
        old = deepcopy(self.state)
        try:
            yield self
        except Exception:
            self.state = old
            raise


@pytest.fixture
def mutation(monkeypatch):
    database = MemoryTransaction()

    def one(c, sql, **args):
        if 'FROM dbo.users' in sql:
            return USER
        if 'FROM dbo.request_results' in sql:
            return c.state['results'].get((args['u'], args['op'], args['k']))
        raise AssertionError(sql)

    def execute(c, sql, **args):
        assert 'INSERT INTO dbo.request_results' in sql
        c.state['results'][(args['u'],args['op'],args['k'])] = {'fingerprint': args['f'], 'response': args['r']}

    monkeypatch.setattr(operations, 'one', one)
    monkeypatch.setattr(operations, 'execute', execute)
    return Service(database), database


def test_same_intent_replays_result_without_running_action(mutation):
    svc, db = mutation
    def action(c):
        c.state['effects'] += 1
        return {'id': 'existing-result'}
    first = svc.mutate(USER, 'draw', 'persistent-retry-key', {}, action)
    second = svc.mutate(USER, 'draw', 'persistent-retry-key', {}, action)
    assert first == second
    assert db.state['effects'] == 1


def test_idempotency_key_payload_conflict(mutation):
    svc, db = mutation
    svc.mutate(USER, 'reserve', 'persistent-retry-key', {'quantity':1}, lambda c: {'id':'one'})
    with pytest.raises(HTTPException) as err:
        svc.mutate(USER, 'reserve', 'persistent-retry-key', {'quantity':2}, lambda c: pytest.fail('must not execute'))
    assert err.value.status_code == 409


def test_failed_action_does_not_cache_success_and_can_retry(mutation):
    svc, db = mutation
    def fails(c):
        c.state['effects'] += 1
        raise RuntimeError('simulated database disconnection')
    with pytest.raises(RuntimeError):
        svc.mutate(USER, 'draw', 'persistent-retry-key', {}, fails)
    assert db.state == {'results': {}, 'effects': 0}
    assert svc.mutate(USER, 'draw', 'persistent-retry-key', {}, lambda c: {'id':'retried'}) == {'id':'retried'}


def test_read_only_viewer_rejects_arbitrary_table():
    svc = AuthOnly()
    with pytest.raises(HTTPException) as error:
        svc.view_database({**USER,'role':'admin'}, 'users; DROP TABLE users', 1)
    assert error.value.status_code == 404


def test_taipei_week_boundary():
    from foodsave.ranking import previous_week
    # UTC Sunday 16:00 is Monday 00:00 in Taipei, the settlement boundary.
    key, start, end = previous_week(datetime(2026,10,4,16,0,tzinfo=timezone.utc))
    assert key == '2026-09-28'
    assert start == datetime(2026,9,27,16)
    assert end == datetime(2026,10,4,16)
    assert previous_week(datetime(2026,10,4,15,59,tzinfo=timezone.utc))[0] == '2026-09-21'


def test_overlapping_ranking_and_reserved_grant_source_rejected():
    with pytest.raises(ValidationError):
        S.RankingRules(rules=[{'start_rank':1,'end_rank':10,'spins':3},{'start_rank':10,'end_rank':50,'spins':1}])
    with pytest.raises(ValidationError):
        S.Grant(user_id=USER['id'], source_key='week:2026-09-28', remaining=3, expires_at='2027-01-01T00:00:00Z')


@pytest.mark.parametrize('grant,prizes,message', [(None, [], '次數'), ({'id':'grant'}, [], '獎品')])
def test_draw_failure_does_not_issue_mutation(monkeypatch, grant, prizes, message):
    svc = Service()
    monkeypatch.setattr(svc, 'mutate', lambda user, op, key, payload, action: action(None))
    monkeypatch.setattr(operations, 'one', lambda *a, **k: grant)
    monkeypatch.setattr(operations, 'rows', lambda *a, **k: prizes)
    monkeypatch.setattr(operations, 'execute', lambda *a, **k: pytest.fail('must not deduct or issue reward'))
    with pytest.raises(HTTPException) as error:
        svc.draw(USER, 'same-draw-request')
    assert error.value.status_code == 409
    assert message in error.value.detail


def test_draw_response_omits_weight_and_issues_coupon_after_deductions(monkeypatch):
    svc = Service()
    calls = []
    prize = {'id':'prize','name':'Fixture only','kind':'coupon','weight':99,'remaining':1,
             'terms':'Not a real reward','expires_at':datetime(2027,1,1),'discount_percent':20}
    monkeypatch.setattr(svc, 'mutate', lambda user, op, key, payload, action: action(None))
    monkeypatch.setattr(operations, 'one', lambda *a, **k: {'id':'grant'})
    monkeypatch.setattr(operations, 'rows', lambda *a, **k: [prize])
    monkeypatch.setattr(operations, 'execute', lambda c, sql, **k: calls.append(sql))
    result = svc.draw(USER, 'same-draw-request')
    assert 'weight' not in result['prize']
    assert 'remaining' not in result['prize']
    assert result['coupon_code']
    assert 'UPDATE dbo.spin_grants' in calls[0]
    assert 'UPDATE dbo.prizes' in calls[1]
    assert 'INSERT INTO dbo.draws' in calls[2]
    assert 'INSERT INTO dbo.coupons' in calls[3]


def test_public_registration_requires_explicit_operator_enablement(client, monkeypatch):
    monkeypatch.delenv('FOODSAVE_REGISTRATION_ENABLED', raising=False)
    response = client.post('/auth/register', json={'email':'new@example.test','password':PASSWORD})
    assert response.status_code == 503


def test_deletion_contract_is_request_not_completed_erasure(client):
    class DeletionFake(AuthOnly):
        def throttle(self, *args):
            pass
        def request_deletion(self, user, password):
            assert user['id'] == USER['id']
            assert password == PASSWORD
            return {'id':'request-id','state':'requested','account_disabled':True,'erasure_completed':False}
    app.dependency_overrides[service] = lambda: DeletionFake()
    response = client.post('/account/deletion-requests', headers={'Authorization':f'Bearer {SESSION}'}, json={'password':PASSWORD,'confirm':'DELETE'})
    assert response.status_code == 202
    assert response.json()['erasure_completed'] is False
    assert PASSWORD not in response.text


def test_maintenance_rejects_consumer_before_database(client):
    response = client.post('/admin/maintenance', headers={'Authorization':f'Bearer {SESSION}'})
    assert response.status_code == 403


def test_managed_identity_refuses_other_database(monkeypatch):
    from foodsave.db import engine
    engine.cache_clear()
    monkeypatch.delenv('FOODSAVE_ODBC_CONNECTION', raising=False)
    monkeypatch.setenv('FOODSAVE_SQL_SERVER', 'foodsave-fixture.database.windows.net')
    monkeypatch.setenv('FOODSAVE_SQL_DATABASE', 'unrelated_database')
    with pytest.raises(RuntimeError, match='Dedicated foodsave'):
        engine()
    engine.cache_clear()


def test_managed_identity_requires_installed_driver_and_no_idle_pool(monkeypatch):
    import pyodbc
    from sqlalchemy.pool import NullPool
    from foodsave.db import engine
    engine.cache_clear()
    monkeypatch.delenv('FOODSAVE_ODBC_CONNECTION', raising=False)
    monkeypatch.setenv('FOODSAVE_SQL_SERVER', 'foodsave-fixture.database.windows.net')
    monkeypatch.setenv('FOODSAVE_SQL_DATABASE', 'foodsave')
    monkeypatch.setenv('FOODSAVE_ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
    monkeypatch.setattr(pyodbc, 'drivers', lambda: [])
    with pytest.raises(RuntimeError, match='installed and verified'):
        engine()
    monkeypatch.setattr(pyodbc, 'drivers', lambda: ['ODBC Driver 18 for SQL Server'])
    db = engine()  # creates an engine, never opens a SQL connection
    assert isinstance(db.pool, NullPool)
    assert 'Database=foodsave;' in db.url.query['odbc_connect']
    assert 'Authentication=ActiveDirectoryMsi;' in db.url.query['odbc_connect']
    assert 'PWD=' not in db.url.query['odbc_connect']
    db.dispose()
    engine.cache_clear()
