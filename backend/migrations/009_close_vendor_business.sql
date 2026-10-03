CREATE PROCEDURE dbo.close_vendor_business @vendor_id varchar(36)
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1 THROW 51000,'Active caller transaction required',1;
 -- API must first authenticate the deletion password and disable this account
 -- with a deletion request in the SAME transaction. This is not a public DELETE.
 IF NOT EXISTS(SELECT 1 FROM dbo.users u WITH(UPDLOCK,HOLDLOCK) JOIN dbo.deletion_requests d ON d.user_id=u.id WHERE u.id=@vendor_id AND u.role='vendor' AND u.active=0 AND d.state='requested')
 BEGIN SELECT 'deletion_required' AS outcome; RETURN; END;
 DECLARE @store varchar(36),@name nvarchar(100),@lock int;
 SELECT @store=id,@name=name FROM dbo.stores WHERE owner_id=@vendor_id;
 IF @store IS NULL BEGIN SELECT 'closed' AS outcome,0 AS removed_orders; RETURN; END;
 DECLARE @resource nvarchar(255)=N'foodsave:store-mode:'+@store;
 EXEC @lock=sp_getapplock @Resource=@resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @lock<0 THROW 51000,'Store operation busy',1;
 DECLARE @products TABLE(id varchar(36) PRIMARY KEY);
 INSERT @products SELECT id FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE store_id=@store;
 DECLARE @orders TABLE(id varchar(36) PRIMARY KEY,user_id varchar(36),state varchar(12));
 INSERT @orders SELECT r.id,r.user_id,r.state FROM dbo.reservations r WITH(UPDLOCK,HOLDLOCK) JOIN @products p ON p.id=r.product_id;
 DECLARE @recipients TABLE(user_id varchar(36) PRIMARY KEY);
 INSERT @recipients SELECT user_id FROM @orders UNION SELECT user_id FROM dbo.favorites WITH(UPDLOCK,HOLDLOCK) WHERE vendor_id=@vendor_id;
 INSERT dbo.notifications(id,user_id,event_key,kind,body,related_vendor_id)
 SELECT CONVERT(varchar(36),NEWID()),r.user_id,'vendor_closed:'+@vendor_id,'vendor_closed',N'店家「'+COALESCE(@name,N'已關閉店家')+N'」已刪帳，相關預約與收藏已移除，請勿再前往取貨。',@vendor_id
 FROM @recipients r WHERE NOT EXISTS(SELECT 1 FROM dbo.notifications n WHERE n.user_id=r.user_id AND n.event_key='vendor_closed:'+@vendor_id);
 INSERT dbo.reservation_terminals(reservation_id,user_id,vendor_id,reason,previous_state,released_quantity)
 SELECT o.id,o.user_id,@vendor_id,'vendor_closed',o.state,0 FROM @orders o;
 UPDATE q SET response=(SELECT o.id AS id,'removed' AS state,'vendor_closed' AS terminal_reason FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)
 FROM dbo.request_results q JOIN @orders o ON JSON_VALUE(q.response,'$.id')=o.id
 WHERE q.operation IN ('reserve','pickup-preview','pickup-confirm','transition');
 -- Remove cached vendor/product text and authority after physical business deletion.
 UPDATE q SET response=(SELECT @vendor_id AS id,'removed' AS state,'vendor_closed' AS terminal_reason FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)
 FROM dbo.request_results q WHERE q.user_id=@vendor_id AND q.operation IN ('product.save','stock-adjust','store-mode','stock-loss');
 UPDATE q SET response=(SELECT @store AS id,'removed' AS state,'vendor_closed' AS terminal_reason FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)
 FROM dbo.request_results q WHERE q.operation='store.create' AND JSON_VALUE(q.response,'$.owner_id')=@vendor_id;
 DELETE r FROM dbo.reviews r JOIN @orders o ON o.id=r.reservation_id;
 DELETE r FROM dbo.reservations r JOIN @orders o ON o.id=r.id;
 DELETE FROM dbo.favorites WHERE vendor_id=@vendor_id;
 DELETE p FROM dbo.products p JOIN @products x ON x.id=p.id;
 DELETE FROM dbo.stores WHERE id=@store AND owner_id=@vendor_id;
 SELECT 'closed' AS outcome,(SELECT COUNT(*) FROM @orders) AS removed_orders;
END;
