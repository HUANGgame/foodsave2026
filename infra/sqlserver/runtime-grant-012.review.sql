-- REVIEW ONLY; owner must replace principal and approve before execution. No new identity.
SET XACT_ABORT ON;
IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;
IF DATABASE_PRINCIPAL_ID(N'REPLACE_WITH_APPROVED_RUNTIME') IS NULL THROW 51000,'Approved existing runtime required',1;
IF NOT EXISTS(SELECT 1 FROM dbo.schema_migrations WHERE version='012_account_lifecycle.sql') THROW 51000,'Owner schema012 required',1;
BEGIN TRANSACTION;
GRANT SELECT,INSERT,DELETE ON OBJECT::dbo.account_challenges TO [REPLACE_WITH_APPROVED_RUNTIME];
GRANT EXECUTE ON OBJECT::dbo.apply_account_password TO [REPLACE_WITH_APPROVED_RUNTIME];
-- No direct password_hash UPDATE, role change, new role membership, DDL or viewer access.
COMMIT;
