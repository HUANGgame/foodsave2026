import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {FoodApi,ApiError} from '../lib/api';

test('a late old-session response cannot clear or overwrite a newer login',async()=>{
 const original=globalThis.fetch;let resolveOld!:(r:Response)=>void;const session=randomUUID();
 globalThis.fetch=async(input)=>{const path=new URL(String(input)).pathname;if(path==='/auth/login')return Response.json({access_token:session});if(path==='/me')return Response.json({id:'user',role:'consumer'});return new Promise<Response>(r=>{resolveOld=r;});};
 try{const api=new FoodApi('https://example.test');await api.login('first@example.test',randomUUID());const old=api.request('/pending');await api.login('second@example.test',randomUUID());resolveOld(Response.json({detail:'old session expired'},{status:401}));await assert.rejects(old,(e:unknown)=>e instanceof ApiError&&e.status===401);assert.equal(api.authenticated,true);}finally{globalThis.fetch=original;}
});

test('draw retry keeps original intent after a lost reply and never stores token',async()=>{
 const original=globalThis.fetch,descriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage'),stored=new Map<string,string>(),keys:string[]=[],session=randomUUID();let attempts=0;
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(k:string)=>stored.get(k)??null,setItem:(k:string,v:string)=>stored.set(k,v),removeItem:(k:string)=>stored.delete(k)}});
 globalThis.fetch=async(input,init)=>{const path=new URL(String(input)).pathname;if(path==='/auth/login')return Response.json({access_token:session});if(path==='/me')return Response.json({id:'user',role:'consumer'});keys.push((init!.headers as Record<string,string>)['Idempotency-Key']);if(++attempts===1)throw new TypeError('simulated lost response');return Response.json({id:'same-result'});};
 try{const api=new FoodApi('https://example.test');await api.login('member@example.test',randomUUID());await assert.rejects(api.mutate('draw','/draws',{}));assert.equal(api.hasPending('draw'),true);assert.ok(!JSON.stringify([...stored]).includes(session));await api.mutate('draw','/draws',{});assert.equal(keys[0],keys[1]);assert.equal(api.hasPending('draw'),false);}finally{globalThis.fetch=original;if(descriptor)Object.defineProperty(globalThis,'localStorage',descriptor);else Reflect.deleteProperty(globalThis,'localStorage');}
});

test('offline logout clears local authentication and next account stays separate',async()=>{
 const original=globalThis.fetch;let identity='first';
 globalThis.fetch=async(input)=>{const path=new URL(String(input)).pathname;if(path==='/auth/login')return Response.json({access_token:randomUUID()});if(path==='/me')return Response.json({id:identity,role:'consumer'});throw new TypeError('offline');};
 try{const api=new FoodApi('https://example.test');await api.login('first@example.test',randomUUID());await assert.rejects(api.logout());assert.equal(api.authenticated,false);identity='second';assert.equal((await api.login('second@example.test',randomUUID())).id,'second');assert.equal(api.authenticated,true);}finally{globalThis.fetch=original;}
});

test('guarded store reconciliation after restart clears only that account intent after successful read',async()=>{
 const original=globalThis.fetch,descriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage'),stored=new Map<string,string>();let revision=2,fail=true,identity='owner';
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(k:string)=>stored.get(k)??null,setItem:(k:string,v:string)=>stored.set(k,v),removeItem:(k:string)=>stored.delete(k)}});
 globalThis.fetch=async(input,init)=>{const path=new URL(String(input)).pathname;if(path==='/auth/login')return Response.json({access_token:'synthetic'});if(path==='/me')return Response.json({id:identity,role:'consumer',is_vendor:true});if(init?.method==='PUT'){revision++;throw new Error('lost after commit');}if(fail)throw new Error('offline');return Response.json({location_revision:revision,latitude:25,longitude:121});};
 try{const first=new FoodApi('https://example.test');await first.login('owner@example.test','synthetic');await assert.rejects(first.mutate('store-location:mine','/vendor/stores/mine/location',{expected_revision:2,latitude:25,longitude:121},'PUT'));const restarted=new FoodApi(first.base);await restarted.login('owner@example.test','synthetic');assert.equal(restarted.pendingBody('store-location:mine'),undefined);assert.equal(restarted.hasPending('store-location:mine'),true);await assert.rejects(restarted.reconcileStoreLocation('mine'));assert.equal(restarted.hasPending('store-location:mine'),true);fail=false;const current=await restarted.reconcileStoreLocation<{location_revision:number}>('mine');assert.equal(current.location_revision,3);assert.equal(restarted.hasPending('store-location:mine'),false);assert.ok(!JSON.stringify([...stored]).includes('latitude'));}
 finally{globalThis.fetch=original;if(descriptor)Object.defineProperty(globalThis,'localStorage',descriptor);else Reflect.deleteProperty(globalThis,'localStorage');}
});
