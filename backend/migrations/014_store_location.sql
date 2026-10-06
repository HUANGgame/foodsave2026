-- New owner-run source only; not executed or SQL-validated in this rebuild.
-- Existing locations were already public. Preserve them; only NEW stores start
-- as unpublished GPS drafts. Do not rewrite coordinates, owners or sessions.
SET XACT_ABORT ON;
IF @@TRANCOUNT=0 OR XACT_STATE()<>1
 THROW 51000,'Active migration runner transaction required',1;
ALTER TABLE dbo.stores ADD location_revision int NOT NULL
 CONSTRAINT df_stores_location_revision DEFAULT 1 WITH VALUES;
ALTER TABLE dbo.stores ADD location_confirmed bit NOT NULL
 CONSTRAINT df_stores_location_confirmed_existing DEFAULT 1 WITH VALUES;
ALTER TABLE dbo.stores DROP CONSTRAINT df_stores_location_confirmed_existing;
EXEC(N'ALTER TABLE dbo.stores ADD CONSTRAINT df_stores_location_confirmed DEFAULT 0 FOR location_confirmed');
EXEC(N'ALTER TABLE dbo.stores ADD CONSTRAINT ck_stores_location_revision CHECK(location_revision>=1)');
-- No GRANT, role change or automatic deployment. Runtime column UPDATE rights
-- are a separate review requirement before any future release.
