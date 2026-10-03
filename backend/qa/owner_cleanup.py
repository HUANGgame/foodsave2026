"""Owner-only cleanup of one approved concurrency fixture. Preview by default."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

NAMES = ('consumer-a', 'consumer-b', 'vendor', 'store', 'product', 'expiry', 'prize', 'grant', 'request')


def validate_manifest(value):
    if set(value) != {'format', 'run_id', 'ids', 'scope'} or value['format'] != 1 or value['scope'] != 'committed_concurrency_fixture':
        raise ValueError('invalid_manifest')
    run = UUID(value['run_id'])
    expected = {n: str(uuid5(run, n)) for n in NAMES}
    if value['ids'] != expected:
        raise ValueError('manifest_ids_not_derived_from_run')
    return run, expected


def inspect(c, run, ids):
    from foodsave.db import one, rows, execute
    execute(c, 'SET LOCK_TIMEOUT 10000')
    execute(c, 'SET XACT_ABORT ON')
    if one(c, "SELECT DB_NAME() AS name,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS owner") != {'name': 'foodsave', 'owner': 1}:
        raise ValueError('existing_owner_in_foodsave_required')
    if not one(c, "SELECT version FROM dbo.schema_migrations WHERE version='005_deletion_request_procedure.sql'"):
        raise ValueError('schema005_required')
    if one(c, 'SELECT COUNT(*) AS n FROM sys.foreign_keys WHERE delete_referential_action<>0 OR is_disabled=1 OR is_not_trusted=1')['n']:
        raise ValueError('unexpected_foreign_key_configuration')
    if one(c, 'SELECT COUNT(*) AS n FROM sys.triggers WHERE parent_class=1 AND is_disabled=0')['n']:
        raise ValueError('unexpected_enabled_trigger')
    p = {'a': ids['consumer-a'], 'b': ids['consumer-b'], 'v': ids['vendor'], 's': ids['store'], 'p': ids['product']}
    marker = 'foodsave-qa:' + run.hex
    users = rows(c, 'SELECT id,email,role,active FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id IN (:a,:b,:v)', **p)
    expected = {ids[n]: (f'qa+{run.hex}.{n}@example.invalid', 'vendor' if n == 'vendor' else 'consumer') for n in NAMES[:3]}
    if len(users) != 3 or any((u['email'], u['role']) != expected[u['id']] or not u['active'] for u in users):
        raise ValueError('account_marker_mismatch')
    stores = rows(c, 'SELECT id,owner_id,name FROM dbo.stores WITH(UPDLOCK,HOLDLOCK) WHERE id=:s OR owner_id IN (:a,:b,:v)', **p)
    if len(stores) != 1 or dict(stores[0]) != {'id': ids['store'], 'owner_id': ids['vendor'], 'name': marker}:
        raise ValueError('store_scope_mismatch')
    products = rows(c, 'SELECT id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=:p OR store_id=:s', **p)
    if len(products) != 1:
        raise ValueError('product_scope_mismatch')
    product = products[0]
    if any(product[k] != v for k, v in {'id': ids['product'], 'store_id': ids['store'], 'name': marker, 'photo_url': 'https://images.example.invalid/qa.png', 'original_price_minor': 100, 'sale_price_minor': 50}.items()):
        raise ValueError('product_marker_mismatch')
    orders = rows(c, 'SELECT id,user_id,product_id,state,quantity,snapshot FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE product_id=:p OR user_id IN (:a,:b,:v)', **p)
    if len(orders) > 1 or product['available_quantity'] != 1-len(orders):
        raise ValueError('unexpected_fixture_stock')
    for r in orders:
        snapshot = json.loads(r['snapshot'])
        if r['user_id'] not in (p['a'], p['b']) or r['product_id'] != p['p'] or r['state'] != 'waiting' or r['quantity'] != 1 or snapshot.get('name') != marker or snapshot.get('store_id') != p['s']:
            raise ValueError('reservation_scope_mismatch')
    requests = rows(c, 'SELECT user_id,operation,request_key,fingerprint,response FROM dbo.request_results WITH(UPDLOCK,HOLDLOCK) WHERE user_id IN (:a,:b,:v)', **p)
    if len(requests) != len(orders):
        raise ValueError('request_count_mismatch')
    for q in requests:
        response = json.loads(q['response'])
        if q['operation'] != 'reserve' or q['request_key'] != 'qa-concurrent-stock' or not any(r['user_id'] == q['user_id'] and r['id'] == response.get('id') for r in orders):
            raise ValueError('request_scope_mismatch')
    # Any unexpected activity aborts; these tables are NEVER cleaned by this tool.
    for table, predicate in (
        ('sessions', 'user_id IN (:a,:b,:v)'), ('exp_events', 'user_id IN (:a,:b,:v)'),
        ('favorites', 'user_id IN (:a,:b,:v) OR store_id=:s'),
        ('reviews', 'user_id IN (:a,:b,:v) OR reservation_id IN (SELECT id FROM dbo.reservations WHERE product_id=:p)'),
        ('spin_grants', 'user_id IN (:a,:b,:v)'), ('draws', 'user_id IN (:a,:b,:v)'),
        ('coupons', 'user_id IN (:a,:b,:v)'), ('audit_logs', 'actor_id IN (:a,:b,:v) OR target_id IN (:a,:b,:v,:s,:p)'),
        ('weekly_rankings', 'user_id IN (:a,:b,:v)'), ('deletion_requests', 'user_id IN (:a,:b,:v)')):
        if one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WITH(UPDLOCK,HOLDLOCK) WHERE {predicate}', **p)['n']:
            raise ValueError('unexpected_fixture_activity')
    scope = {'run_id': str(run), 'ids': ids, 'reservation_ids': sorted(r['id'] for r in orders),
             'request_keys': sorted((q['user_id'], q['operation'], q['request_key'], q['fingerprint'], hashlib.sha256(q['response'].encode()).hexdigest()) for q in requests),
             'counts': {'users': 3, 'stores': 1, 'products': 1, 'reservations': len(orders), 'request_results': len(requests)}}
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
    return scope, digest


def cleanup(database, manifest, approved_preview=None):
    from foodsave.db import execute, one
    run, ids = validate_manifest(manifest)
    with database.connect().execution_options(isolation_level='SERIALIZABLE') as c:
        tx = c.begin()
        try:
            scope, digest = inspect(c, run, ids)
            if approved_preview is None:
                tx.rollback()
                return {'mode': 'preview', 'run_id': str(run), 'counts': scope['counts'], 'preview_sha256': digest, 'committed': False}
            if approved_preview != digest:
                raise ValueError('preview_changed_abort')
            for uid, op, key, _, _ in scope['request_keys']:
                if execute(c, 'DELETE FROM dbo.request_results WHERE user_id=:u AND operation=:op AND request_key=:k', u=uid, op=op, k=key).rowcount != 1:
                    raise ValueError('request_delete_count')
            for rid in scope['reservation_ids']:
                if execute(c, 'DELETE FROM dbo.reservations WHERE id=:id AND product_id=:p', id=rid, p=ids['product']).rowcount != 1:
                    raise ValueError('reservation_delete_count')
            for table, names in (('products', ('product',)), ('stores', ('store',)), ('users', NAMES[:3])):
                for name in names:
                    if execute(c, f'DELETE FROM dbo.{table} WHERE id=:id', id=ids[name]).rowcount != 1:
                        raise ValueError('delete_count_mismatch')
                    if one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE id=:id', id=ids[name])['n']:
                        raise ValueError('remaining_fixture')
            tx.commit()
            return {'mode': 'apply', 'run_id': str(run), 'deleted_counts': scope['counts'], 'preview_sha256': digest, 'committed': True, 'fixture_accounts_remaining': 0}
        except BaseException:
            if tx.is_active: tx.rollback()
            raise


def main():
    from owner_migrate import owner_database, add_connection_arguments
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approved-preview-sha256')
    args = parser.parse_args()
    if args.apply != bool(args.approved_preview_sha256):
        parser.error('Apply requires the reviewed preview SHA256; preview omits both flags')
    database = None
    try:
        manifest = json.loads(args.manifest.read_text())
        validate_manifest(manifest)
        database = owner_database(args.server, args.driver)
        print(json.dumps(cleanup(database, manifest, args.approved_preview_sha256), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_class': type(error).__name__, 'details': 'withheld; inspect privately; transaction rolled back on validation or SQL failure'}))
        raise SystemExit(1)
    finally:
        if database is not None: database.dispose()


if __name__ == '__main__': main()
