IF EXISTS(SELECT owner_id FROM dbo.stores WHERE owner_id IS NOT NULL GROUP BY owner_id HAVING COUNT(*)>1)
 THROW 51000, 'Existing multi-store owners require review; no automatic reassignment', 1;
-- Owner-reviewed migration only. Preserve existing stores' reservation behavior.
ALTER TABLE dbo.stores ADD service_mode varchar(16) NULL;
-- Separate compilation after ADD; static owner-only SQL, no user input.
EXEC(N'UPDATE dbo.stores SET service_mode=''reservation'' WHERE service_mode IS NULL');
EXEC(N'ALTER TABLE dbo.stores ALTER COLUMN service_mode varchar(16) NOT NULL');
EXEC(N'ALTER TABLE dbo.stores ADD CONSTRAINT df_stores_service_mode DEFAULT ''information'' FOR service_mode');
EXEC(N'ALTER TABLE dbo.stores ADD CONSTRAINT ck_stores_service_mode CHECK(service_mode IN (''information'',''reservation''))');
-- No pause/transition state, product mode or product timestamp column.
-- sourceUpdatedAt derives from merchant request_results.created_at; unknown is NULL.
CREATE UNIQUE INDEX ux_stores_single_owner ON dbo.stores(owner_id) WHERE owner_id IS NOT NULL;
