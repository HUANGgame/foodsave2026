from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .db import execute, one, rows
from .service import Service, uid


def previous_week(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Taipei'))
    end = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.weekday())
    start = end - timedelta(days=7)
    return start.date().isoformat(), start.astimezone(timezone.utc).replace(tzinfo=None), end.astimezone(timezone.utc).replace(tzinfo=None)


class RankingService(Service):
    def settle_previous_week(self):
        with self.transaction() as c:
            execute(c, "DECLARE @r int; EXEC @r=sp_getapplock @Resource='foodsave:weekly', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000; IF @r<0 THROW 51000,'Ranking lock unavailable',1;")
            now = one(c, 'SELECT SYSUTCDATETIME() AS now')['now'].replace(tzinfo=timezone.utc)
            week, start, end = previous_week(now)
            if one(c, 'SELECT week_key FROM dbo.weekly_settlements WHERE week_key=:w', w=week):
                return {'week': week, 'already_settled': True}
            rules = rows(c, 'SELECT start_rank,end_rank,spins FROM dbo.ranking_rules WITH(HOLDLOCK) ORDER BY start_rank')
            results = rows(c, "SELECT e.user_id,SUM(CAST(e.amount AS bigint)) AS exp FROM dbo.exp_events e JOIN dbo.users u ON u.id=e.user_id WHERE e.occurred_at>=:start AND e.occurred_at<:end AND u.active=1 AND u.role='consumer' GROUP BY e.user_id HAVING SUM(CAST(e.amount AS bigint))>0 ORDER BY SUM(CAST(e.amount AS bigint)) DESC,e.user_id OFFSET 0 ROWS FETCH NEXT 10000 ROWS ONLY", start=start, end=end)
            execute(c, 'INSERT INTO dbo.weekly_settlements(week_key,starts_at,ends_at) VALUES(:w,:s,:e)', w=week, s=start, e=end)
            for rank, row in enumerate(results, 1):
                spins = next((r['spins'] for r in rules if r['start_rank'] <= rank <= r['end_rank']), 0)
                execute(c, 'INSERT INTO dbo.weekly_rankings(week_key,user_id,rank,exp,spins) VALUES(:w,:u,:r,:e,:s)', w=week, u=row['user_id'], r=rank, e=row['exp'], s=spins)
                if spins:
                    execute(c, 'INSERT INTO dbo.spin_grants(id,user_id,source_key,remaining,expires_at) VALUES(:id,:u,:source,:n,:expiry)', id=uid(), u=row['user_id'], source='week:'+week+':'+row['user_id'], n=spins, expiry=end+timedelta(days=7))
            return {'week': week, 'ranked_users': len(results), 'already_settled': False}
