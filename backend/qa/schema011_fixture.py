"""Fixed, bounded schema011 QA identifiers. No database access at import time."""
import json
import os
from pathlib import Path
import stat
from uuid import UUID, uuid5

PAIRS = ('reserve-mode', 'reserve-loss', 'cancel-loss', 'expiry-loss')
RACE_CASES = tuple(f'{pair}-{first}' for pair in PAIRS for first in ('left', 'right'))
INJECTION_CASES = ('notification-expiry', 'notification-loss')
CASES = RACE_CASES + INJECTION_CASES
NAMES = ('consumer-a', 'consumer-b', 'vendor', 'store', 'product', 'order-seed',
         'order-new', 'deletion', 'audit')


def make_manifest(run):
    if run.version != 4:
        raise ValueError('fresh_uuid4_required')
    return {'format': 11, 'scope': 'schema011-eight-races-two-rollback-injections', 'run_id': str(run),
            'batches': {case: {n: str(uuid5(run, f'schema011:{case}:{n}')) for n in NAMES}
                        for case in CASES}}


def validate_manifest(value):
    if not isinstance(value, dict) or value != make_manifest(UUID(value.get('run_id', ''))):
        raise ValueError('manifest_exact_derivation_required')
    return value


def private_parent(path):
    path = Path(path)
    parent = path.parent
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('private_0700_directory_required')
    if parent.resolve() != parent.absolute():
        raise ValueError('symlink_directory_rejected')
    return path


def write_private(path, value):
    path = private_parent(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_private(path):
    path = private_parent(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 32768:
            raise ValueError('private_regular_manifest_required')
        return validate_manifest(json.load(stream))


def marker(ids):
    return 'foodsave-qa011:' + ids['store']


def email(ids, name):
    return f"qa011+{ids[name]}@example.invalid"


def key(ids, action):
    return 'qa011:' + ids['product'] + ':' + action


def expected_requests(case, ids):
    """Allowed exact (user, operation, key) and original payload fingerprints."""
    from foodsave.security import digest
    from foodsave.service import dump
    pair = case.rsplit('-', 1)[0]
    definitions = []
    if pair.startswith('reserve-'):
        definitions.append(('consumer-b', 'reserve', 'reserve', {'product_id': ids['product'], 'quantity': 1}))
    if pair == 'reserve-mode':
        definitions.append(('vendor', 'store-mode', 'mode', {'id': ids['store'], 'mode': 'information'}))
    if pair.endswith('-loss'):
        definitions.append(('vendor', 'stock-loss', 'loss', {'product_id': ids['product'], 'expected_revision': 1,
                            'expected_pending': int(pair != 'reserve-loss'), 'actual_available': 0}))
    if pair == 'cancel-loss':
        definitions.append(('consumer-a', 'transition', 'cancel', {'id': ids['order-seed'], 'target': 'cancelled', 'code_hash': digest('')}))
    return {(ids[user], operation, key(ids, action)): digest(dump(payload)) for user, operation, action, payload in definitions}


def preflight(c, owner=False):
    from foodsave.db import execute, one
    execute(c, 'SET LOCK_TIMEOUT 10000')
    execute(c, 'SET XACT_ABORT ON')
    value = one(c, "SELECT DB_NAME() AS name,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS owner")
    if value['name'] != 'foodsave' or value['owner'] != int(owner):
        raise ValueError('existing_authorized_identity_required')
    if not one(c, "SELECT version FROM dbo.schema_migrations WHERE version='011_mark_notification_read.sql'"):
        raise ValueError('schema011_required')
    if not owner:
        for table, perm in (('users', 'DELETE'), ('reservations', 'DELETE'), ('notifications', 'INSERT')):
            if one(c, "SELECT HAS_PERMS_BY_NAME(:t,'OBJECT',:p) AS allowed", t='dbo.'+table, p=perm)['allowed'] != 0:
                raise ValueError('restricted_runtime_required')
        for proc in ('expire_reservation', 'report_stock_loss', 'close_vendor_business', 'submit_deletion_request'):
            if one(c, "SELECT HAS_PERMS_BY_NAME(:p,'OBJECT','EXECUTE') AS allowed", p='dbo.'+proc)['allowed'] != 1:
                raise ValueError('existing_procedure_permission_required')


def seed(c, ids, case, password):
    from datetime import timedelta
    import secrets
    from foodsave.db import execute, one
    from foodsave.security import hash_password, digest
    from foodsave.service import dump
    for name in NAMES[:3]:
        if one(c, 'SELECT id FROM dbo.users WITH(UPDLOCK,HOLDLOCK) WHERE id=:id OR email=:e', id=ids[name], e=email(ids, name)):
            raise ValueError('fixture_collision_do_not_rerun')
        execute(c, 'INSERT dbo.users(id,email,password_hash,role) VALUES(:id,:e,:h,:r)',
                id=ids[name], e=email(ids, name), h=hash_password(password), r='vendor' if name=='vendor' else 'consumer')
    now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
    execute(c, "INSERT dbo.stores(id,owner_id,name,latitude,longitude,service_mode) VALUES(:s,:v,:n,0,0,'reservation')",
            s=ids['store'], v=ids['vendor'], n=marker(ids))
    pending = case.startswith(('cancel-', 'expiry-'))
    execute(c, "INSERT dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active) VALUES(:p,:s,:n,'https://images.example.invalid/qa.png',100,50,:q,:end,1)",
            p=ids['product'], s=ids['store'], n=marker(ids), q=0 if pending else 1, end=now+timedelta(minutes=10))
    if pending:
        execute(c, "INSERT dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,'waiting',1,:snapshot,:h,:end)",
                id=ids['order-seed'], u=ids['consumer-a'], p=ids['product'], snapshot=dump({'name': marker(ids), 'store_id': ids['store'], 'sale_price_minor': 50}),
                h=digest(secrets.token_hex(6)), end=now-timedelta(seconds=1) if case.startswith('expiry-') else now+timedelta(minutes=10))
