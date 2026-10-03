import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CACHE_MS,FamilySource,normalizeFamily,PUBLIC_AREA,quantity,sourceTime} from '../lib/familymart';
const payload=()=>({code:1,data:[{oldPKey:'001234',name:'合成測試門市',address:'測試地址',latitude:25.03,longitude:121.56,updateDate:'2026-10-03 19:10:01',info:[{categories:[{name:'餐盒',qty:50,products:[{code:'0007',name:'合成便當',qty:2},{code:'0008',name:'未回報數量商品'}]}]}]}]});
test('FamilyMart requires exact success status/code/data and preserves unknown quantities and leading zeros',()=>{
 const [store]=normalizeFamily(200,payload());assert.equal(store.id,'001234');assert.equal(store.products[0].id,'0007');assert.equal(store.products[0].quantity,2);assert.equal(store.products[1].quantity,null);assert.equal(store.quantity,null);assert.equal(store.sourceUpdatedAt,'2026-10-03T19:10:01+08:00');
 for(const response of [{code:0,data:[]},{code:'1',data:[]},{code:1},{code:1,data:null}])assert.throws(()=>normalizeFamily(200,response));
 for(const status of [401,403,429,500])assert.throws(()=>normalizeFamily(status,payload()));
 for(const value of [undefined,null,'',-1,2.5,'unknown',false])assert.equal(quantity(value),null);
 assert.equal(sourceTime('unknown'),null);assert.equal(quantity('0'),0);
});
test('category totals are never added, missing store/product disappears on a new successful response',()=>{
 const source=payload();source.data[0].info[0].categories[0].products=[{code:'0007',name:'合成便當',qty:2}];
 assert.equal(normalizeFamily(200,source)[0].quantity,2);
 assert.deepEqual(normalizeFamily(200,{code:1,data:[]}),[]);
 source.data[0].info=[];assert.equal(normalizeFamily(200,source)[0].quantity,null);
});
test('query cache survives reload, coalesces requests and never retries blocked sources during 30 minutes',async()=>{
 let now=Date.parse('2026-10-03T11:35:00Z'),calls=0;const storage=new Map<string,string>();const disk={getItem:(k:string)=>storage.get(k)||null,setItem:(k:string,v:string)=>{storage.set(k,v);}};
 const transport=async()=>{calls++;return {status:403,data:{}};};
 const source=new FamilySource(disk,transport,()=>now);const [a,b]=await Promise.all([source.query(),source.query()]);assert.equal(calls,1);assert.equal(a.status,'unavailable');assert.deepEqual(a.stores,[]);assert.deepEqual(a,b);
 const reopened=new FamilySource(disk,transport,()=>now);await reopened.query();assert.equal(calls,1);now+=CACHE_MS;await reopened.query();assert.equal(calls,2);
 assert.equal(PUBLIC_AREA.latitude,25.0375197);
});
test('failure retains explicitly old snapshot; successful empty response clears it',async()=>{
 let now=Date.parse('2026-10-03T11:35:00Z'),step=0;
 const source=new FamilySource(undefined,async()=>step++===0?{status:200,data:payload()}:step===2?{status:429,data:{}}:{status:200,data:{code:1,data:[]}},()=>now);
 const good=await source.query();now+=CACHE_MS;const failed=await source.query();assert.equal(failed.status,'unavailable');assert.equal(failed.stores.length,1);assert.equal(failed.lastSuccessAt,good.checkedAt);assert.notEqual(failed.checkedAt,failed.lastSuccessAt);
 now+=CACHE_MS;const empty=await source.query();assert.equal(empty.status,'ok');assert.deepEqual(empty.stores,[]);
});
test('area caches are isolated and nearby coordinates/results are never persisted',async()=>{
 const storage=new Map<string,string>();const disk={getItem:(k:string)=>storage.get(k)||null,setItem:(k:string,v:string)=>{storage.set(k,v);}};
 let calls=0;const transport=async()=>{calls++;return {status:200,data:payload()};};
 const area={id:'other-public',name:'公開中心',latitude:22.625,longitude:120.314};
 await new FamilySource(disk,transport,Date.now,PUBLIC_AREA).query();
 const other=new FamilySource(disk,transport,Date.now,area);assert.deepEqual(other.current().stores,[]);await other.query();assert.equal(calls,2);assert.equal(storage.size,2);
 await new FamilySource(disk,transport,Date.now,area).query();assert.equal(calls,2);
 const nearby=new FamilySource(disk,transport,Date.now,{...area,id:'nearby-session',nearby:true});await nearby.query();await nearby.query();assert.equal(calls,3);assert.equal(storage.size,2);
});
