"""Owner-only, policy-gated erasure. Never imported by the HTTP service.

Receipts attest only to application SQL scope, NOT backups/logs/external photos.
Each account phase is atomic; a failed phase is retried from its durable state.
"""
from dataclasses import dataclass
from datetime import timedelta
import re
from .db import execute, one, rows
from .security import digest


@dataclass(frozen=True)
class Policy:
    version: str
    grace_days: int
    business_retention_days: int
    receipt_days: int
    external_procedure: str
    enabled: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', self.version):
            raise ValueError('Explicit policy version required')
        for name in ('grace_days', 'business_retention_days', 'receipt_days'):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 36500:
                raise ValueError('Explicit finite retention days required')
        if self.grace_days > 30:
            raise ValueError('Identifiable PII must be cleared within 30 days')
        if self.receipt_days < 1 or not self.external_procedure.strip():
            raise ValueError('Receipt expiry and backup/log/photo procedure required')
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be a boolean')


CHECKLIST = (
    'sessions and credentials; account remains disabled',
    'own favorites, reviews and idempotency responses',
    'vendor names, photo URLs, coordinates and reservation snapshots',
    'retained business rows remain pseudonymous until configured purge date',
    'business purge: coupons, draws, grants, EXP, ranks, reservations, audit, user',
    'unlinked SQL completion receipt with explicit expiry',
    'external backup/log/photo procedure remains operator responsibility',
)


class Eraser:
    def __init__(self, database, policy):
        self.database, self.policy = database, policy

    def run(self, *, apply=False, limit=10):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Batch limit must be 1..100')
        if apply and not self.policy.enabled:
            raise ValueError('Execution disabled: approved enabled policy required')
        # Dry-run uses SELECT only, including connection validation.
        with self.database.connect() as c:
            if one(c, 'SELECT DB_NAME() AS name')['name'] != 'foodsave':
                raise ValueError('Dedicated foodsave database required')
            if not one(c, "SELECT version FROM dbo.schema_migrations WHERE version='011_mark_notification_read.sql'"):
                raise ValueError('Owner migrations through 011 required')
            pending = rows(c, "SELECT TOP (:limit) id FROM dbo.deletion_requests WHERE state='requested' AND approved_for_erasure=1 AND ((pii_cleared_at IS NULL AND requested_at<=DATEADD(day,-:grace,SYSUTCDATETIME())) OR (pii_cleared_at IS NOT NULL AND purge_after<=SYSUTCDATETIME())) ORDER BY requested_at,id", limit=limit, grace=self.policy.grace_days)
        results = []
        for item in pending:
            try:
                results.append(self.process(item['id'], apply=apply))
            except Exception:
                # Never log SQL parameters/credentials/PII. Durable phase is unchanged.
                results.append({'request_id': item['id'], 'state': 'failed_retryable'})
        if apply:
            with self.database.begin() as c:
                execute(c, 'DELETE TOP (100) FROM dbo.erasure_receipts WHERE expires_at<=SYSUTCDATETIME()')
                execute(c, 'DELETE TOP (100) FROM dbo.notifications WHERE expires_at<=SYSUTCDATETIME()')
                execute(c, 'DELETE TOP (100) FROM dbo.reservation_terminals WHERE expires_at<=SYSUTCDATETIME()')
        return results

    def process(self, request_id, *, apply=False):
        if apply and not self.policy.enabled:
            raise ValueError('Execution disabled')
        with (self.database.begin() if apply else self.database.connect()) as c:
            if one(c, 'SELECT DB_NAME() AS name')['name'] != 'foodsave':
                raise ValueError('Dedicated foodsave database required')
            if apply:
                execute(c, "SET LOCK_TIMEOUT 5000; DECLARE @r int; EXEC @r=sp_getapplock @Resource='foodsave:erasure', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000; IF @r<0 THROW 51000,'Erasure lock unavailable',1;")
            receipt = one(c, 'SELECT request_id FROM dbo.erasure_receipts WHERE request_id=:r', r=request_id)
            if receipt:
                return {'request_id': request_id, 'state': 'sql_completed', 'external_erasure_verified': False}
            request = one(c, 'SELECT * FROM dbo.deletion_requests WHERE id=:r', r=request_id)
            if not request:
                return {'request_id': request_id, 'state': 'not_found'}
            if not request['approved_for_erasure']:
                return {'request_id': request_id, 'state': 'pending_operator_review'}
            u = request['user_id']
            hint = ' WITH(UPDLOCK,HOLDLOCK)' if apply else ''
            user = one(c, 'SELECT id,email,active FROM dbo.users' + hint + ' WHERE id=:u', u=u)
            if not user or user['active']:
                raise ValueError('Account must already be disabled')
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now']
            due = request['requested_at'] + timedelta(days=self.policy.grace_days)
            phase = 'clear_pii' if not request['pii_cleared_at'] else 'purge_business'
            if request['pii_cleared_at']:
                due = request['purge_after']
                if request['policy_version'] != self.policy.version:
                    return {'request_id': request_id, 'state': 'policy_mismatch'}
            if now < due:
                return {'request_id': request_id, 'state': 'waiting_retention', 'due': due.isoformat()}
            # Never orphan a still-redeemable customer order on a deleting vendor.
            if one(c, "SELECT TOP (1) r.id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE r.state='waiting' AND (r.user_id=:u OR s.owner_id=:u)", u=u):
                return {'request_id': request_id, 'state': 'blocked_waiting_orders'}
            if not apply:
                return {'request_id': request_id, 'state': 'dry_run', 'phase': phase, 'checklist': CHECKLIST}
            if phase == 'clear_pii':
                self.clear_pii(c, u, user['email'])
                execute(c, 'UPDATE dbo.deletion_requests SET pii_cleared_at=:now,purge_after=:purge,policy_version=:v WHERE id=:r', now=now, purge=now+timedelta(days=self.policy.business_retention_days), v=self.policy.version, r=request_id)
                return {'request_id': request_id, 'state': 'pii_cleared_business_retained'}
            self.purge(c, u)
            execute(c, 'INSERT INTO dbo.erasure_receipts(request_id,policy_version,completed_at,expires_at) VALUES(:r,:v,:now,:expires)', r=request_id, v=self.policy.version, now=now, expires=now+timedelta(days=self.policy.receipt_days))
            return {'request_id': request_id, 'state': 'sql_completed', 'external_erasure_verified': False}

    def clear_pii(self, c, u, email):
        execute(c, "UPDATE dbo.users SET email=:email,password_hash='erased',active=0 WHERE id=:u", email='erased-'+u+'@example.invalid', u=u)
        for table in ('sessions', 'favorites', 'reviews', 'request_results', 'notifications', 'reservation_terminals'):
            execute(c, f'DELETE FROM dbo.{table} WHERE user_id=:u', u=u)
        execute(c, "UPDATE dbo.notifications SET body=N'店家相關通知；店家識別資料已移除。',related_vendor_id=NULL,event_key='vendor-erased:'+id WHERE related_vendor_id=:u", u=u)
        execute(c, 'UPDATE dbo.reservation_terminals SET vendor_id=NULL WHERE vendor_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.favorites WHERE vendor_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.rate_limits WHERE bucket=:b', b=digest('deletion-public-account:'+email))
        execute(c, "UPDATE dbo.reservations SET pickup_code_hash=REPLICATE('0',64) WHERE user_id=:u", u=u)
        # Keep other customers' numeric transaction evidence but scrub vendor text.
        execute(c, "UPDATE r SET snapshot=JSON_MODIFY(JSON_MODIFY(r.snapshot,'$.name',N'已刪除商品'),'$.photo_url','') FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u", u=u)
        execute(c, "UPDATE q SET response=JSON_MODIFY(JSON_MODIFY(q.response,'$.snapshot.name',N'已刪除商品'),'$.snapshot.photo_url','') FROM dbo.request_results q JOIN dbo.stores s ON s.id=JSON_VALUE(q.response,'$.snapshot.store_id') WHERE q.operation='reserve' AND s.owner_id=:u", u=u)
        # Preserve idempotency keys: do not make an admin retry create another store.
        execute(c, "UPDATE dbo.request_results SET response=JSON_MODIFY(JSON_MODIFY(JSON_MODIFY(JSON_MODIFY(response,'$.owner_id',NULL),'$.name',N'已刪除店家'),'$.latitude',0),'$.longitude',0) WHERE operation='store.create' AND JSON_VALUE(response,'$.owner_id')=:u", u=u)
        execute(c, "UPDATE p SET name=N'已刪除商品',photo_url='',active=0,revision=revision+1 FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u", u=u)
        execute(c, "UPDATE dbo.stores SET name=N'已刪除店家',latitude=0,longitude=0 WHERE owner_id=:u", u=u)

    def purge(self, c, u):
        # FK order; never delete other users' reservations to erase a vendor.
        for table in ('sessions', 'favorites', 'reviews', 'request_results', 'notifications', 'reservation_terminals', 'coupons', 'draws', 'spin_grants', 'exp_events', 'weekly_rankings', 'reservations'):
            execute(c, f'DELETE FROM dbo.{table} WHERE user_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.audit_logs WHERE actor_id=:u OR target_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.favorites WHERE vendor_id=:u', u=u)
        execute(c, 'DELETE p FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id WHERE s.owner_id=:u AND NOT EXISTS(SELECT 1 FROM dbo.reservations r WHERE r.product_id=p.id)', u=u)
        execute(c, 'DELETE FROM dbo.stores WHERE owner_id=:u AND NOT EXISTS(SELECT 1 FROM dbo.products p WHERE p.store_id=stores.id)', u=u)
        execute(c, 'UPDATE dbo.stores SET owner_id=NULL WHERE owner_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.deletion_requests WHERE user_id=:u', u=u)
        execute(c, 'DELETE FROM dbo.users WHERE id=:u', u=u)
