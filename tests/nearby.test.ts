import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FoodApi,RequestCancelled} from '../lib/api';
import {allNearby,nearbyCatalog} from '../lib/nearby';
import {snapshotNavigation} from '../lib/location';

test('nearby pagination includes rows beyond 200 and preserves one query center',async()=>{
 const api=new FoodApi('https://example.test');const paths:string[]=[];
 api.request=async <T,>(path:string)=>{paths.push(path);const p=new URL(path,api.base).searchParams;const offset=Number(p.get('cursor')||0);return {items:Array.from({length:100},(_,i)=>({id:String(offset+i)})),radius_m:1000,next_cursor:offset<200?String(offset+100):null} as T;};
 const rows=await allNearby(api,'products',[25.123,121.456]);assert.equal(rows.length,300);assert.equal(rows[299].id,'299');for(const path of paths){const p=new URL(path,api.base).searchParams;assert.equal(p.get('latitude'),'25.123');assert.equal(p.get('longitude'),'121.456');assert.equal(p.get('limit'),'100');}
});
test('cursor loops and partial failures never return a partial catalog',async()=>{
 const api=new FoodApi('https://example.test');api.request=async <T,>()=>({items:[{id:'one'}],radius_m:1000,next_cursor:'repeat'}) as T;
 await assert.rejects(allNearby(api,'stores',[25,121]),/分頁未完成/);
 api.request=async <T,>(path:string)=>{if(path.includes('products'))throw new Error('offline');return {items:[{id:'one'}],radius_m:1000,next_cursor:null} as T;};
 await assert.rejects(nearbyCatalog(api,[25,121]),/offline/);
});
test('aborted or superseded account reads cannot publish nearby results',async()=>{
 const api=new FoodApi('https://example.test'),controller=new AbortController();api.request=async <T,>()=>{controller.abort();return {items:[{id:'old'}],radius_m:1000,next_cursor:null} as T;};
 await assert.rejects(allNearby(api,'stores',[25,121],controller.signal),RequestCancelled);
 api.request=async <T,>()=>{api.clear();return {items:[],radius_m:1000,next_cursor:null} as T;};await assert.rejects(allNearby(api,'stores',[25,121]),RequestCancelled);
});
test('historical navigation uses only valid order snapshot coordinates',()=>{
 assert.match(snapshotNavigation(JSON.stringify({latitude:25,longitude:121,location_revision:2}))!,/destination=25,121/);
 for(const data of [null,{},'{broken',{latitude:null,longitude:121},{latitude:91,longitude:121},{latitude:25,longitude:Infinity}])assert.equal(snapshotNavigation(data),null);
});
test('explicit request cancellation ignores a fetch implementation that returns late',async()=>{
 const original=globalThis.fetch,controller=new AbortController();globalThis.fetch=async()=>{controller.abort();return Response.json({id:'late'});};try{await assert.rejects(new FoodApi('https://example.test').request('/late','GET',undefined,undefined,controller.signal),RequestCancelled);}finally{globalThis.fetch=original;}
});
