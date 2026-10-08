"""Fixed 1 km database filtering plus immutable-ID keyset pagination.

Pages are live reads, not a cross-request snapshot. Clients restart from page 1
when their center changes or on refresh; they must follow every next_cursor.
"""
import base64
import binascii
import hashlib
import json
import math
from uuid import UUID
from fastapi import HTTPException

RADIUS_M = 1000
EARTH_RADIUS_M = 6371008.8  # Mean-radius spherical great-circle distance.

# Clamp haversine rounding at both ends before SQRT/ASIN. Longitude differences
# are periodic, so the same expression handles the antimeridian and poles.
# Every candidate is distance-filtered in SQL before TOP/cursor paging. No
# global "first 200" candidate set, offset, or Python distance filtering.
NEARBY_CTE = """
WITH visible AS (
 SELECT s.id,s.owner_id,s.name,s.latitude,s.longitude,s.service_mode,
        s.location_revision,
        POWER(SIN(RADIANS(CAST(s.latitude AS float)-:latitude)/2.0),2)
        + COS(RADIANS(:latitude))*COS(RADIANS(CAST(s.latitude AS float)))
        * POWER(SIN(RADIANS(CAST(s.longitude AS float)-:longitude)/2.0),2) AS h
 FROM dbo.stores s JOIN dbo.users u ON u.id=s.owner_id
 WHERE s.location_confirmed=1 AND u.active=1 AND u.role IN ('consumer','vendor')
), distances AS (
 SELECT visible.*,2.0*:earth_radius*ASIN(SQRT(CASE WHEN h<0 THEN 0 WHEN h>1 THEN 1 ELSE h END)) AS distance_m
 FROM visible
), nearby AS (
 SELECT * FROM distances WHERE distance_m<=:radius
)
"""

STORES_SQL = NEARBY_CTE + """
SELECT TOP (:fetch) s.id,s.owner_id AS vendor_id,s.name,s.latitude,s.longitude,
 s.service_mode,s.location_revision,s.distance_m,
 (SELECT COUNT(*) FROM dbo.products p WHERE p.store_id=s.id AND p.active=1
  AND p.pickup_deadline>SYSUTCDATETIME() AND p.available_quantity>0) AS product_count
FROM nearby s
WHERE (:after IS NULL OR s.id>:after)
ORDER BY s.id
"""

PRODUCTS_SQL = NEARBY_CTE + """
SELECT TOP (:fetch) p.id,p.store_id,s.name AS store_name,s.owner_id AS vendor_id,
 s.latitude,s.longitude,s.service_mode,s.location_revision,s.distance_m,
 p.name,p.photo_url,p.original_price_minor,p.sale_price_minor,p.available_quantity,
 p.pickup_deadline,p.revision,
 (SELECT MAX(q.created_at) FROM dbo.request_results q
 WHERE q.operation IN ('product.save','stock-adjust','stock-loss')
 AND JSON_VALUE(q.response,'$.id')=p.id) AS source_updated_at,
 SYSUTCDATETIME() AS checked_at
FROM dbo.products p JOIN nearby s ON s.id=p.store_id
WHERE p.active=1 AND p.pickup_deadline>SYSUTCDATETIME()
 AND (:store_id IS NULL OR p.store_id=:store_id) AND (:after IS NULL OR p.id>:after)
ORDER BY p.id
"""


def _invalid():
    raise HTTPException(422, '附近查詢或分頁識別碼不正確，請重新查詢')


def parameters(resource, latitude, longitude, limit, cursor, store_id=None):
    # Validate service callers as well as API parameters. All values are bound
    # SQL parameters; the cursor is a position, never an authorization token.
    if resource not in ('stores', 'products') or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        _invalid()
    try:
        latitude, longitude = float(latitude), float(longitude)
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            _invalid()
        if store_id is not None and str(UUID(store_id)) != store_id:
            _invalid()
    except (TypeError, ValueError, AttributeError):
        _invalid()
    scope = hashlib.sha256(json.dumps([1, resource, latitude, longitude, store_id, RADIUS_M], separators=(',', ':')).encode()).hexdigest()
    after = None
    if cursor is not None:
        try:
            if not isinstance(cursor, str) or not cursor or len(cursor) > 768:
                _invalid()
            value = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
            if not isinstance(value, dict) or set(value) != {'v', 'scope', 'after'} or type(value['v']) is not int or value['v'] != 1 or value['scope'] != scope:
                _invalid()
            after = value['after']
            if not isinstance(after, str) or str(UUID(after)) != after:
                _invalid()
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, AttributeError):
            _invalid()
    return dict(latitude=latitude, longitude=longitude, radius=RADIUS_M,
                earth_radius=EARTH_RADIUS_M, fetch=limit + 1, after=after), scope


def page(rows, limit, scope):
    items = [dict(row) for row in rows[:limit]]
    cursor = None
    if len(rows) > limit:
        value = {'v': 1, 'scope': scope, 'after': items[-1]['id']}
        cursor = base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
    return {'items': items, 'next_cursor': cursor, 'radius_m': RADIUS_M, 'page_size': limit}
