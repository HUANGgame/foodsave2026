-- REVIEW TEMPLATE ONLY. NOT EXECUTED. Requires explicit approval of actual identity
-- and these four columns after the read-only preflight and validation results.
SET XACT_ABORT ON;
DECLARE @Approved bit=0;
DECLARE @Principal sysname=N'REPLACE_WITH_VERIFIED_RUNTIME_PRINCIPAL';
DECLARE @ExpectedSid varbinary(85)=NULL;
IF @Approved<>1 OR @Principal LIKE N'REPLACE_%' OR @ExpectedSid IS NULL
 THROW 51000,'Pending explicit reviewed authorization; nothing granted',1;
IF DB_NAME()<>N'foodsave' THROW 51000,'Wrong database',1;
IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=@Principal AND sid=@ExpectedSid AND type='E' AND authentication_type_desc='EXTERNAL')
 THROW 51000,'Existing runtime identity mismatch',1;
IF EXISTS(SELECT 1 FROM sys.database_role_members WHERE member_principal_id=DATABASE_PRINCIPAL_ID(@Principal))
 THROW 51000,'Role memberships require separate review',1;
IF EXISTS(SELECT 1 FROM sys.schemas WHERE principal_id=DATABASE_PRINCIPAL_ID(@Principal))
 THROW 51000,'Runtime schema ownership requires separate review',1;
IF NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='013_store_capabilities.sql') OR NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='014_store_location.sql')
 THROW 51000,'Reviewed schema013/014 required',1;
IF @@TRANCOUNT<>0 THROW 51000,'Run as a standalone reviewed transaction',1;
BEGIN TRY
 BEGIN TRANSACTION;
 DECLARE @Sql nvarchar(max)=N'GRANT UPDATE (latitude,longitude,location_confirmed,location_revision) ON OBJECT::dbo.stores TO '+QUOTENAME(@Principal)+N';';
 EXEC sp_executesql @Sql;
 COMMIT;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK;
 THROW;
END CATCH;
-- No CREATE USER, role membership, owner_id UPDATE, table-wide UPDATE, GRANT
-- OPTION, ALTER/CONTROL/IMPERSONATE or procedure changes. No automatic REVOKE.
