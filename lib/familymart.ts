import {Capacitor,CapacitorHttp} from '@capacitor/core';
export const FAMILY_ENDPOINT='https://stamp.family.com.tw/api/maps/MapProductInfo';
export const FAMILY_SOURCE='https://event.family.com.tw/cherishfood/';
export const CACHE_MS=30*60*1000;
export const PUBLIC_AREA={id:'taipei-xinyi-public-v1',name:'臺北市信義區（公開測試區域）',latitude:25.0375197,longitude:121.5636704} as const;
export type QueryArea={id:string;name:string;latitude:number;longitude:number;nearby?:boolean};
export const PUBLIC_AREAS:readonly QueryArea[]=[PUBLIC_AREA,
 {id:'newtaipei-banqiao-v1',name:'新北市板橋區',latitude:25.014,longitude:121.464},
 {id:'taoyuan-center-v1',name:'桃園市桃園區',latitude:24.993,longitude:121.301},
 {id:'taichung-west-v1',name:'臺中市西區',latitude:24.141,longitude:120.663},
 {id:'tainan-westcentral-v1',name:'臺南市中西區',latitude:22.994,longitude:120.196},
 {id:'kaohsiung-lingya-v1',name:'高雄市苓雅區',latitude:22.625,longitude:120.314}];
export type ExternalProduct={id:string;name:string;quantity:number|null;category:string};
export type ExternalStore={id:string;name:string;address:string;latitude:number;longitude:number;sourceUpdatedAt:string|null;products:ExternalProduct[];quantity:number|null};
export type SourceResult={status:'ok'|'unavailable';stores:ExternalStore[];checkedAt:string|null;lastSuccessAt:string|null;cached:boolean;retryAt:string|null;httpStatus?:number};
type Response={status:number;data:unknown};
type StorageLike=Pick<Storage,'getItem'|'setItem'>;
type Saved={version:1;checkedAt:string;lastSuccessAt:string|null;data:unknown;status:'ok'|'unavailable';httpStatus?:number};
function object(value:unknown):Record<string,unknown>{return value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};}
function list(value:unknown){return Array.isArray(value)?value:[];}
function text(value:unknown,limit=160){return typeof value==='string'?value.slice(0,limit):'';}
function id(value:unknown){return typeof value==='string'&&value.length>0?value.slice(0,80):typeof value==='number'&&Number.isSafeInteger(value)?String(value):'';}
export function sourceTime(value:unknown):string|null{
 const raw=text(value,80);if(!raw)return null;
 // FamilyMart wall-clock timestamps refer to Taiwan, never interpret them as UTC.
 const local=raw.match(/^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/);
 const normalized=local?`${local[1]}-${local[2]}-${local[3]}T${local[4]}:${local[5]}:${local[6]}+08:00`:raw;
 if(!local&&!/(Z|[+-]\d\d:\d\d)$/.test(raw))return null;
 return Number.isFinite(Date.parse(normalized))?normalized:null;
}
export function quantity(value:unknown):number|null{
 const n=typeof value==='number'?value:typeof value==='string'&&/^\d+$/.test(value)?Number(value):NaN;
 return Number.isSafeInteger(n)&&n>=0?n:null;
}
export function normalizeFamily(status:number,payload:unknown):ExternalStore[]{
 const response=object(payload);
 if(status!==200||response.code!==1||!Array.isArray(response.data))throw new Error('source_unavailable');
 const stores:ExternalStore[]=[];const seen=new Set<string>();
 for(const value of response.data.slice(0,200)){
  const s=object(value),identity=id(s.oldPKey),name=text(s.name),lat=Number(s.latitude),lng=Number(s.longitude);
  if(!identity||!name||s.latitude===null||s.longitude===null||s.latitude===''||s.longitude===''||!Number.isFinite(lat)||!Number.isFinite(lng)||lat< -90||lat>90||lng< -180||lng>180||seen.has(identity))continue;
  seen.add(identity);const products:ExternalProduct[]=[],productIds=new Set<string>();
  for(const info of list(s.info))for(const category of list(object(info).categories))for(const product of list(object(category).products)){
   const p=object(product),productId=id(p.code),productName=text(p.name);
   if(!productId||!productName||productIds.has(productId)||products.length>=200)continue;
   productIds.add(productId);products.push({id:productId,name:productName,quantity:quantity(p.qty),category:text(object(category).name)});
  }
  const total=products.length&&products.every(p=>p.quantity!==null)?products.reduce((n,p)=>n+p.quantity!,0):null;
  stores.push({id:identity,name,address:text(s.address,300),latitude:lat,longitude:lng,sourceUpdatedAt:sourceTime(s.updateDate),products,quantity:total!==null&&Number.isSafeInteger(total)?total:null});
 }
 if(response.data.length&&!stores.length)throw new Error('source_schema_changed');
 return stores;
}
export async function familyTransport(area:QueryArea=PUBLIC_AREA):Promise<Response>{
 if(!Number.isFinite(area.latitude)||!Number.isFinite(area.longitude)||Math.abs(area.latitude)>90||Math.abs(area.longitude)>180)throw new Error('invalid_area');
 const data={ProjectCode:'202106302',OldPKeys:[],PostInfo:'',Latitude:area.latitude,Longitude:area.longitude};
 // Coordinates are selected by the user; nearby coordinates require explicit consent.
 // Never forward app bearer or account data.
 if(Capacitor.isNativePlatform()){
  const response=await CapacitorHttp.post({url:FAMILY_ENDPOINT,headers:{'Content-Type':'application/json'},data,connectTimeout:10000,readTimeout:15000,disableRedirects:true,responseType:'json'});
  return {status:response.status,data:response.data};
 }
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{
  const response=await fetch(FAMILY_ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),credentials:'omit',redirect:'error',signal:controller.signal});
  return {status:response.status,data:await response.json()};
 }finally{clearTimeout(timer);}
}
export class FamilySource {
 private saved:Saved|null=null;private pending:Promise<SourceResult>|null=null;
 private cacheKey:string;
 constructor(private storage?:StorageLike,private transport?:()=>Promise<Response>,private now:()=>number=Date.now,area:QueryArea=PUBLIC_AREA){
  const selected={...area};this.transport=transport||(()=>familyTransport(selected));
  this.cacheKey='foodsave-public-familymart-v1:'+selected.id+':'+selected.latitude+':'+selected.longitude;
  if(selected.nearby)this.storage=undefined;
  try{
   const raw=this.storage?.getItem(this.cacheKey);if(!raw||raw.length>2_000_000)return;
   const value=JSON.parse(raw) as Saved;
   if(value.version!==1||!['ok','unavailable'].includes(value.status)||!Number.isFinite(Date.parse(value.checkedAt))||(value.lastSuccessAt!==null&&!Number.isFinite(Date.parse(value.lastSuccessAt))))return;
   if(value.status==='ok'&&value.data===null)return;
   if(value.data!==null)normalizeFamily(200,value.data);
   this.saved=value;
  }catch{/* Invalid local cache is ignored; never turns into a successful empty source. */}
 }
 current(cached=true):SourceResult{
  const saved=this.saved;
  return {status:saved?.status||'unavailable',stores:saved?.data?normalizeFamily(200,saved.data):[],checkedAt:saved?.checkedAt||null,lastSuccessAt:saved?.lastSuccessAt||null,cached,retryAt:saved?new Date(Date.parse(saved.checkedAt)+CACHE_MS).toISOString():null,httpStatus:saved?.httpStatus};
 }
 query():Promise<SourceResult>{
  if(this.pending)return this.pending;
  if(this.saved&&this.now()-Date.parse(this.saved.checkedAt)<CACHE_MS)return Promise.resolve(this.current());
  this.pending=this.fetchOnce().finally(()=>{this.pending=null;});return this.pending;
 }
 private async fetchOnce():Promise<SourceResult>{
  const checkedAt=new Date(this.now()).toISOString();let status:number|undefined;
  try{
   const response=await this.transport!();status=response.status;normalizeFamily(status,response.data);
   this.saved={version:1,checkedAt,lastSuccessAt:checkedAt,data:response.data,status:'ok',httpStatus:status};
  }catch{
   this.saved={version:1,checkedAt,lastSuccessAt:this.saved?.lastSuccessAt||null,data:this.saved?.data||null,status:'unavailable',httpStatus:status};
  }
  try{const raw=JSON.stringify(this.saved);if(raw.length<=2_000_000)this.storage?.setItem(this.cacheKey,raw);}catch{/* Session cache still enforces cooldown. */}
  return this.current(false);
 }
}
export function isStale(store:ExternalStore,result:SourceResult,now=Date.now()){
 const source=store.sourceUpdatedAt?Date.parse(store.sourceUpdatedAt):NaN;
 return result.status!=='ok'||!result.lastSuccessAt||now-Date.parse(result.lastSuccessAt)>=CACHE_MS||!Number.isFinite(source)||now-source>=CACHE_MS||source>now+5*60*1000;
}
