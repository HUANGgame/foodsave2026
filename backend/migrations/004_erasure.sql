-- Owner-only erasure metadata. No automatic job or runtime DELETE permission.
ALTER TABLE dbo.stores ALTER COLUMN owner_id varchar(36) NULL;
ALTER TABLE dbo.deletion_requests ADD
 approved_for_erasure bit NOT NULL DEFAULT 0,
 pii_cleared_at datetime2 NULL,
 purge_after datetime2 NULL,
 policy_version varchar(80) NULL;
CREATE TABLE dbo.erasure_receipts (
 request_id varchar(36) NOT NULL PRIMARY KEY,
 policy_version varchar(80) NOT NULL,
 completed_at datetime2 NOT NULL,
 expires_at datetime2 NOT NULL
);
