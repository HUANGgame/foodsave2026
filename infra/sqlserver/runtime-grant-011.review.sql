-- REVIEW ONLY. Requires explicit approval of this exact scope before execution.
SET XACT_ABORT ON;
IF N'REPLACE_WITH_APPROVED_RUNTIME' LIKE N'REPLACE_%' THROW 51000,'Replace approved principal placeholder first',1;
IF DB_NAME()<>N'foodsave' THROW 51000,'Wrong database',1;
IF NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='011_mark_notification_read.sql') THROW 51000,'Owner migrations006-011 required',1;
IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=N'REPLACE_WITH_APPROVED_RUNTIME' AND type='E' AND authentication_type_desc='EXTERNAL' AND sid=CONVERT(binary(16),CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_APP_ID')))
 THROW 51000,'Existing approved runtime principal must match Application ID',1;
-- Fixed modules must share dbo ownership with the data tables; no impersonation.
IF EXISTS(SELECT 1 FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id
 WHERE s.name='dbo' AND o.name IN ('expire_reservation','close_vendor_business','report_stock_loss','mark_notification_read','notifications','reservation_terminals','reservations','products','stores','favorites','reviews','request_results','users','deletion_requests')
 AND COALESCE(o.principal_id,s.principal_id)<>DATABASE_PRINCIPAL_ID('dbo'))
 THROW 51000,'Unexpected ownership chain; stop for review',1;
IF EXISTS(SELECT 1 FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
 WHERE o.schema_id=SCHEMA_ID('dbo') AND o.name IN ('expire_reservation','close_vendor_business','report_stock_loss','mark_notification_read') AND m.execute_as_principal_id IS NOT NULL)
 THROW 51000,'Unexpected module impersonation; stop for review',1;
BEGIN TRY
 BEGIN TRANSACTION;
 GRANT UPDATE (service_mode) ON OBJECT::dbo.stores TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT EXECUTE ON OBJECT::dbo.expire_reservation TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT EXECUTE ON OBJECT::dbo.close_vendor_business TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT EXECUTE ON OBJECT::dbo.report_stock_loss TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT EXECUTE ON OBJECT::dbo.mark_notification_read TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (id,user_id,event_key,kind,body,created_at,read_at,expires_at) ON OBJECT::dbo.notifications TO [REPLACE_WITH_APPROVED_RUNTIME];
 GRANT SELECT (reservation_id,user_id,vendor_id,reason,previous_state,released_quantity,created_at) ON OBJECT::dbo.reservation_terminals TO [REPLACE_WITH_APPROVED_RUNTIME];
 COMMIT;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK;
 THROW;
END CATCH;
-- No direct INSERT/UPDATE/DELETE on the two new tables, no direct business DELETE,
-- no users DELETE, owner approval access, role membership, DDL or GRANT OPTION.
