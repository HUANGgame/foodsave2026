-- Incremental approved grant ONLY, after owner migration005 and identity verification.
-- Placeholder: replace with the same previously approved contained runtime user.
-- Does not create/alter the procedure, user, role, schema or business data.
SET XACT_ABORT ON;
IF N'REPLACE_WITH_APPROVED_RUNTIME' LIKE N'REPLACE_%'
 THROW 51000, 'Replace approved principal placeholder first', 1;
IF DB_NAME()<>N'foodsave' THROW 51000, 'Wrong database', 1;
IF NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='005_deletion_request_procedure.sql')
 THROW 51000, 'Owner migration005 required', 1;
IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=N'REPLACE_WITH_APPROVED_RUNTIME' AND type='E' AND authentication_type_desc='EXTERNAL' AND sid=CONVERT(binary(16),CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_APP_ID')))
 THROW 51000, 'Existing approved runtime principal identity must match Application ID', 1;
BEGIN TRY
 BEGIN TRANSACTION;
 GRANT EXECUTE ON OBJECT::dbo.submit_deletion_request TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.deletion_requests TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY SELECT (approved_for_erasure,pii_cleared_at,purge_after,policy_version,completed_at,requested_at)
  ON OBJECT::dbo.deletion_requests TO [REPLACE_WITH_APPROVED_RUNTIME];
 DENY SELECT, INSERT, UPDATE, DELETE ON OBJECT::dbo.erasure_receipts TO [REPLACE_WITH_APPROVED_RUNTIME];
 COMMIT;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK;
 THROW;
END CATCH;
