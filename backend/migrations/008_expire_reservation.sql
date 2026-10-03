CREATE PROCEDURE dbo.expire_reservation @reservation_id varchar(36)
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1 THROW 51000,'Active caller transaction required',1;
 DECLARE @product varchar(36),@store varchar(36),@vendor varchar(36),@user varchar(36),@name nvarchar(160),@qty int,@state varchar(12),@expiry datetime2,@lock int;
 SELECT @product=r.product_id,@store=p.store_id FROM dbo.reservations r JOIN dbo.products p ON p.id=r.product_id WHERE r.id=@reservation_id;
 IF @product IS NULL BEGIN SELECT 'absent' AS outcome; RETURN; END;
 DECLARE @resource nvarchar(255)=N'foodsave:store-mode:'+@store;
 EXEC @lock=sp_getapplock @Resource=@resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @lock<0 THROW 51000,'Store operation busy',1;
 SELECT @name=p.name,@vendor=s.owner_id FROM dbo.products p WITH(UPDLOCK,HOLDLOCK) JOIN dbo.stores s ON s.id=p.store_id WHERE p.id=@product;
 SELECT @user=user_id,@qty=quantity,@state=state,@expiry=expires_at FROM dbo.reservations WITH(UPDLOCK,HOLDLOCK) WHERE id=@reservation_id;
 IF @state IS NULL BEGIN SELECT 'absent' AS outcome; RETURN; END;
 IF @state NOT IN ('waiting','expired') OR @expiry>SYSUTCDATETIME() BEGIN SELECT 'not_expired' AS outcome; RETURN; END;
 -- Legacy state=expired already returned stock: migrate to deletion without return.
 DECLARE @release int=CASE WHEN @state='waiting' THEN @qty ELSE 0 END;
 INSERT dbo.reservation_terminals(reservation_id,user_id,vendor_id,reason,previous_state,released_quantity)
 VALUES(@reservation_id,@user,@vendor,'expired',@state,@release);
 INSERT dbo.notifications(id,user_id,event_key,kind,body,related_vendor_id)
 VALUES(CONVERT(varchar(36),NEWID()),@user,'expired:'+@reservation_id,'expired',COALESCE(@name,N'商品')+N'：預約已逾期並移除，請勿再前往取貨。',@vendor);
 IF @release>0 UPDATE dbo.products SET available_quantity=available_quantity+@release,revision=revision+1 WHERE id=@product;
 -- Scrub obsolete capabilities/snapshots but retain original idempotency keys.
 UPDATE q SET response=(SELECT @reservation_id AS id,'expired' AS state,'expired' AS terminal_reason FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)
 FROM dbo.request_results q WHERE q.operation IN ('reserve','pickup-preview','pickup-confirm','transition') AND JSON_VALUE(q.response,'$.id')=@reservation_id;
 DELETE FROM dbo.reviews WHERE reservation_id=@reservation_id;
 DELETE FROM dbo.reservations WHERE id=@reservation_id;
 SELECT 'expired' AS outcome,@release AS released_quantity;
END;
