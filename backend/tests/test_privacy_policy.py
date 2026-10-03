import json
from pathlib import Path
from fastapi.testclient import TestClient
from foodsave.api import app

ROOT = Path(__file__).parents[2]
POLICY = json.loads((ROOT/'backend/foodsave/static/privacy-policy.json').read_text())


def test_approved_content_does_not_enable_registration(monkeypatch):
    for name in ['FOODSAVE_PRIVACY_POLICY_COMPLETE','FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED','FOODSAVE_REGISTRATION_ENABLED','FOODSAVE_RETENTION_SUMMARY']:
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as client:
        response = client.get('/privacy')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'draft'
        assert data['policy'] == POLICY
        assert data['retention'] == POLICY['summary']
        assert data['request_is_erasure'] is False
        page = client.get('/privacy-policy')
        assert page.status_code == 200
        assert 'text/html' in page.headers['content-type']
        for section in POLICY['sections']:
            for paragraph in section['paragraphs']:
                assert paragraph in page.text


def test_public_policy_escapes_operator(monkeypatch):
    monkeypatch.setenv('FOODSAVE_OPERATOR_NAME','<script>alert(1)</script>')
    with TestClient(app) as client:
        page = client.get('/privacy-policy').text
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page


def test_approved_owner_policy_has_finite_retention_and_no_execution():
    owner = json.loads((ROOT/'infra/erasure-policy-approved-test.json').read_text())
    assert owner['version'] == POLICY['version']
    assert (owner['grace_days'],owner['business_retention_days'],owner['receipt_days']) == (0,0,30)
    assert owner['enabled'] is False
    app_source = (ROOT/'app/privacy/page.tsx').read_text()
    assert 'backend/foodsave/static/privacy-policy.json' in app_source
