-- PUBLIC TEMPLATE: replace only approved runtime name/object ID. NOT EXECUTED.
-- User explicitly approved runtime business access, not owner/DDL/erasure rights.
-- IMPORTANT: deletion request INSERT withheld: SQL cannot grant INSERT by column.
-- Current deletion-submit API will fail/roll back until reviewed view/proc fix.
-- Connect directly to database foodsave as existing authorized owner.
SET XACT_ABORT ON;
IF N'REPLACE_WITH_APPROVED_RUNTIME' LIKE N'REPLACE_%'
 THROW 51000, 'Replace placeholders with explicitly approved identity first', 1;
IF DB_NAME() <> N'foodsave' THROW 51000, 'Wrong database; nothing granted', 1;
IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version='004_erasure.sql')
 THROW 51000, 'Expected reviewed schema 004; nothing granted', 1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF DATABASE_PRINCIPAL_ID(N'REPLACE_WITH_APPROVED_RUNTIME') IS NULL
   CREATE USER [REPLACE_WITH_APPROVED_RUNTIME] FROM EXTERNAL PROVIDER
     WITH OBJECT_ID='00000000-0000-0000-0000-000000000000';
 -- No guessed SID / no directory-role fallback. If Entra resolution fails, STOP.
 IF NOT EXISTS (SELECT 1 FROM sys.database_principals
   WHERE name=N'REPLACE_WITH_APPROVED_RUNTIME' AND type='E'
     AND sid=CONVERT(binary(16),CONVERT(uniqueidentifier,'00000000-0000-0000-0000-000000000000')))
   THROW 51000, 'Principal identity mismatch; owner must inspect mapping', 1;
 IF EXISTS (SELECT 1 FROM sys.database_role_members WHERE member_principal_id=DATABASE_PRINCIPAL_ID(N'REPLACE_WITH_APPROVED_RUNTIME'))
   THROW 51000, 'Existing role membership requires separate review', 1;
 IF EXISTS (SELECT 1 FROM sys.schemas WHERE principal_id=DATABASE_PRINCIPAL_ID(N'REPLACE_WITH_APPROVED_RUNTIME'))
   THROW 51000, 'Runtime must not own a schema', 1;
 -- Stop on existing broad/direct rights rather than quietly preserving them.
 -- A fresh contained principal is expected for this first authorization.
 IF EXISTS (SELECT 1 FROM sys.database_permissions
   WHERE grantee_principal_id=DATABASE_PRINCIPAL_ID(N'REPLACE_WITH_APPROVED_RUNTIME')
     AND NOT (class=0 AND permission_name='CONNECT' AND state='G'))
   THROW 51000, 'Existing explicit permissions require review; no changes committed', 1;
 GRANT CONNECT TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.users TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (active) ON OBJECT::dbo.users TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (token_hash,user_id,expires_at) ON OBJECT::dbo.sessions TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT INSERT, DELETE ON OBJECT::dbo.sessions TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.rate_limits TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (attempts,window_start) ON OBJECT::dbo.rate_limits TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.stores TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.products TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active,revision) ON OBJECT::dbo.products TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.reservations TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (state,completed_at) ON OBJECT::dbo.reservations TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.request_results TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT ON OBJECT::dbo.exp_rules TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (amount,enabled) ON OBJECT::dbo.exp_rules TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.exp_events TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT, DELETE ON OBJECT::dbo.favorites TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.reviews TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.spin_grants TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (remaining) ON OBJECT::dbo.spin_grants TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.prizes TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT UPDATE (remaining) ON OBJECT::dbo.prizes TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.draws TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT ON OBJECT::dbo.coupons TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT INSERT ON OBJECT::dbo.audit_logs TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT, INSERT, DELETE ON OBJECT::dbo.ranking_rules TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (week_key) ON OBJECT::dbo.weekly_settlements TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT INSERT ON OBJECT::dbo.weekly_settlements TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT INSERT ON OBJECT::dbo.weekly_rankings TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (version) ON OBJECT::dbo.schema_migrations TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (id,user_id,state) ON OBJECT::dbo.deletion_requests TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.deletion_requests TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY SELECT (approved_for_erasure,pii_cleared_at,purge_after,policy_version,completed_at,requested_at)
   ON OBJECT::dbo.deletion_requests TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY SELECT, INSERT, UPDATE, DELETE ON OBJECT::dbo.erasure_receipts TO [REPLACE_WITH_APPROVED_RUNTIME];
 -- No role, schema-wide permission, GRANT OPTION, DDL, IMPERSONATE,
 -- database-owner permission, erasure approval, or other database is granted.
 COMMIT;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT > 0 ROLLBACK;
 THROW;
END CATCH;
-- Metadata-only review. Does not read account/business rows.
SELECT p.name,dp.state_desc,dp.permission_name,dp.class_desc,
 OBJECT_SCHEMA_NAME(dp.major_id) AS schema_name,
 OBJECT_NAME(dp.major_id) AS object_name,
 CASE WHEN dp.minor_id>0 THEN COL_NAME(dp.major_id,dp.minor_id) END AS column_name
FROM sys.database_permissions dp
JOIN sys.database_principals p ON p.principal_id=dp.grantee_principal_id
WHERE p.name=N'REPLACE_WITH_APPROVED_RUNTIME'
ORDER BY object_name,permission_name,column_name;
