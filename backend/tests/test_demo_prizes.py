import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from foodsave import api, demo_prizes as demo

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZES_ENABLED','true')
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZE_STORE',str(tmp_path/'demo-prizes.json'))
    api.app.dependency_overrides[api.current_user]=lambda:{'id':'synthetic-admin','role':'admin'}
    with TestClient(api.app) as c:yield c
    api.app.dependency_overrides.clear()

def test_admin_update_shared_snapshot_no_coupon(client,monkeypatch,tmp_path):
    pool=client.get('/admin/demo-prizes').json()
    pool['prizes'][0]['name']='新示範咖啡'
    saved=client.put('/admin/demo-prizes',json=pool)
    assert saved.status_code==200 and saved.json()['revision']==2
    assert json.loads((tmp_path/'demo-prizes.json').read_text())['prizes'][0]['name']=='新示範咖啡'
    assert client.put('/admin/demo-prizes',json=pool).status_code==409
    api.app.dependency_overrides[api.current_user]=lambda:{'id':'synthetic-consumer','role':'consumer'}
    monkeypatch.setattr(demo.secrets,'randbelow',lambda n:0)
    public=client.get('/demo-prizes').json()
    result=client.post('/demo-draws',json={'revision':2}).json()
    assert result['prizes']==public['prizes'] and result['revision']==2
    assert result['prize']['name']=='新示範咖啡'
    assert result['redeemable'] is False and result['consumes_real_spin'] is False
    assert result['notice']=='示範，暫不可兌換'
    assert 'coupon_code' not in result and 'weight' not in result['prize']

def test_roles_cannot_edit_or_draw_as_wrong_role(client):
    pool=client.get('/admin/demo-prizes').json()
    assert client.post('/demo-draws',json={'revision':1}).status_code==403
    for role in ('consumer','vendor'):
        api.app.dependency_overrides[api.current_user]=lambda role=role:{'role':role}
        assert client.get('/admin/demo-prizes').status_code==403
        assert client.put('/admin/demo-prizes',json=pool).status_code==403
    assert client.post('/demo-draws',json={'revision':1}).status_code==403

def test_disabled_default_and_no_write(client,monkeypatch,tmp_path):
    monkeypatch.delenv('FOODSAVE_DEMO_PRIZES_ENABLED')
    assert client.get('/demo-prizes').json()=={'enabled':False}
    assert client.get('/admin/demo-prizes').status_code==404
    assert not (tmp_path/'demo-prizes.json').exists()

def test_six_unique_slots_and_weight_bounds(client):
    pool=client.get('/admin/demo-prizes').json()
    pool['prizes'][0]['id']=pool['prizes'][1]['id']
    assert client.put('/admin/demo-prizes',json=pool).status_code==422
    pool=client.get('/admin/demo-prizes').json();pool['prizes'][0]['weight']=0
    assert client.put('/admin/demo-prizes',json=pool).status_code==422

def test_all_six_server_sectors_selectable(client,monkeypatch):
    api.app.dependency_overrides[api.current_user]=lambda:{'role':'consumer'}
    for index in range(6):
        monkeypatch.setattr(demo.secrets,'randbelow',lambda n,index=index:index)
        assert client.post('/demo-draws',json={'revision':1}).json()['prize']['id']==f'demo-{index+1}'


def test_changed_version_never_selects_result(client,monkeypatch):
    data=client.get('/admin/demo-prizes').json()
    assert client.put('/admin/demo-prizes',json=data).status_code==200
    api.app.dependency_overrides[api.current_user]=lambda:{'role':'consumer'}
    def forbidden(_):raise AssertionError('must not choose a result on mismatch')
    monkeypatch.setattr(demo.secrets,'randbelow',forbidden)
    response=client.post('/demo-draws',json={'revision':1})
    assert response.status_code==409
    data=response.json()
    assert data['revision']==2 and data['code']=='pool_changed'
    assert 'prize' not in data and 'coupon_code' not in data
    assert client.post('/demo-draws',json={}).status_code==422


def test_draw_and_admin_update_share_atomic_lock(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered,release,updating=Event(),Event(),Event()
    config=demo.DemoPoolUpdate.model_validate(demo.read())
    def choose(n):
        entered.set()
        assert release.wait(2)
        return 0
    def edit():
        updating.set()
        return demo.update(config)
    monkeypatch.setattr(demo.secrets,'randbelow',choose)
    with ThreadPoolExecutor(max_workers=2) as executor:
        result=executor.submit(demo.draw,1)
        assert entered.wait(2)
        changed=executor.submit(edit)
        assert updating.wait(2)
        assert not changed.done()
        release.set()
        assert result.result(timeout=2)['revision']==1
        assert changed.result(timeout=2)['revision']==2
