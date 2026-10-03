-- REVIEW/RUN ONLY on the approved foodsave DB using the approved runtime.
-- Synthetic transaction only; never commits or sends mail. Not concurrency proof.
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;
IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;
IF @@TRANCOUNT<>0 THROW 51000,'Standalone session required',1;
DECLARE @u varchar(36)=CONVERT(varchar(36),NEWID());
DECLARE @email nvarchar(254)=N'auth012-qa-'+@u+N'@example.invalid';
DECLARE @t char(64)=CONVERT(char(64),HASHBYTES('SHA2_256',CONVERT(varchar(36),NEWID())),2);
DECLARE @e char(64)=CONVERT(char(64),HASHBYTES('SHA2_256',@email),2);
DECLARE @s char(64)=CONVERT(char(64),HASHBYTES('SHA2_256',CONVERT(varchar(36),NEWID())),2);
-- Deliberately unusable password markers, no real password or raw bearer token.
DECLARE @old varchar(256)='scrypt-v2$synthetic-old$unusable';
DECLARE @new varchar(256)='scrypt-v2$synthetic-new$unusable';
DECLARE @result TABLE(changed int);
BEGIN TRY
 BEGIN TRANSACTION;
 INSERT dbo.users(id,email,password_hash,role) VALUES(@u,@email,@old,'consumer');
 INSERT dbo.sessions(token_hash,user_id,expires_at) VALUES(@s,@u,DATEADD(minute,1,SYSUTCDATETIME()));
 INSERT dbo.account_challenges(token_hash,email_key,purpose,expires_at) VALUES(@t,@e,'reset',DATEADD(minute,15,SYSUTCDATETIME()));
 IF NOT EXISTS(SELECT 1 FROM dbo.account_challenges WITH(UPDLOCK,HOLDLOCK) WHERE token_hash=@t AND email_key=@e AND purpose='reset' AND expires_at>SYSUTCDATETIME()) THROW 51000,'Challenge assertion failed',1;
 INSERT @result EXEC dbo.apply_account_password @u,'wrong-expected-hash',@new,1;
 IF NOT EXISTS(SELECT 1 FROM @result WHERE changed=0) OR NOT EXISTS(SELECT 1 FROM dbo.sessions WHERE token_hash=@s) THROW 51000,'Expected-hash guard failed',1;
 DELETE @result;
 INSERT @result EXEC dbo.apply_account_password @u,@old,@new,1;
 IF NOT EXISTS(SELECT 1 FROM @result WHERE changed=1) THROW 51000,'Password mutation failed',1;
 IF EXISTS(SELECT 1 FROM dbo.sessions WHERE user_id=@u) THROW 51000,'Session revocation failed',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.users WHERE id=@u AND password_hash=@new AND email_verified_at IS NOT NULL AND role='consumer') THROW 51000,'User mutation assertion failed',1;
 DELETE dbo.account_challenges WHERE email_key=@e;
 IF EXISTS(SELECT 1 FROM dbo.account_challenges WHERE token_hash=@t) THROW 51000,'Challenge consumption failed',1;
 ROLLBACK TRANSACTION;
 IF EXISTS(SELECT 1 FROM dbo.users WHERE id=@u) OR EXISTS(SELECT 1 FROM dbo.sessions WHERE token_hash=@s) OR EXISTS(SELECT 1 FROM dbo.account_challenges WHERE token_hash=@t) THROW 51000,'Rollback residual detected',1;
 SELECT 'PASS: synthetic procedure/hash guard/session revocation/challenge deletion/rollback; NOT concurrency or email evidence' AS result;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
