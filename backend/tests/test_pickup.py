"""Security/control-flow doubles, not real SQL execution evidence."""
from datetime import datetime, timedelta
import json
import secrets
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from foodsave import schemas as S
from foodsave.service import Service
import foodsave.service as operations

VENDOR = {'id': 'vendor', 'role': 'vendor'}
NOW = datetime(2026, 10, 3)
TOKEN = secrets.token_urlsafe(32)

class Direct(Service):
    def mutate(self, user, operation, key, payload, action):
        return action(None)


def order(**changes):
    return dict(id='order', user_id='consumer', state='waiting', quantity=1,
                expires_at=NOW + timedelta(minutes=5), now=NOW,
                snapshot=json.dumps({'name': 'QA food', 'sale_price_minor': 50}), **changes)


def test_preview_shows_snapshot_without_transition_or_pii(monkeypatch):
    def query(c, sql, **args):
        assert 's.owner_id=:vendor' in sql and args['vendor'] == VENDOR['id']
        return [order()]
    monkeypatch.setattr(operations, 'rows', query)
    monkeypatch.setattr(operations, 'execute', lambda *a, **k: pytest.fail('preview may not mutate orders'))
    result = Direct().preview_pickup(VENDOR, 'preview-key', 'FS1.'+TOKEN)
    assert result['name'] == 'QA food' and result['total_price_minor'] == 50
    assert result['review_expires_at'] == NOW + timedelta(minutes=2)
    assert len(result['review_token']) == 43
    assert set(result) == {'id','name','quantity','unit_price_minor','total_price_minor','review_token','review_expires_at'}


@pytest.mark.parametrize('state,expired', [('completed', False), ('cancelled', False), ('waiting', True)])
def test_preview_rejects_spent_or_expired(monkeypatch, state, expired):
    row = order(); row['state'] = state
    if expired: row['expires_at'] = NOW
    monkeypatch.setattr(operations, 'rows', lambda *a, **k: [row])
    with pytest.raises(HTTPException) as error: Direct().preview_pickup(VENDOR, 'preview-key', 'FS1.'+TOKEN)
    assert error.value.status_code == 409


def test_preview_unknown_or_other_store_and_consumer_rejected(monkeypatch):
    monkeypatch.setattr(operations, 'rows', lambda *a, **k: [])
    with pytest.raises(HTTPException) as error: Direct().preview_pickup(VENDOR, 'preview-key', 'FS1.'+TOKEN)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error: Direct().preview_pickup({'id':'consumer','role':'consumer'}, 'preview-key', 'FS1.'+TOKEN)
    assert error.value.status_code == 403


@pytest.mark.parametrize('missing,bad_token,expired', [(True,False,False),(False,True,False),(False,False,True)])
def test_confirm_requires_vendor_bound_valid_unexpired_review(monkeypatch, missing, bad_token, expired):
    def query(c, sql, **args):
        assert args['u'] == 'vendor' and "operation='pickup-preview'" in sql
        return None if missing else {'now': NOW, 'response': json.dumps({'id':'order','review_token':TOKEN,'review_expires_at':str(NOW + timedelta(seconds=-1 if expired else 30))})}
    monkeypatch.setattr(operations, 'one', query)
    svc=Direct(); svc._transition=lambda *a, **k: pytest.fail('must not fulfill')
    with pytest.raises(HTTPException): svc.confirm_pickup(VENDOR, 'confirm-key', 'preview-key', secrets.token_urlsafe(32) if bad_token else TOKEN)


def test_confirm_calls_locked_transition_only_after_review(monkeypatch):
    monkeypatch.setattr(operations, 'one', lambda *a, **k: {'now': NOW, 'response': json.dumps({'id':'order','review_token':TOKEN,'review_expires_at':str(NOW+timedelta(seconds=30))})})
    calls=[]; svc=Direct(); svc._transition=lambda *a, **k: calls.append((a,k)) or {'state':'completed'}
    assert svc.confirm_pickup(VENDOR, 'confirm-key', 'preview-key', TOKEN)['state']=='completed'
    assert len(calls)==1 and calls[0][0][2:]==('order','completed') and calls[0][1]=={'reviewed':True}


@pytest.mark.parametrize('credential', ['https://example.invalid/scan', 'FS1.short', 'name:someone', '123456', 'FS1.'+'A'*44])
def test_untrusted_qr_formats_rejected(credential):
    with pytest.raises(ValidationError): S.PickupPreview(credential=credential)


@pytest.mark.parametrize('delta', [0,2,-2,True,1.5])
def test_stock_adjustment_bounded(delta):
    with pytest.raises(ValidationError): S.StockAdjustment(delta=delta)
