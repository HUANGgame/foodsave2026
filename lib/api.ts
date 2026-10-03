export type Account={id:string;email:string;role:'consumer'|'vendor'|'admin';exp:number;spins:number};
export type LiveProduct={id:string;store_id:string;store_name:string;name:string;photo_url:string;latitude:number;longitude:number;original_price_minor:number;sale_price_minor:number;available_quantity:number;pickup_deadline:string;revision:number;active?:boolean};
export type Prize={id:string;name:string;kind?:string;terms?:string;expires_at?:string;discount_percent?:number};
export type Draw={id:string;prize:Prize;segments:{id:string;name:string}[];coupon_code?:string};
export type Order={id:string;product_id:string;state:string;quantity:number;snapshot:string|{name:string;sale_price_minor:number};expires_at:string;pickup_code?:string};
export class ApiError extends Error {constructor(public status:number,message:string){super(message);}}
export function utc(value:string){return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value)?value:value+'Z');}
export class FoodApi {
 private token='';private identity='';
 constructor(readonly base:string){}
 get authenticated(){return Boolean(this.token);}
 hasPending(operation:string){try{return Boolean(this.identity&&localStorage.getItem(`foodsave-pending-v1:${this.identity}:${operation}`));}catch{return false;}}
 clear(){this.token='';this.identity='';}
 async request<T>(path:string,method='GET',body?:unknown,key?:string):Promise<T>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{const response=await fetch(this.base+path,{method,signal:controller.signal,cache:'no-store',headers:{'Content-Type':'application/json',...(this.token?{Authorization:`Bearer ${this.token}`} : {}),...(key?{'Idempotency-Key':key}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
   const data=await response.json();if(!response.ok){if(response.status===401)this.clear();throw new ApiError(response.status,data.detail||'服務暫時無法使用');}return data as T;
  }catch(error){if(error instanceof ApiError)throw error;throw new ApiError(0,'連線未完成。請檢查網路後重試；未確認的操作會沿用原識別碼。');}finally{clearTimeout(timer);}
 }
 async login(email:string,password:string){const session=await this.request<{access_token:string}>('/auth/login','POST',{email,password});this.token=session.access_token;try{const me=await this.request<Account>('/me');this.identity=me.id;return me;}catch(e){this.clear();throw e;}}
 async logout(){await this.request('/auth/logout','POST',{});this.clear();}
 async mutate<T>(operation:string,path:string,body:unknown,method='POST'):Promise<T>{
  if(!this.identity)throw new ApiError(401,'請先登入');
  const storageKey=`foodsave-pending-v1:${this.identity}:${operation}`;
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify({path,method,body})));
  const fingerprint=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
  let intent:{key:string;fingerprint:string};
  try{const old=localStorage.getItem(storageKey);intent=old?JSON.parse(old):{key:crypto.randomUUID(),fingerprint};if(intent.fingerprint!==fingerprint)throw new ApiError(409,'上一筆操作尚未確認，請先重試相同內容。');localStorage.setItem(storageKey,JSON.stringify(intent));}
  catch(error){if(error instanceof ApiError)throw error;throw new ApiError(0,'無法安全保留重試識別碼，操作尚未送出。請開啟裝置儲存權限。');}
  try{const result=await this.request<T>(path,method,body,intent.key);localStorage.removeItem(storageKey);return result;}
  catch(error){if(error instanceof ApiError&&error.status>=400&&error.status<500&&error.status!==401&&error.status!==408&&error.status!==429){localStorage.removeItem(storageKey);}throw error;}
 }
}
const rawBase=process.env.NEXT_PUBLIC_API_BASE_URL||'';
export const liveConfigurationError=!/^https:\/\/[^\s]+/.test(rawBase)?'正式模式尚未設定有效的 HTTPS API，請聯絡服務管理者。':'';
export const api=new FoodApi(rawBase.replace(/\/$/,''));
