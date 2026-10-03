-- REVIEW ONLY: requires separate approval. No execution by deployment/startup.
-- One mode-control column only; existing SELECT/INSERT permissions stay unchanged.
SET XACT_ABORT ON;
IF N'REPLACE_WITH_APPROVED_RUNTIME' LIKE N'REPLACE_%'
 THROW 51000, 'Replace approved principal placeholder first', 1;
IF DB_NAME()<>N'foodsave' THROW 51000, 'Wrong database', 1;
IF NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='006_store_service_mode.sql')
 THROW 51000, 'Owner migration006 required', 1;
IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=N'REPLACE_WITH_APPROVED_RUNTIME' AND type='E' AND authentication_type_desc='EXTERNAL' AND sid=CONVERT(binary(16),CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_APP_ID')))
 THROW 51000, 'Existing approved runtime principal identity must match Application ID', 1;
BEGIN TRY
 BEGIN TRANSACTION;
 GRANT UPDATE (service_mode) ON OBJECT::dbo.stores TO [REPLACE_WITH_APPROVED_RUNTIME];
 COMMIT;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK;
 THROW;
END CATCH;
