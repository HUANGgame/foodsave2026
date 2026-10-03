CREATE PROCEDURE dbo.mark_notification_read @user_id varchar(36),@notification_id varchar(36)
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1 THROW 51000,'Active caller transaction required',1;
 UPDATE dbo.notifications SET read_at=COALESCE(read_at,SYSUTCDATETIME())
 WHERE id=@notification_id AND user_id=@user_id;
 SELECT CASE WHEN @@ROWCOUNT=1 THEN 'read' ELSE 'not_found' END AS outcome;
END;
