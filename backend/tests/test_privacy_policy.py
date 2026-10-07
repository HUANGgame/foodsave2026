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


def test_location_amendment_preserves_other_approved_policy_content():
    import subprocess
    previous=json.loads(subprocess.check_output(['git','show','9b924eb2397d9c88625f0f4d149b46f5be9429f8:backend/foodsave/static/privacy-policy.json'],cwd=ROOT))
    assert POLICY['version']=='foodsave-test-20261007-v2'
    assert POLICY['summary']==previous['summary'] and POLICY['links']==previous['links']
    for old,new in zip(previous['sections'],POLICY['sections'],strict=True):
        assert old['title']==new['title']
        if old['title']=='定位、相機與外部服務':
            assert new['paragraphs'][1:]==old['paragraphs'][1:]
            assert new['paragraphs'][0].split('商家點選掃碼取貨')[1]==old['paragraphs'][0].split('商家點選掃碼取貨')[1]
            assert '座標送至 FoodSave 後端' in new['paragraphs'][0]
            assert '店址草稿座標會保存於 FoodSave 資料庫' in new['paragraphs'][0]
            assert '取貨地點快照' in new['paragraphs'][0]
            assert '不會因關閉或重新載入 App 而清除' in new['paragraphs'][0]
        elif old['title']=='測試範圍':
            assert new['paragraphs']==[p.replace('寄信量與服務可用性受全站配額及限時授權影響。','寄信量受全站配額及服務可用性影響。') for p in old['paragraphs']]
        else:assert new==old
    settings=json.loads((ROOT/'infra/privacy-public-settings.example.json').read_text())
    assert settings['NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE']=='true'
    assert settings['FOODSAVE_PRIVACY_POLICY_COMPLETE']=='false'
    assert settings['FOODSAVE_REGISTRATION_ENABLED']=='false'
    with TestClient(app) as client:
        assert POLICY['version'] in client.get('/privacy-policy').text
