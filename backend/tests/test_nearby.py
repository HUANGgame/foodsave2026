"""SQLite query-semantics checks with TOP->LIMIT adaptation, NOT Azure SQL tests.

The distance CTE, WHERE, joins and ordering execute as written. This does not
validate T-SQL compilation, SQL Server plans/permissions or transaction locks.
"""
import base64
from contextlib import contextmanager
from datetime import datetime
import json
import math
import re
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from foodsave import nearby
from foodsave.nearby_queries import query as nearby_query
from foodsave.service import Service
from foodsave.api import app, service
import foodsave.service as operations

NOW='2026-10-06 12:00:00'


def identity(number):return str(UUID(int=number))


class LocalQueryDB:
    def __init__(self):
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute("ATTACH DATABASE ':memory:' AS dbo")
        for name,fn in [('RADIANS',math.radians),('SIN',math.sin),('COS',math.cos),('SQRT',math.sqrt),('ASIN',math.asin)]:self.db.create_function(name,1,fn)
        self.db.create_function('POWER',2,pow)
        self.db.create_function('SYSUTCDATETIME',0,lambda:NOW)
        self.db.create_function('JSON_VALUE',2,lambda value,path:json.loads(value).get(path[2:]))
        self.db.executescript('''
CREATE TABLE dbo.users(id TEXT PRIMARY KEY,role TEXT,active INTEGER);
CREATE TABLE dbo.stores(id TEXT PRIMARY KEY,owner_id TEXT,name TEXT,latitude REAL,longitude REAL,service_mode TEXT,location_revision INTEGER,location_confirmed INTEGER);
CREATE TABLE dbo.products(id TEXT PRIMARY KEY,store_id TEXT,name TEXT,photo_url TEXT,original_price_minor INTEGER,sale_price_minor INTEGER,available_quantity INTEGER,pickup_deadline TEXT,revision INTEGER,active INTEGER);
CREATE TABLE dbo.request_results(operation TEXT,response TEXT,created_at TEXT);
INSERT INTO dbo.users VALUES ('owner','consumer',1),('inactive','consumer',0),('admin','admin',1);
''')
        self.executed=[]

    @contextmanager
    def begin(self):yield self

    def rows(self,c,sql,**parameters):
        assert sql.startswith(nearby.NEARBY_CTE)
        assert sql.endswith(('ORDER BY s.id\n', 'ORDER BY p.id\n'))
        assert set(re.findall(r'(?<!:):([a-zA-Z_]\w*)', sql)) == set(parameters)
        assert all(value is not None for value in parameters.values())
        self.executed.append((sql,parameters))
        # Only adapt SQL Server row-limit syntax; use the actual production CTE.
        adapted=sql.replace('SELECT TOP (:fetch)','SELECT')+' LIMIT :fetch'
        rows=[dict(row) for row in self.db.execute(adapted,parameters)]
        for row in rows:
            for k in ('checked_at','source_updated_at'):
                if row.get(k) is not None:row[k]=datetime.fromisoformat(row[k])
        return rows

    def store(self,n,lat=0,lng=0,owner='owner',confirmed=1):
        self.db.execute('INSERT INTO dbo.stores VALUES (?,?,?,?,?,?,1,?)',(identity(n),owner,'Store '+str(n),lat,lng,'reservation',confirmed))
        return identity(n)

    def product(self,n,store,active=1,deadline='2026-10-07 12:00:00'):
        self.db.execute('INSERT INTO dbo.products VALUES (?,?,?,?,100,50,5,?,1,?)',(identity(n),store,'Food '+str(n),'https://example.invalid/food',deadline,active))
        return identity(n)


@pytest.fixture
def query_db(monkeypatch):
    db=LocalQueryDB();monkeypatch.setattr(operations,'rows',db.rows)
    yield Service(db),db
    db.db.close()


def collect(method,**query):
    found=[];cursor=None;seen=set()
    while True:
        page=method(**query,cursor=cursor)
        found.extend(page['items']);cursor=page['next_cursor']
        assert page['radius_m']==1000
        if cursor is None:return found
        assert cursor not in seen
        seen.add(cursor)


def test_more_than_200_distant_candidates_do_not_hide_any_nearby_store(query_db):
    svc,db=query_db
    for n in range(1,401):db.store(n,lat=2,lng=2)
    for n in range(401,732):db.store(n)
    result=collect(svc.nearby_stores,latitude=0,longitude=0,limit=37)
    assert [s['id'] for s in result]==[identity(n) for n in range(401,732)]
    assert len({s['id'] for s in result})==331
    assert all(s['product_count']==0 for s in result)  # empty stores remain visible
    assert all(p['fetch']==38 for sql,p in db.executed)


def test_products_are_distance_filtered_before_paging_and_selected_store_is_complete(query_db):
    svc,db=query_db;far=db.store(1,lat=2);near=db.store(2);another=db.store(3)
    for n in range(1,401):db.product(n,far)
    for n in range(401,706):db.product(n,near)
    for n in range(706,741):db.product(n,another)
    all_items=collect(svc.nearby_products,latitude=0,longitude=0,limit=43)
    assert [p['id'] for p in all_items]==[identity(n) for n in range(401,741)]
    selected=collect(svc.nearby_products,latitude=0,longitude=0,limit=31,store_id=near)
    assert len(selected)==305 and all(p['store_id']==near for p in selected)
    assert all(p['source']=='foodsave' and p['stale'] for p in selected)


def test_unconfirmed_inactive_and_missing_owners_are_not_public_and_expired_products_excluded(query_db):
    svc,db=query_db
    published=db.store(1);db.store(2,confirmed=0);db.store(3,owner='inactive');db.store(4,owner='admin');db.store(5,owner=None)
    for n in range(1,6):db.product(n,identity(n))
    db.product(6,published,active=0);db.product(7,published,deadline=NOW)
    stores=svc.nearby_stores(0,0)['items'];products=svc.nearby_products(0,0)['items']
    assert [s['id'] for s in stores]==[published]
    assert stores[0]['product_count']==1
    assert [p['id'] for p in products]==[identity(1)]
    # Explicit publication changes query eligibility; GPS draft itself did not.
    db.db.execute('UPDATE dbo.stores SET location_confirmed=1 WHERE id=?',(identity(2),))
    assert [s['id'] for s in svc.nearby_stores(0,0)['items']]==[published,identity(2)]


@pytest.mark.parametrize('center,inside,outside',[
    ((0,0),(0,0.008993),(0,0.008994)),  # ~999.98m vs ~1000.09m
    ((0,179.999),(0,-179.999),(0,-179.98)),
    ((89.999,0),(89.999,180),(89.98,0)),
    ((-89.999,0),(-89.999,180),(-89.98,0)),
])
def test_one_kilometer_boundary_antimeridian_and_poles(query_db,center,inside,outside):
    svc,db=query_db;db.store(1,*inside);db.store(2,*outside)
    items=svc.nearby_stores(*center)['items']
    assert [s['id'] for s in items]==[identity(1)]
    assert 0<=items[0]['distance_m']<=1000


def test_identical_and_antipodal_points_do_not_cause_math_domain_error(query_db):
    svc,db=query_db;db.store(1);db.store(2,lng=180)
    items=svc.nearby_stores(0,0)['items']
    assert len(items)==1 and items[0]['distance_m']==0


@pytest.mark.parametrize('count,limit',[(0,10),(1,1),(50,50),(51,50),(300,100)])
def test_page_lookahead_and_last_page_do_not_drop_boundary_item(query_db,count,limit):
    svc,db=query_db
    for n in range(1,count+1):db.store(n)
    items=collect(svc.nearby_stores,latitude=0,longitude=0,limit=limit)
    assert [s['id'] for s in items]==[identity(n) for n in range(1,count+1)]


def test_deleting_previous_page_item_does_not_shift_next_page(query_db):
    svc,db=query_db
    for n in range(1,8):db.store(n)
    first=svc.nearby_stores(0,0,limit=3)
    db.db.execute('DELETE FROM dbo.stores WHERE id=?',(identity(1),))
    second=svc.nearby_stores(0,0,limit=3,cursor=first['next_cursor'])
    assert [s['id'] for s in second['items']]==[identity(n) for n in (4,5,6)]


def test_cursor_is_bound_to_center_resource_and_store_filter(query_db):
    svc,db=query_db
    for n in range(1,4):db.store(n);db.product(n,identity(n))
    store_cursor=svc.nearby_stores(0,0,limit=1)['next_cursor']
    product_cursor=svc.nearby_products(0,0,limit=1)['next_cursor']
    for call in (lambda:svc.nearby_stores(1,0,cursor=store_cursor),lambda:svc.nearby_products(0,0,cursor=store_cursor),lambda:svc.nearby_products(0,0,cursor=product_cursor,store_id=identity(1))):
        with pytest.raises(HTTPException) as e:call()
        assert e.value.status_code==422


@pytest.mark.parametrize('cursor',['','not-base64!!!','x'*769,base64.urlsafe_b64encode(b'[]').decode(),base64.urlsafe_b64encode(b'null').decode()])
def test_bad_cursor_is_rejected_before_query(query_db,cursor):
    svc,db=query_db
    with pytest.raises(HTTPException) as e:svc.nearby_stores(0,0,cursor=cursor)
    assert e.value.status_code==422 and not db.executed


@pytest.mark.parametrize('lat,lng,limit',[(91,0,1),(0,181,1),(float('nan'),0,1),(0,float('inf'),1),(0,0,0),(0,0,101),(0,0,True),(0,0,'50')])
def test_invalid_query_never_reaches_database(query_db,lat,lng,limit):
    svc,db=query_db
    with pytest.raises(HTTPException) as e:svc.nearby_stores(lat,lng,limit=limit)
    assert e.value.status_code==422 and not db.executed


def test_api_requires_location_and_rejects_radius_override_without_silently_broadening(query_db):
    svc,db=query_db
    svc.authenticate=lambda token:{'id':'customer','role':'consumer'}
    app.dependency_overrides[service]=lambda:svc
    try:
        with TestClient(app) as client:
            headers={'Authorization':'Bearer local-fixture'}
            assert client.get('/nearby/stores?latitude=0&longitude=0').status_code==401
            for query in ('','latitude=0','latitude=nan&longitude=0','latitude=0&longitude=0&radius=5000','latitude=0&longitude=0&limit=101'):
                assert client.get('/nearby/stores?'+query,headers=headers).status_code==422
            r=client.get('/nearby/stores?latitude=0&longitude=0',headers=headers)
            assert r.status_code==200 and r.json()=={'items':[],'next_cursor':None,'radius_m':1000,'page_size':50}
            assert client.get('/nearby/products?latitude=0&longitude=0&store_id=bad',headers=headers).status_code==422
    finally:app.dependency_overrides.clear()


def test_legacy_lists_keep_array_contract_without_200_item_cutoff(monkeypatch):
    from foodsave.admin import AdminService
    queries=[]
    class DB:
        @contextmanager
        def begin(self):yield None
    def rows(c,sql,**p):
        queries.append(sql)
        if 'SELECT p.*' in sql:return [{'id':identity(n)} for n in range(1,306)]
        if 'source_updated_at' in sql:return [{'id':identity(n),'source_updated_at':None,'checked_at':datetime(2026,10,6)} for n in range(1,306)]
        return [{'id':identity(n)} for n in range(1,306)]
    import foodsave.admin as admin
    monkeypatch.setattr(operations,'rows',rows);monkeypatch.setattr(admin,'rows',rows)
    svc=AdminService(DB());svc.expire_reservations=lambda **kw:0
    assert len(svc.list_products())==305
    assert len(svc.stores({'id':'customer'}))==305
    assert len(svc.vendor_catalog({'id':'vendor','role':'vendor'})['products'])==305
    assert all('FETCH NEXT 200' not in q for q in queries)
    assert all('s.location_confirmed=1' in q for q in queries[:2])


@pytest.mark.parametrize('resource,store_id', [
    ('stores', None), ('products', None),
    ('products', identity(0)), ('products', identity((1 << 128) - 1)),
])
@pytest.mark.parametrize('after', [None, identity(0), identity((1 << 128) - 1)])
def test_optional_query_filters_have_only_non_null_bound_values(resource, after, store_id):
    parameters, _ = nearby.parameters(resource, 25, 121, 50, None, store_id)
    parameters['after'] = after
    before = dict(parameters)
    sql, bindings = nearby_query(resource, parameters, store_id)
    assert parameters == before
    assert sql.startswith(nearby.NEARBY_CTE)
    assert sql.endswith('ORDER BY ' + ('s' if resource == 'stores' else 'p') + '.id\n')
    assert (':after' in sql) == (after is not None)
    assert (':store_id' in sql) == (resource == 'products' and store_id is not None)
    assert ' IS NULL OR ' not in sql
    assert set(re.findall(r'(?<!:):([a-zA-Z_]\w*)', sql)) == set(bindings)
    assert all(value is not None for value in bindings.values())
    assert {key: bindings[key] for key in before if key != 'after'} == {
        key: value for key, value in before.items() if key != 'after'}
    if after is not None:
        assert bindings['after'] == after
    if store_id is not None:
        assert bindings['store_id'] == store_id
    from sqlalchemy import text
    from sqlalchemy.dialects.mssql.pyodbc import MSDialect_pyodbc
    compiled = text(sql).bindparams(**bindings).compile(dialect=MSDialect_pyodbc(paramstyle='qmark'))
    assert len(compiled.positiontup) == str(compiled).count('?')
    assert all(compiled.params[key] is not None for key in compiled.positiontup)


@pytest.mark.parametrize('changes', [{'after': 'bad'}, {'unexpected': 1}, {'fetch': None}])
def test_query_builder_rejects_invalid_bindings(changes):
    parameters, _ = nearby.parameters('products', 0, 0, 50, None)
    with pytest.raises(HTTPException) as error:
        nearby_query('products', {**parameters, **changes})
    assert error.value.status_code == 422


def test_query_builder_rejects_invalid_resource_and_store_filter():
    parameters, _ = nearby.parameters('stores', 0, 0, 50, None)
    for resource, store_id in (('unknown', None), ('stores', identity(1)), ('products', 'invalid')):
        with pytest.raises(HTTPException) as error:
            nearby_query(resource, parameters, store_id)
        assert error.value.status_code == 422
