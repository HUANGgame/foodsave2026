"""Owner-only schema011 exact synthetic batch cleanup. Preview first; never legacy005."""
import argparse
import hashlib
import json
from pathlib import Path
from qa.schema011_fixture import CASES, NAMES, email, expected_requests, marker, preflight, read_private, validate_manifest


def validate_rows(case, ids, data):
    """Fail closed on every unexpected row/reference. Pure function for adversarial tests."""
    users = {r['id']: r for r in data['users']}
    if set(users) != {ids[n] for n in NAMES[:3]}:
        raise ValueError('three_exact_users_required')
    closure = case.startswith('reserve-close')
    for name in NAMES[:3]:
        u = users[ids[name]]
        if u['email'] != email(ids, name) or u['role'] != ('vendor' if name=='vendor' else 'consumer') or (not u['active'] and not (closure and name=='vendor')):
            raise ValueError('user_marker_mismatch')
    closed = not users[ids['vendor']]['active']
    if len(data['stores']) != int(not closed) or len(data['products']) != int(not closed):
        raise ValueError('business_scope_mismatch')
    for row in data['stores']:
        if any(row[k] != v for k,v in {'id':ids['store'], 'owner_id':ids['vendor'], 'name':marker(ids), 'latitude':0, 'longitude':0}.items()) or row['service_mode'] not in ('reservation','information'):
            raise ValueError('store_marker_mismatch')
    for row in data['products']:
        expected = {'id':ids['product'],'store_id':ids['store'],'name':marker(ids),'photo_url':'https://images.example.invalid/qa.png','original_price_minor':100,'sale_price_minor':50,'active':True}
        if any(row[k] != v for k,v in expected.items()) or row['available_quantity'] not in (0,1) or row['revision'] not in (1,2,3):
            raise ValueError('product_marker_mismatch')
    allowed_orders = {ids['order-seed']:ids['consumer-a']} if case.startswith(('cancel-','expiry-')) else {ids['order-new']:ids['consumer-b']}
    if len(data['reservations']) > 1 or len(data['reservation_terminals']) > 1:
        raise ValueError('order_bound')
    present = set()
    for r in data['reservations']:
        snapshot = json.loads(r['snapshot'])
        if r['id'] not in allowed_orders or r['user_id'] != allowed_orders[r['id']] or r['product_id'] != ids['product'] or r['quantity'] != 1 or r['state'] not in ('waiting','cancelled') or snapshot.get('name') != marker(ids) or snapshot.get('store_id') != ids['store'] or snapshot.get('sale_price_minor') != 50:
            raise ValueError('reservation_scope_mismatch')
        present.add(r['id'])
    allowed_reasons = {'expired','vendor_out_of_stock'} if case.startswith('expiry-') else {'vendor_closed'} if closure else {'vendor_out_of_stock'}
    terminals = {}
    for r in data['reservation_terminals']:
        rid = r['reservation_id']
        if rid not in allowed_orders or rid in present or r['user_id'] != allowed_orders[rid] or r['vendor_id'] != ids['vendor'] or r['reason'] not in allowed_reasons or r['previous_state'] != 'waiting' or r['released_quantity'] != int(r['reason']=='expired'):
            raise ValueError('terminal_scope_mismatch')
        terminals[rid] = r
    requests = expected_requests(case, ids)
    if len(data['request_results']) > len(requests):
        raise ValueError('request_bound')
    for q in data['request_results']:
        identity = (q['user_id'],q['operation'],q['request_key'])
        body = json.loads(q['response'])
        allowed_id = ids['store'] if q['operation']=='store-mode' else ids['product'] if q['operation']=='stock-loss' else next(iter(allowed_orders))
        if identity not in requests or q['fingerprint'] != requests[identity] or body.get('id') != allowed_id:
            raise ValueError('request_scope_mismatch')
    allowed_notices = {(r['user_id'], (r['reason']+':'+(ids['vendor'] if r['reason']=='vendor_closed' else rid)), r['reason']) for rid,r in terminals.items()}
    if len(data['notifications']) != len(allowed_notices):
        raise ValueError('notification_count_mismatch')
    for n in data['notifications']:
        if (n['user_id'],n['event_key'],n['kind']) not in allowed_notices or n['related_vendor_id'] != ids['vendor'] or n['read_at'] is not None:
            raise ValueError('notification_scope_mismatch')
    if len(data['deletion_requests']) != int(closed) or len(data['audit_logs']) != int(closed):
        raise ValueError('closure_receipt_mismatch')
    for r in data['deletion_requests']:
        if r['id'] != ids['deletion'] or r['user_id'] != ids['vendor'] or r['state'] != 'requested' or r['approved_for_erasure'] or any(r[k] is not None for k in ('completed_at','pii_cleared_at','purge_after','policy_version')):
            raise ValueError('deletion_scope_mismatch')
    for r in data['audit_logs']:
        if r['id'] != ids['audit'] or r['actor_id'] != ids['vendor'] or r['action'] != 'account.deletion_requested' or r['target_id'] != ids['deletion']:
            raise ValueError('audit_scope_mismatch')
    return {table:len(values) for table,values in data.items()}


# These predicates deliberately also select references from OTHER users. Such rows
# must fail validation; they are never silently included in the deletion scope.
SCOPES = {
    'users': 'id IN (:a,:b,:v)',
    'stores': 'id=:s OR owner_id IN (:a,:b,:v)',
    'products': 'id=:p OR store_id=:s',
    'reservations': 'id IN (:o,:n) OR user_id IN (:a,:b,:v) OR product_id=:p',
    'reservation_terminals': 'reservation_id IN (:o,:n) OR user_id IN (:a,:b,:v) OR vendor_id IN (:a,:b,:v)',
    'notifications': 'user_id IN (:a,:b,:v) OR related_vendor_id IN (:a,:b,:v) OR event_key IN (:eo,:en,:lo,:ln,:cl)',
    'request_results': "user_id IN (:a,:b,:v) OR JSON_VALUE(response,'$.id') IN (:a,:b,:v,:s,:p,:o,:n,:d) OR JSON_VALUE(response,'$.owner_id') IN (:a,:b,:v) OR JSON_VALUE(response,'$.store_id')=:s OR JSON_VALUE(response,'$.snapshot.store_id')=:s",
    'deletion_requests': 'id=:d OR user_id IN (:a,:b,:v)',
    'audit_logs': 'id=:audit OR actor_id IN (:a,:b,:v) OR target_id IN (:a,:b,:v,:s,:p,:o,:n,:d)',
}
FORBIDDEN = {
    'sessions': 'user_id IN (:a,:b,:v)',
    'favorites': 'user_id IN (:a,:b,:v) OR vendor_id IN (:a,:b,:v)',
    'reviews': 'user_id IN (:a,:b,:v) OR reservation_id IN (:o,:n)',
    'exp_events': 'user_id IN (:a,:b,:v) OR RIGHT(event_key,36) IN (:a,:b,:v,:o,:n)',
    'spin_grants': 'user_id IN (:a,:b,:v)', 'draws': 'user_id IN (:a,:b,:v)',
    'coupons': 'user_id IN (:a,:b,:v)', 'weekly_rankings': 'user_id IN (:a,:b,:v)',
    'erasure_receipts': 'request_id=:d',
}
DELETE_KEYS = {'request_results':('user_id','operation','request_key'), 'notifications':('id',),
               'reservation_terminals':('reservation_id',), 'reservations':('id',),
               'audit_logs':('id',), 'deletion_requests':('id',), 'products':('id',),
               'stores':('id',), 'users':('id',)}


def parameters(ids):
    return dict(a=ids['consumer-a'],b=ids['consumer-b'],v=ids['vendor'],s=ids['store'],p=ids['product'],o=ids['order-seed'],n=ids['order-new'],d=ids['deletion'],audit=ids['audit'],
                eo='expired:'+ids['order-seed'],en='expired:'+ids['order-new'],lo='vendor_out_of_stock:'+ids['order-seed'],ln='vendor_out_of_stock:'+ids['order-new'],cl='vendor_closed:'+ids['vendor'])


def inspect(c, manifest, case):
    from foodsave.db import one, rows
    preflight(c, owner=True)
    if one(c, 'SELECT COUNT(*) AS n FROM sys.foreign_keys WHERE delete_referential_action<>0 OR is_disabled=1 OR is_not_trusted=1')['n'] or one(c, 'SELECT COUNT(*) AS n FROM sys.triggers WHERE parent_class=1 AND is_disabled=0')['n']:
        raise ValueError('unexpected_foreign_keys_or_triggers')
    ids = manifest['batches'][case]; params = parameters(ids)
    for table, predicate in FORBIDDEN.items():
        if one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WITH(UPDLOCK,HOLDLOCK) WHERE {predicate}', **params)['n']:
            raise ValueError('unexpected_reference_stop')
    # Never select password/session hashes or pickup hashes. Request bodies may
    # contain opaque pickup capabilities: kept only in process, hashed for preview.
    columns = {'users':'id,email,role,active', 'reservations':'id,user_id,product_id,state,quantity,snapshot,expires_at,completed_at'}
    data = {table:[dict(r) for r in rows(c, f'SELECT {columns.get(table,"*")} FROM dbo.{table} WITH(UPDLOCK,HOLDLOCK) WHERE {predicate}', **params)] for table,predicate in SCOPES.items()}
    counts = validate_rows(case, ids, data)
    canonical = {table:sorted(values,key=lambda r:json.dumps(r,sort_keys=True,default=str)) for table,values in data.items()}
    digest = hashlib.sha256(json.dumps({'manifest':manifest,'case':case,'rows':canonical},sort_keys=True,default=str).encode()).hexdigest()
    return data, counts, digest


def cleanup(database, manifest, case, approved_preview=None):
    from foodsave.db import execute, one
    validate_manifest(manifest)
    if case not in CASES:
        raise ValueError('unknown_case')
    with database.connect().execution_options(isolation_level='SERIALIZABLE') as c:
        tx = c.begin()
        try:
            data, counts, digest = inspect(c, manifest, case)
            if approved_preview is None:
                tx.rollback()
                return {'mode':'preview','case':case,'counts':counts,'preview_sha256':digest,'committed':False}
            if approved_preview != digest:
                raise ValueError('preview_changed_abort')
            for table, keys in DELETE_KEYS.items():
                for row in data[table]:
                    predicate = ' AND '.join(f'{k}=:{k}' for k in keys)
                    if execute(c, f'DELETE FROM dbo.{table} WHERE {predicate}', **{k:row[k] for k in keys}).rowcount != 1:
                        raise ValueError('delete_count_mismatch')
            params = parameters(manifest['batches'][case])
            for table,predicate in {**SCOPES,**FORBIDDEN}.items():
                if one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {predicate}', **params)['n']:
                    raise ValueError('residual_batch_rows')
            tx.commit()
            return {'mode':'apply','case':case,'deleted_counts':counts,'preview_sha256':digest,'committed':True,'remaining':0}
        except BaseException:
            if tx.is_active:
                tx.rollback()
            raise


def main():
    from owner_migrate import add_connection_arguments, owner_database
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--case',choices=CASES,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--approved-preview-sha256')
    args = parser.parse_args()
    if args.apply != bool(args.approved_preview_sha256):
        parser.error('Apply requires exact reviewed digest; preview omits both flags')
    database = None
    try:
        manifest = read_private(args.manifest)
        database = owner_database(args.server,args.driver)
        print(json.dumps(cleanup(database,manifest,args.case,args.approved_preview_sha256),sort_keys=True))
    except Exception as error:
        print(json.dumps({'status':'failed','error_class':type(error).__name__,'details':'withheld; stop and investigate privately; uncertain commit requires read-only reconciliation'}))
        raise SystemExit(1)
    finally:
        if database is not None:
            database.dispose()

if __name__ == '__main__':
    main()
