"""Build nearby queries from fixed fragments and non-null bound filters."""
from uuid import UUID
from fastapi import HTTPException
from . import nearby


def _invalid():
    raise HTTPException(422, '附近查詢或分頁識別碼不正確，請重新查詢')


def query(resource, parameters, store_id=None):
    expected = {'latitude', 'longitude', 'radius', 'earth_radius', 'fetch', 'after'}
    if resource not in ('stores', 'products') or set(parameters) != expected:
        _invalid()
    if resource == 'stores' and store_id is not None:
        _invalid()
    bound = dict(parameters)
    try:
        for value in (bound['after'], store_id):
            if value is not None and (not isinstance(value, str) or str(UUID(value)) != value):
                _invalid()
    except (TypeError, ValueError, AttributeError):
        _invalid()
    sql = nearby.PRODUCTS_SQL if resource == 'products' else nearby.STORES_SQL
    if resource == 'products':
        original = ' AND (:store_id IS NULL OR p.store_id=:store_id)'
        sql = sql.replace(original, '' if store_id is None else ' AND p.store_id=:store_id')
        if store_id is not None:
            bound['store_id'] = store_id
        original = ' AND (:after IS NULL OR p.id>:after)'
        replacement = ' AND p.id>:after'
    else:
        original = 'WHERE (:after IS NULL OR s.id>:after)'
        replacement = 'WHERE s.id>:after'
    sql = sql.replace(original, '' if bound['after'] is None else replacement)
    if bound['after'] is None:
        del bound['after']
    if any(value is None for value in bound.values()):
        _invalid()
    return sql, bound
