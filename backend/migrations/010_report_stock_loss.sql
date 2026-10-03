CREATE PROCEDURE dbo.report_stock_loss
 @vendor_id varchar(36),@product_id varchar(36),@expected_revision int,@expected_pending int,@actual_available int
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1 THROW 51000,'Active caller transaction required',1;
 IF @actual_available IS NULL OR @expected_revision IS NULL OR @expected_pending IS NULL OR @expected_revision<1 OR @actual_available<0 OR @actual_available>1000000 OR @expected_pending<0
 BEGIN SELECT 'invalid' AS outcome; RETURN; END;
 DECLARE @store varchar(36),@name nvarchar(160),@revision int,@lock int;
 SELECT @store=p.store_id FROM dbo.products p JOIN dbo.stores s ON s.id=p.store_id JOIN dbo.users u ON u.id=s.owner_id WHERE p.id=@product_id AND s.owner_id=@vendor_id AND u.role='vendor' AND u.active=1;
 IF @store IS NULL BEGIN SELECT 'not_found' AS outcome; RETURN; END;
 DECLARE @resource nvarchar(255)=N'foodsave:store-mode:'+@store;
 EXEC @lock=sp_getapplock @Resource=@resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @lock<0 THROW 51000,'Store operation busy',1;
 SELECT @name=name,@revision=revision FROM dbo.products WITH(UPDLOCK,HOLDLOCK) WHERE id=@product_id;
 DECLARE @orders TABLE(id varchar(36) PRIMARY KEY,user_id varchar(36));
 INSERT @orders SELECT id,user_id FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE product_id=@product_id AND state='waiting';
 IF @revision<>@expected_revision OR (SELECT COUNT(*) FROM @orders)<>@expected_pending
 BEGIN SELECT 'conflict' AS outcome; RETURN; END;
 INSERT dbo.reservation_terminals(reservation_id,user_id,vendor_id,reason,previous_state,released_quantity)
 SELECT id,user_id,@vendor_id,'vendor_out_of_stock','waiting',0 FROM @orders;
 INSERT dbo.notifications(id,user_id,event_key,kind,body,related_vendor_id)
 SELECT CONVERT(varchar(36),NEWID()),user_id,'vendor_out_of_stock:'+id,'vendor_out_of_stock',@name+N'：很抱歉，店家確認此商品已售完，這次預約無法提供。請勿再前往取貨。',@vendor_id FROM @orders;
 UPDATE q SET response=(SELECT o.id AS id,'removed' AS state,'vendor_out_of_stock' AS terminal_reason FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)
 FROM dbo.request_results q JOIN @orders o ON JSON_VALUE(q.response,'$.id')=o.id
 WHERE q.operation IN ('reserve','pickup-preview','pickup-confirm','transition');
 -- Lost physical units never re-enter available inventory. No EXP or penalty.
 UPDATE dbo.products SET available_quantity=@actual_available,revision=revision+1 WHERE id=@product_id;
 DELETE r FROM dbo.reviews r JOIN @orders o ON o.id=r.reservation_id;
 DELETE r FROM dbo.reservations r JOIN @orders o ON o.id=r.id;
 SELECT 'applied' AS outcome,@product_id AS id,@actual_available AS available_quantity,@revision+1 AS revision,(SELECT COUNT(*) FROM @orders) AS cancelled_count;
END;
