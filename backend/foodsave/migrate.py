"""Explicit one-way migration runner; never runs when the web service starts."""
from pathlib import Path
from .db import engine, execute, one


def main(database=None):
    with (database or engine()).begin() as conn:
        execute(conn, "DECLARE @r int; EXEC @r=sp_getapplock @Resource='foodsave:migrate', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000; IF @r<0 THROW 51000,'Migration lock unavailable',1;")
        execute(conn, "IF OBJECT_ID('dbo.schema_migrations','U') IS NULL CREATE TABLE dbo.schema_migrations (version varchar(80) PRIMARY KEY, applied_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME())")
        for path in sorted((Path(__file__).parent.parent / 'migrations').glob('*.sql')):
            if not one(conn, 'SELECT version FROM dbo.schema_migrations WHERE version=:v', v=path.name):
                execute(conn, path.read_text())
                execute(conn, 'INSERT INTO dbo.schema_migrations(version) VALUES (:v)', v=path.name)
                print('Applied', path.name)


if __name__ == '__main__':
    main()
