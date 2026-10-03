-- Same dbo ownership chain permits this fixed INSERT without base-table grants.
-- No EXECUTE AS, dynamic SQL, optional approval fields or permanent-erasure work.
CREATE PROCEDURE dbo.submit_deletion_request
 @request_id uniqueidentifier,
 @user_id uniqueidentifier
AS
BEGIN
 SET NOCOUNT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1
  THROW 51000, 'Deletion request requires the existing account transaction', 1;
 IF @request_id IS NULL OR @user_id IS NULL
  THROW 51000, 'Request and account identifiers are required', 1;
 INSERT INTO dbo.deletion_requests
  (id,user_id,state,requested_at,completed_at,approved_for_erasure,pii_cleared_at,purge_after,policy_version)
 VALUES
  (CONVERT(varchar(36),@request_id),CONVERT(varchar(36),@user_id),'requested',SYSUTCDATETIME(),NULL,0,NULL,NULL,NULL);
END;
