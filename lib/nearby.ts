import {FoodApi,LiveProduct,LiveStore,RequestCancelled} from './api';
import type {Point} from './location';
type Page<T>={items:T[];next_cursor:string|null;radius_m:number;page_size:number};
export async function allNearby<T extends {id:string}>(api:FoodApi,resource:'stores'|'products',center:Point,signal?:AbortSignal):Promise<T[]>{
 const session=api.sessionVersion,items=new Map<string,T>(),seen=new Set<string>();let cursor:string|null=null;
 do{
  if(signal?.aborted||api.sessionVersion!==session)throw new RequestCancelled();
  const query=new URLSearchParams({latitude:String(center[0]),longitude:String(center[1]),limit:'100'});
  if(cursor!==null)query.set('cursor',cursor);
  const page=await api.request<Page<T>>(`/nearby/${resource}?${query}`,'GET',undefined,undefined,signal);
  if(signal?.aborted||api.sessionVersion!==session)throw new RequestCancelled();
  if(!Array.isArray(page.items)||page.radius_m!==1000||!(page.next_cursor===null||typeof page.next_cursor==='string'))throw new Error('附近資料未完整，請重新整理。');
  for(const item of page.items){if(!item||typeof item.id!=='string')throw new Error('附近資料格式不正確。');items.set(item.id,item);}
  cursor=page.next_cursor;
  if(cursor!==null){if(!cursor||seen.has(cursor))throw new Error('附近分頁未完成，請重新整理。');seen.add(cursor);}
 }while(cursor!==null);
 return [...items.values()];
}
export async function nearbyCatalog(api:FoodApi,center:Point,signal?:AbortSignal){
 const [stores,products]=await Promise.all([allNearby<LiveStore>(api,'stores',center,signal),allNearby<LiveProduct>(api,'products',center,signal)]);
 return {stores,products};
}
