-- CANDIDATE: owner review/approval required. No automatic deployment or registration enablement.
IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;
ALTER TABLE dbo.users ADD email_verified_at datetime2 NULL;
-- Existing users stay unverified (NULL); no fabricated verification or forced lockout.
CREATE TABLE dbo.account_challenges (
 token_hash char(64) NOT NULL PRIMARY KEY,
 email_key char(64) NOT NULL,
 purpose varchar(16) NOT NULL CHECK(purpose IN ('register','reset')),
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 expires_at datetime2 NOT NULL,
 CHECK(expires_at>created_at)
);
CREATE UNIQUE INDEX ix_account_challenge_email_purpose ON dbo.account_challenges(email_key,purpose);
CREATE INDEX ix_account_challenge_expiry ON dbo.account_challenges(expires_at);
-- EXEC permits CREATE PROCEDURE without GO inside the existing transaction runner.
EXEC(N'CREATE PROCEDURE dbo.apply_account_password
 @user_id varchar(36),@expected_hash varchar(256),@new_hash varchar(256),@verify_email bit
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 IF @@TRANCOUNT=0 OR XACT_STATE()<>1 THROW 51000,''Active caller transaction required'',1;
 IF @new_hash NOT LIKE ''scrypt-v2$%'' THROW 51000,''Strong password hash required'',1;
 UPDATE dbo.users WITH(UPDLOCK,HOLDLOCK)
 SET password_hash=@new_hash,email_verified_at=CASE WHEN @verify_email=1 THEN SYSUTCDATETIME() ELSE email_verified_at END
 WHERE id=@user_id AND active=1 AND password_hash=@expected_hash;
 DECLARE @changed int=@@ROWCOUNT;
 IF @changed=1 DELETE dbo.sessions WHERE user_id=@user_id;
 SELECT @changed AS changed;
END;');
