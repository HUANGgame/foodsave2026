import {test} from 'node:test';
import assert from 'node:assert/strict';
import {freshState,favorite,reserve,remaining,changeReservation,review,expire,weekStart} from '../lib/demo';
test('reservation prevents duplicate waiting order, cancellation restores inventory',()=>{let s=reserve(freshState(),'rice1',1000);assert.equal(remaining(s,'rice1'),3);assert.throws(()=>reserve(s,'rice1',1001));s=changeReservation(s,s.reservations[0].id,'cancel','',1002);assert.equal(remaining(s,'rice1'),4);assert.equal(s.exp.length,0)});
test('pickup validates code; completed inventory and EXP counted once; completed-only reviews',()=>{let s=reserve(freshState(),'rice1',1000);const r=s.reservations[0];assert.throws(()=>review(s,r.id,5,'好吃'));assert.throws(()=>changeReservation(s,r.id,'complete','000000',1001));s=changeReservation(s,r.id,'complete',r.code,1001);assert.equal(remaining(s,'rice1'),3);assert.equal(s.exp[0].amount,100);assert.throws(()=>changeReservation(s,r.id,'complete',r.code,1002));s=review(s,r.id,5,'好吃',1003);assert.equal(s.exp.reduce((a,e)=>a+e.amount,0),180);assert.throws(()=>review(s,r.id,5,'再次',1004))});
test('expired reservation cannot be completed and gives no EXP',()=>{const s=reserve(freshState(),'bread1',0);const e=expire(s,1800000);assert.equal(e.reservations[0].status,'expired');assert.equal(remaining(e,'bread1'),3);assert.throws(()=>changeReservation(s,s.reservations[0].id,'complete',s.reservations[0].code,1800000));assert.equal(e.exp.length,0)});
test('favorite toggle cannot farm EXP',()=>{let s=favorite(freshState(),'rice');s=favorite(s,'rice');s=favorite(s,'rice');assert.equal(s.exp.length,1);assert.equal(s.exp[0].amount,50)});
test('stock cannot become negative',()=>{let s=freshState();for(let i=0;i<2;i++){s=reserve(s,'bread2',1000);let r=s.reservations.at(-1)!;s=changeReservation(s,r.id,'complete',r.code,1001)}assert.equal(remaining(s,'bread2'),0);assert.throws(()=>reserve(s,'bread2',1002))});
test('week resets at Taipei Monday midnight',()=>{assert.equal(new Date(weekStart(Date.parse('2026-10-04T16:00:00Z'))).toISOString(),'2026-10-04T16:00:00.000Z');assert.equal(new Date(weekStart(Date.parse('2026-10-04T15:59:59Z'))).toISOString(),'2026-09-27T16:00:00.000Z')});

test('merchant creates and updates remaining inventory without altering existing order snapshots',async()=>{
 const {saveProduct,catalog}=await import('../lib/demo');const now=Date.now();
 const input={store:'rice',name:'手作便當',original:100,price:60,quantity:2,kind:'打折',icon:'🍱',availableUntil:now+3600000};
 let s=saveProduct(freshState(),input,undefined,now);const id=catalog(s).at(-1)!.id;
 s=reserve(s,id,now+1);assert.equal(remaining(s,id),1);
 s=saveProduct(s,{...input,name:'新版便當',price:50,quantity:4},id,now+2);
 assert.equal(remaining(s,id),4);assert.equal(s.reservations[0].snapshot!.name,'手作便當');assert.equal(s.reservations[0].snapshot!.price,60);
 s=changeReservation(s,s.reservations[0].id,'cancel','',now+3);assert.equal(remaining(s,id),5);
 assert.throws(()=>saveProduct(s,{...input,quantity:-1},id,now));assert.throws(()=>saveProduct(s,{...input,price:101},id,now));
 assert.throws(()=>saveProduct(s,{...input,availableUntil:now-1},id,now));
});
test('product deadline prevents bookings and caps reservation expiry',async()=>{
 const {saveProduct,catalog}=await import('../lib/demo');const now=Date.now();let s=saveProduct(freshState(),{store:'rice',name:'短效商品',original:20,price:0,quantity:1,kind:'打折',icon:'🍙',availableUntil:now+60000},undefined,now);const id=catalog(s).at(-1)!.id;
 const booked=reserve(s,id,now+1);assert.equal(booked.reservations[0].expires,now+60000);assert.throws(()=>reserve(s,id,now+60001));
});
