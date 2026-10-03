"""Owner-only synthetic auth012 erasure QA. Plan default; never commit/send mail."""
import argparse
import json
import os
import re
from uuid import uuid4


def safe_error(exc):
    """Never render driver messages, SQL parameters or credentials."""
    result = {'error_class': type(exc).__name__}
    original = getattr(exc, 'orig', exc)
    args = getattr(original, 'args', ())
    if args and isinstance(args[0], str) and re.fullmatch(r'[A-Z0-9]{5}', args[0]):
        result['sqlstate'] = args[0]
    return result


def write_manifest(path, manifest):
    # Exclusive creation rejects symlinks and preserves an earlier recovery record.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def residual_checks(database, manifest):
    from foodsave.db import execute, one
    results = {}
    for table, column, key in [('users', 'id', 'users'), ('account_challenges', 'token_hash', 'tickets'), ('rate_limits', 'bucket', 'buckets')]:
        try:
            # A fresh connection per table still runs when a prior query/connection fails.
            with database.connect() as c:
                c.connection.driver_connection.timeout = 30
                execute(c, "SET LOCK_TIMEOUT 5000")
                params = {f'p{i}': value for i, value in enumerate(manifest[key])}
                placeholders = ','.join(':'+name for name in params)
                row = one(c, f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {column} IN ({placeholders})', **params)
                results[table] = {'residual': int(row['n'])}
        except Exception as exc:
            results[table] = safe_error(exc)
    return results


def suite(database, manifest_path):
    from foodsave.db import execute,one
    from foodsave.erasure import Eraser
    from foodsave.security import digest
    marker=uuid4().hex
    users=[str(uuid4()),str(uuid4())]
    emails=[f'erasure-qa-{marker}-{i}@example.invalid' for i in range(2)]
    tickets=[digest('ticket:'+marker+str(i)) for i in range(2)]
    actions=['login:email','auth:mail:email','auth:finish:email','deletion-public-account']
    buckets=[digest(a+':'+emails[0]) for a in actions]
    sentinels=[digest('login:email:'+emails[1]),digest('auth:password:global:qa-'+marker),digest('auth:mail:global:hour:qa-'+marker),digest('auth:mail:probe:once:v1:'+emails[0])]
    manifest = {'version': 1, 'marker': marker, 'users': users, 'tickets': tickets,
                'buckets': buckets + sentinels}
    write_manifest(manifest_path, manifest)
    worker=Eraser(None,None);checks=[]
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    failures = []
    try:
        with database.connect() as c:
            c.connection.driver_connection.timeout=30
            tx=c.begin()
            try:
                execute(c,'SET XACT_ABORT ON; SET LOCK_TIMEOUT 5000')
                check(one(c,'SELECT DB_NAME() AS n')['n']=='foodsave','dedicated_database')
                check(bool(one(c,"SELECT version FROM dbo.schema_migrations WHERE version='012_account_lifecycle.sql'")),'schema012')
                check(one(c,"SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS n")['n']==1,'existing_owner_only')
                for i in range(2):
                    execute(c,"INSERT dbo.users(id,email,password_hash,role,active,email_verified_at) VALUES(:u,:e,'unusable-qa-marker','consumer',0,SYSUTCDATETIME())",u=users[i],e=emails[i])
                    execute(c,"INSERT dbo.account_challenges(token_hash,email_key,purpose,expires_at) VALUES(:t,:e,'reset',DATEADD(minute,15,SYSUTCDATETIME()))",t=tickets[i],e=digest('account-email:'+emails[i]))
                for i,b in enumerate(buckets+sentinels):
                    execute(c,'INSERT dbo.rate_limits(bucket,attempts,window_start) VALUES(:b,3,DATEADD(second,:age,SYSUTCDATETIME()))',b=b,age=-901 if i in (0,2) else 0)
                execute(c,'SAVE TRANSACTION auth_erasure_injection')
                worker.clear_auth(c,users[0],emails[0])
                # Simulates interruption after auth changes: rollback the same transaction scope.
                execute(c,'ROLLBACK TRANSACTION auth_erasure_injection')
                check(bool(one(c,'SELECT token_hash FROM dbo.account_challenges WHERE token_hash=:t',t=tickets[0])),'rollback_restores_challenge')
                check(one(c,'SELECT email_verified_at AS v FROM dbo.users WHERE id=:u',u=users[0])['v'] is not None,'rollback_restores_verified_time')
                check(bool(one(c,'SELECT bucket FROM dbo.rate_limits WHERE bucket=:b',b=buckets[0])),'rollback_restores_expired_counter')
                worker.clear_auth(c,users[0],emails[0])
                check(not one(c,'SELECT token_hash FROM dbo.account_challenges WHERE token_hash=:t',t=tickets[0]),'own_challenge_removed')
                check(bool(one(c,'SELECT token_hash FROM dbo.account_challenges WHERE token_hash=:t',t=tickets[1])),'other_challenge_preserved')
                check(one(c,'SELECT email_verified_at AS v FROM dbo.users WHERE id=:u',u=users[0])['v'] is None,'own_verified_time_cleared')
                check(one(c,'SELECT email_verified_at AS v FROM dbo.users WHERE id=:u',u=users[1])['v'] is not None,'other_verified_time_preserved')
                for i,b in enumerate(buckets):
                    check(bool(one(c,'SELECT bucket FROM dbo.rate_limits WHERE bucket=:b',b=b))==(i in (1,3)),f'counter_expiry_scope_{i}')
                for b in sentinels:
                    check(one(c,'SELECT attempts FROM dbo.rate_limits WHERE bucket=:b',b=b)['attempts']==3,'unrelated_or_once_counter_preserved')
                for i in (1,3):
                    execute(c,'UPDATE dbo.rate_limits SET window_start=DATEADD(second,-901,SYSUTCDATETIME()) WHERE bucket=:b',b=buckets[i])
                worker.clear_expired_email_counters(c,emails[0])
                check(all(not one(c,'SELECT bucket FROM dbo.rate_limits WHERE bucket=:b',b=b) for b in buckets),'later_expired_own_counters_removed')
            except Exception as exc:
                failures.append({"phase": "fixture", **safe_error(exc)})
            finally:
                try:
                    if tx.is_active:tx.rollback()
                except Exception as exc:
                    failures.append({"phase": "rollback", **safe_error(exc)})
    except Exception as exc:
        failures.append(safe_error(exc))
    residuals = residual_checks(database, manifest)
    passed = not failures and all(r.get('residual') == 0 for r in residuals.values())
    return {'checks': len(checks), 'status': 'passed' if passed else 'failed',
            'errors': failures, 'residual_checks': residuals,
            'scope': 'synthetic auth cleanup/rollback only; no full erasure, mail, backups or concurrency proof'}



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-rollback',action='store_true')
    parser.add_argument('--recovery-manifest', help='New private 0600 JSON file; required for execution')
    parser.add_argument('--server');parser.add_argument('--driver',choices=['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'])
    args=parser.parse_args()
    if not args.run_rollback:
        print('PLAN ONLY:2 synthetic disabled users,2 challenges,8 counters; existing owner; always rollback; no grants/mail/commit.')
        return 0
    if not args.server or not args.driver or not args.recovery_manifest:parser.error('Explicit server, installed driver and new recovery manifest path required')
    from owner_migrate import owner_database
    database=None
    try:
        database=owner_database(args.server,args.driver)
        result = suite(database, args.recovery_manifest)
        print(json.dumps(result))
        return 0 if result['status'] == 'passed' else 1
    except Exception as exc:
        print(json.dumps({'status': 'failed', **safe_error(exc), 'acceptance': False}))
        return 1
    finally:
        if database is not None:database.dispose()


if __name__=='__main__':raise SystemExit(main())
