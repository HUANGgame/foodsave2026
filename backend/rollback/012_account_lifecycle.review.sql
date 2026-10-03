-- REVIEW ONLY. Turn OFF lifecycle/registration and stop auth writes before owner execution.
-- Roll back schema only after independently confirming no new verified enrollment or password change.
-- Strong password hashes are NOT converted back; never restore old passwords/sessions.
SET XACT_ABORT ON;
IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;
BEGIN TRANSACTION;
IF EXISTS(SELECT 1 FROM dbo.account_challenges) THROW 51000,'Outstanding challenges require explicit cleanup approval',1;
IF EXISTS(SELECT 1 FROM dbo.users WHERE email_verified_at IS NOT NULL OR password_hash LIKE 'scrypt-v2$%') THROW 51000,'Account changes exist; retain additive schema, use application rollback only',1;
DROP PROCEDURE dbo.apply_account_password;
DROP TABLE dbo.account_challenges;
ALTER TABLE dbo.users DROP COLUMN email_verified_at;
DELETE dbo.schema_migrations WHERE version='012_account_lifecycle.sql';
COMMIT;
