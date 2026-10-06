-- READ ONLY. Replace only with independently verified existing runtime identity.
-- Never guess the principal or SID from the app/site display name.
SET NOCOUNT ON;
DECLARE @Principal sysname=N'REPLACE_WITH_VERIFIED_RUNTIME_PRINCIPAL';
DECLARE @ExpectedSid varbinary(85)=NULL;
IF DB_NAME()<>N'foodsave' THROW 51000,'Wrong database',1;
IF @Principal LIKE N'REPLACE_%' OR @ExpectedSid IS NULL THROW 51000,'Verified principal and SID required',1;
IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=@Principal AND sid=@ExpectedSid AND type='E' AND authentication_type_desc='EXTERNAL')
 THROW 51000,'Existing runtime identity mismatch',1;
SELECT version FROM dbo.schema_migrations ORDER BY version;
SELECT name,type_name(user_type_id) AS sql_type,is_nullable FROM sys.columns WHERE object_id=OBJECT_ID('dbo.stores') ORDER BY column_id;
SELECT name,is_unique,is_disabled,is_hypothetical,filter_definition FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.stores');
SELECT COL_NAME(i.object_id,i.column_id) AS index_column,i.key_ordinal,i.is_included_column
 FROM sys.index_columns i JOIN sys.indexes x ON x.object_id=i.object_id AND x.index_id=i.index_id
 WHERE x.object_id=OBJECT_ID('dbo.stores') AND x.name='ux_stores_single_owner' ORDER BY i.key_ordinal;
SELECT OBJECT_NAME(object_id) AS procedure_name,HASHBYTES('SHA2_256',CONVERT(varbinary(max),definition)) AS definition_hash
 FROM sys.sql_modules WHERE object_id IN (OBJECT_ID('dbo.close_vendor_business'),OBJECT_ID('dbo.report_stock_loss'));
SELECT dp.state_desc,dp.permission_name,dp.class_desc,OBJECT_SCHEMA_NAME(dp.major_id) AS schema_name,OBJECT_NAME(dp.major_id) AS object_name,
 CASE WHEN dp.minor_id>0 THEN COL_NAME(dp.major_id,dp.minor_id) END AS column_name
 FROM sys.database_permissions dp WHERE grantee_principal_id=DATABASE_PRINCIPAL_ID(@Principal);
SELECT r.name AS role_name FROM sys.database_role_members m JOIN sys.database_principals r ON r.principal_id=m.role_principal_id WHERE m.member_principal_id=DATABASE_PRINCIPAL_ID(@Principal);
-- Metadata cannot prove effective grants if inherited roles / DENY / ownership differ.
-- Owner must review the entire result and validate using the actual runtime login.
