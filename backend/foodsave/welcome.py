"""One lifetime login grant per account, within the authenticated login transaction."""
from .db import execute, one
from uuid import uuid4

PREFIX = 'welcome:first-login:v1:'


def grant_once(c, user_id):
    # Existing unique source_key index plus serializable range lock. No reset on logout.
    key = PREFIX + user_id
    execute(c, """INSERT INTO dbo.spin_grants(id,user_id,source_key,remaining,expires_at)
        SELECT :id,:u,:key,1,CAST('9999-12-31T23:59:59' AS datetime2)
        WHERE NOT EXISTS (SELECT 1 FROM dbo.spin_grants WITH(UPDLOCK,HOLDLOCK)
                          WHERE source_key=:key)""", id=str(uuid4()),u=user_id,key=key)


def status(c, user_id):
    row=one(c,'SELECT remaining FROM dbo.spin_grants WHERE user_id=:u AND source_key=:key',u=user_id,key=PREFIX+user_id)
    return {'welcome_spin_awarded': row is not None, 'welcome_spin_available': row['remaining'] if row else 0}
