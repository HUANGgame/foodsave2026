-- Owner-only, transactionally applied after006. No runtime privilege changes.
IF EXISTS(SELECT 1 FROM dbo.favorites f LEFT JOIN dbo.stores s ON s.id=f.store_id WHERE s.owner_id IS NULL)
 THROW 51000, 'Unmapped favorites require review; no automatic data loss', 1;
CREATE TABLE dbo.notifications (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 event_key varchar(120) NOT NULL,
 kind varchar(32) NOT NULL CHECK(kind IN ('expired','vendor_closed','vendor_out_of_stock')),
 body nvarchar(400) NOT NULL,
 related_vendor_id varchar(36) NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 read_at datetime2 NULL,
 expires_at datetime2 NOT NULL DEFAULT DATEADD(day,30,SYSUTCDATETIME()),
 UNIQUE(user_id,event_key)
);
CREATE INDEX ix_notifications_inbox ON dbo.notifications(user_id,created_at);
CREATE TABLE dbo.reservation_terminals (
 reservation_id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 vendor_id varchar(36) NULL,
 reason varchar(32) NOT NULL CHECK(reason IN ('expired','vendor_closed','vendor_out_of_stock')),
 previous_state varchar(12) NOT NULL,
 released_quantity int NOT NULL CHECK(released_quantity>=0),
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 expires_at datetime2 NOT NULL DEFAULT DATEADD(day,30,SYSUTCDATETIME())
);
CREATE INDEX ix_reservation_terminals_user ON dbo.reservation_terminals(user_id);
-- Preserve favorite rows, replacing store identity with its unique vendor account.
ALTER TABLE dbo.favorites ADD vendor_id varchar(36) NULL;
EXEC(N'UPDATE f SET vendor_id=s.owner_id FROM dbo.favorites f JOIN dbo.stores s ON s.id=f.store_id');
DECLARE @fk sysname,@pk sysname;
SELECT @fk=fk.name FROM sys.foreign_keys fk JOIN sys.foreign_key_columns c ON c.constraint_object_id=fk.object_id
 WHERE fk.parent_object_id=OBJECT_ID('dbo.favorites') AND COL_NAME(c.parent_object_id,c.parent_column_id)='store_id';
SELECT @pk=name FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID('dbo.favorites') AND type='PK';
IF @fk IS NULL OR @pk IS NULL THROW 51000,'Unexpected favorites constraints',1;
EXEC(N'ALTER TABLE dbo.favorites DROP CONSTRAINT '+QUOTENAME(@fk));
EXEC(N'ALTER TABLE dbo.favorites DROP CONSTRAINT '+QUOTENAME(@pk));
EXEC(N'ALTER TABLE dbo.favorites DROP COLUMN store_id');
EXEC(N'ALTER TABLE dbo.favorites ALTER COLUMN vendor_id varchar(36) NOT NULL');
EXEC(N'ALTER TABLE dbo.favorites ADD CONSTRAINT pk_favorites_account PRIMARY KEY(user_id,vendor_id)');
EXEC(N'ALTER TABLE dbo.favorites ADD CONSTRAINT fk_favorites_vendor FOREIGN KEY(vendor_id) REFERENCES dbo.users(id)');
-- Preserve anti-farming keys when migrating favorites to the same vendor identity.
UPDATE e SET event_key=LEFT(e.event_key,LEN(e.event_key)-36)+s.owner_id
 FROM dbo.exp_events e JOIN dbo.stores s ON RIGHT(e.event_key,36)=s.id
 WHERE e.event_key LIKE 'favorite:%' AND s.owner_id IS NOT NULL;
