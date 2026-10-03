"""Schema011 restricted-runtime SQL acceptance. Plan by default, synthetic, always rollback.
Direct Service calls, not HTTP, concurrency, Android or deployed API proof.
"""
import argparse
from contextlib import contextmanager
from datetime import timedelta
import json
import secrets
from uuid import UUID, uuid4, uuid5

class AcceptanceFailure(Exception): pass
class Pinned:
    def __init__(self,c):self.c=c
    @contextmanager
    def begin(self):yield self.c

def suite(database,run):
    from fastapi import HTTPException
    from foodsave.db import execute,one
    from foodsave.admin import AdminService
    from foodsave.security import hash_password,digest
    from foodsave.service import dump
    ids={n:str(uuid5(run,'terminal:'+n)) for n in ('consumer','follower','vendor','other','store','product','expired','completed')}
    results=[];password=secrets.token_urlsafe(32)
    def check(value,name):
        if not value:raise AcceptanceFailure(name)
        results.append(name)
    def denied(action,status,name):
        try:action()
        except HTTPException as e:check(e.status_code==status,name)
        else:raise AcceptanceFailure(name)
    with database.connect() as c:
        tx=c.begin()
        try:
            execute(c,'SET LOCK_TIMEOUT 10000')
            check(one(c,'SELECT DB_NAME() AS name')['name']=='foodsave','dedicated_database')
            check(bool(one(c,"SELECT version FROM dbo.schema_migrations WHERE version='011_mark_notification_read.sql'")),'schema011_present')
            rights=one(c,"SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS owner,HAS_PERMS_BY_NAME('dbo.users','OBJECT','DELETE') AS erase,HAS_PERMS_BY_NAME('dbo.reservations','OBJECT','DELETE') AS orders,HAS_PERMS_BY_NAME('dbo.notifications','OBJECT','INSERT') AS notices")
            check(all(rights[n]==0 for n in ('owner','erase','orders','notices')),'runtime_has_no_direct_destructive_grants')
            for proc in ('expire_reservation','close_vendor_business','report_stock_loss','mark_notification_read'):
                check(one(c,"SELECT HAS_PERMS_BY_NAME(:p,'OBJECT','EXECUTE') AS allowed",p='dbo.'+proc)['allowed']==1,'execute_'+proc)
            now=one(c,'SELECT SYSUTCDATETIME() AS now')['now'];marker='foodsave-qa:'+run.hex
            for name in ('consumer','follower','vendor','other'):
                email=f'qa+{run.hex}.{name}@example.invalid'
                check(not one(c,'SELECT id FROM dbo.users WHERE id=:id OR email=:e',id=ids[name],e=email),'fresh_'+name)
                execute(c,'INSERT dbo.users(id,email,password_hash,role) VALUES(:id,:e,:h,:r)',id=ids[name],e=email,h=hash_password(password),r='vendor' if name in ('vendor','other') else 'consumer')
            execute(c,"INSERT dbo.stores(id,owner_id,name,latitude,longitude,service_mode) VALUES(:s,:v,:n,0,0,'reservation')",s=ids['store'],v=ids['vendor'],n=marker)
            execute(c,"INSERT dbo.products(id,store_id,name,photo_url,original_price_minor,sale_price_minor,available_quantity,pickup_deadline,active) VALUES(:p,:s,:n,'https://images.example.invalid/qa.png',100,50,2,:expiry,1)",p=ids['product'],s=ids['store'],n=marker,expiry=now+timedelta(minutes=10))
            service=AdminService(Pinned(c));consumer={'id':ids['consumer'],'role':'consumer'};vendor={'id':ids['vendor'],'role':'vendor'};other={'id':ids['other'],'role':'vendor'}
            stock=lambda:one(c,'SELECT available_quantity AS n FROM dbo.products WHERE id=:p',p=ids['product'])['n']
            key=str(uuid4());order=service.reserve(consumer,key,ids['product'],1)
            check(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=order['id'])['outcome']=='not_expired' and stock()==1,'server_time_prevents_early_expiry')
            denied(lambda:service.report_stock_loss(other,str(uuid4()),ids['product'],dict(expected_revision=1,expected_pending=1,actual_available=0)),404,'other_vendor_cannot_report_loss')
            preview=service.stock_loss_preview(vendor,ids['product']);body=dict(expected_revision=preview['revision'],expected_pending=2,actual_available=0)
            denied(lambda:service.report_stock_loss(vendor,str(uuid4()),ids['product'],body),409,'changed_pending_count_blocks_loss')
            check(stock()==1 and bool(one(c,'SELECT id FROM dbo.reservations WHERE id=:id',id=order['id'])),'rejected_loss_preserves_order_stock')
            body['expected_pending']=1;losskey=str(uuid4());loss=service.report_stock_loss(vendor,losskey,ids['product'],body)
            check(loss['cancelled_count']==1 and stock()==0,'loss_keeps_actual_zero')
            check(not one(c,'SELECT id FROM dbo.reservations WHERE id=:id',id=order['id']),'loss_physically_removes_order')
            check(service.report_stock_loss(vendor,losskey,ids['product'],body)==loss and stock()==0,'loss_same_key_no_return')
            check(service.transition(consumer,str(uuid4()),order['id'],'cancelled')['terminal_reason']=='vendor_out_of_stock' and stock()==0,'late_cancel_no_return')
            check(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=order['id'])['outcome']=='absent' and stock()==0,'late_expiry_no_return')
            denied(lambda:service.reserve(consumer,key,ids['product'],1),410,'original_reserve_key_does_not_resurrect')
            notice=service.notifications(consumer)[0]
            denied(lambda:service.mark_notification_read({'id':ids['follower']},notice['id']),404,'cannot_mark_other_inbox')
            check(service.mark_notification_read(consumer,notice['id'])['read'],'own_notice_read')
            check(not one(c,'SELECT id FROM dbo.exp_events WHERE user_id=:u',u=ids['consumer']),'loss_no_exp_or_penalty')
            for name,state in (('expired','waiting'),('completed','completed')):
                execute(c,'INSERT dbo.reservations(id,user_id,product_id,state,quantity,snapshot,pickup_code_hash,expires_at) VALUES(:id,:u,:p,:state,1,:snapshot,:hash,:expiry)',id=ids[name],u=ids['consumer'],p=ids['product'],state=state,snapshot=dump({'name':marker,'sale_price_minor':50}),hash=digest(secrets.token_hex(6)),expiry=now-timedelta(seconds=1))
            check(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=ids['completed'])['outcome']=='not_expired','completed_order_not_expired')
            check(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=ids['expired'])['outcome']=='expired' and stock()==1,'expired_returns_once_then_deletes')
            check(one(c,'EXEC dbo.expire_reservation @reservation_id=:id',id=ids['expired'])['outcome']=='absent' and stock()==1,'expired_retry_no_second_return')
            for name in ('consumer','follower'):
                execute(c,'INSERT dbo.favorites(user_id,vendor_id) VALUES(:u,:v)',u=ids[name],v=ids['vendor'])
            check(one(c,'EXEC dbo.close_vendor_business @vendor_id=:v',v=ids['vendor'])['outcome']=='deletion_required','active_vendor_cannot_be_closed')
            deleted=service.request_deletion(vendor,password)
            check(deleted['account_disabled'] and not deleted['erasure_completed'],'password_verified_account_disabled')
            for table,column,name in (('stores','id','store'),('products','id','product'),('reservations','product_id','product'),('favorites','vendor_id','vendor')):
                check(one(c,f'SELECT COUNT(*) AS n FROM dbo.{table} WHERE {column}=:id',id=ids[name])['n']==0,'closure_removed_'+table)
            check(one(c,"SELECT COUNT(id) AS n FROM dbo.notifications WHERE event_key=:k",k='vendor_closed:'+ids['vendor'])['n']==2,'customer_follower_union_deduplicated')
            check(one(c,'EXEC dbo.close_vendor_business @vendor_id=:v',v=ids['vendor'])['outcome']=='closed','closure_retry_stable')
        finally:tx.rollback()
    with database.connect() as c:
        for table,col in (('users','id'),('request_results','user_id'),('notifications','user_id'),('reservation_terminals','user_id'),('favorites','user_id'),('deletion_requests','user_id')):
            check(one(c,f'SELECT COUNT({col}) AS n FROM dbo.{table} WHERE {col} IN (:a,:b,:v,:o)',a=ids['consumer'],b=ids['follower'],v=ids['vendor'],o=ids['other'])['n']==0,'rollback_zero_'+table)
    return results

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');parser.add_argument('--approved-quiet-window',action='store_true');parser.add_argument('--run-id',type=UUID);args=parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(mode='plan',db_access=False,accounts_in_rollback=4,commits=0,requires=['schema011','reviewed exact runtime grants','approved quiet window','fresh UUID'],not_covered=['HTTP','concurrency','notification SQL failure injection','Android'])));return
    if not args.approved_quiet_window or not args.run_id:parser.error('Explicit approved quiet window and fresh run UUID required')
    from foodsave.db import engine
    database=engine()
    try:
        checks=suite(database,args.run_id);print(json.dumps(dict(status='passed',assertions=checks,count=len(checks),committed_fixtures=False)))
    except Exception as e:
        print(json.dumps(dict(status='failed',error_type=type(e).__name__,failed_assertion=str(e) if isinstance(e,AcceptanceFailure) else None,rollback_requested=True)));raise SystemExit(1)
    finally:database.dispose()
if __name__=='__main__':main()
