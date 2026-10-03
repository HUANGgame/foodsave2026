export const stores = [
 { id:'rice', name:'幸福飯糰', category:'手作早餐', address:'台北市大安區・示範位置', lat:25.0336, lng:121.5435, icon:'🍙', color:'#f5e7ce', intro:'把今天的好滋味，留給剛剛好的你。' },
 { id:'bread', name:'米香烘焙坊', category:'麵包・甜點', address:'台北市大安區・示範位置', lat:25.0308, lng:121.5397, icon:'🥐', color:'#ffe1bc', intro:'每日手作烘焙，讓每一口心意都不浪費。' },
 { id:'green', name:'小樹蔬食', category:'健康餐盒', address:'台北市大安區・示範位置', lat:25.0357, lng:121.5385, icon:'🥗', color:'#dcebd3', intro:'新鮮蔬食，也是對地球的一點溫柔。' }
];
export type Product = {id:string;store:string;name:string;original:number;price:number;stock:number;kind:string;icon:string;availableUntil?:number};
export const products:Product[] = [
 {id:'rice1',store:'rice',name:'鮪魚玉米飯糰',original:45,price:25,stock:4,kind:'即期',icon:'🍙'},
 {id:'rice2',store:'rice',name:'暖心茶葉蛋',original:15,price:8,stock:6,kind:'打折',icon:'🥚'},
 {id:'bread1',store:'bread',name:'奶油可頌組',original:100,price:60,stock:3,kind:'打折',icon:'🥐'},
 {id:'bread2',store:'bread',name:'今日分享小餐包',original:30,price:0,stock:2,kind:'免費',icon:'🥖'},
 {id:'green1',store:'green',name:'繽紛蔬食餐盒',original:120,price:65,stock:3,kind:'即期',icon:'🥗'}
];
export type Reservation = {id:string; product:string; code:string; status:'waiting'|'completed'|'cancelled'|'expired'; expires:number; snapshot?:Pick<Product,'name'|'store'|'price'|'icon'>; review?:{rating:number;text:string}};
export type DemoState = { version:1; catalog?:Product[]; favorites:string[]; notified:string[]; favoriteAwards:string[]; reservations:Reservation[]; exp:{key:string;amount:number;at:number}[] };
export const freshState=():DemoState=>({version:1,favorites:[],notified:[],favoriteAwards:[],reservations:[],exp:[]});
export function expire(s:DemoState, now=Date.now()):DemoState { return {...s,reservations:s.reservations.map(r=>r.status==='waiting'&&r.expires<=now?{...r,status:'expired'}:r)}; }
export const catalog=(s:DemoState):Product[]=>s.catalog??products;
export function remaining(s:DemoState,id:string){return (catalog(s).find(p=>p.id===id)?.stock??0)-s.reservations.filter(r=>r.product===id&&(r.status==='waiting'||r.status==='completed')).length;}
function award(s:DemoState,key:string,amount:number,now:number){return s.exp.some(e=>e.key===key)?s:{...s,exp:[...s.exp,{key,amount,at:now}]};}
export function favorite(s:DemoState,id:string,now=Date.now()):DemoState {
 if(s.favorites.includes(id)) return {...s,favorites:s.favorites.filter(x=>x!==id),notified:s.notified.filter(x=>x!==id)};
 const n={...s,favorites:[...s.favorites,id],favoriteAwards:[...new Set([...s.favoriteAwards,id])]};
 return award(n,'favorite:'+id,50,now);
}
export function reserve(state:DemoState, product:string,now=Date.now()):DemoState {
 const s=expire(state,now);
 const item=catalog(s).find(p=>p.id===product);
 if(!item||remaining(s,product)<=0||(item.availableUntil!==undefined&&item.availableUntil<=now)) throw Error('這項商品已沒有庫存');
 if(s.reservations.some(r=>r.product===product&&r.status==='waiting')) throw Error('你已預約這項商品，請查看我的預約');
 const id='DEMO-'+(s.reservations.length+1).toString().padStart(4,'0');
 return {...s,reservations:[...s.reservations,{id,product,code:(100000+s.reservations.length+1).toString(),status:'waiting',expires:Math.min(now+30*60*1000,item.availableUntil??Infinity),snapshot:{name:item.name,store:item.store,price:item.price,icon:item.icon}}]};
}
export function changeReservation(state:DemoState,id:string,action:'cancel'|'complete',code='',now=Date.now()):DemoState {
 const s=expire(state,now),r=s.reservations.find(r=>r.id===id);
 if(!r||r.status!=='waiting') throw Error('此預約已處理或已逾時');
 if(action==='complete'&&r.code!==code) throw Error('取貨碼不正確');
 const next={...s,reservations:s.reservations.map(x=>x.id===id?{...x,status:action==='cancel'?'cancelled' as const:'completed' as const}:x)};
 return action==='complete'?award(next,'pickup:'+id,100,now):next;
}
export function review(s:DemoState,id:string,rating:number,text:string,now=Date.now()):DemoState {
 const r=s.reservations.find(r=>r.id===id);
 if(!r||r.status!=='completed'||r.review)throw Error('僅限已完成、尚未評論的領取');
 if(!Number.isInteger(rating)||rating<1||rating>5||!text.trim()||text.trim().length>300)throw Error('請填寫 1～5 星及 1～300 字評論');
 return award({...s,reservations:s.reservations.map(x=>x.id===id?{...x,review:{rating,text:text.trim()}}:x)},'review:'+id,80,now);
}
export function weekStart(now=Date.now()) { const d=new Date(now+8*3600000); const day=(d.getUTCDay()+6)%7; return Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()-day)-8*3600000; }
export {distance} from './geo';

export type ProductInput = {store:string;name:string;original:number;price:number;quantity:number;kind:string;icon:string;availableUntil:number};
export function saveProduct(state:DemoState,input:ProductInput,id?:string,now=Date.now()):DemoState {
 const s=expire(state,now),list=catalog(s),old=id?list.find(p=>p.id===id):undefined;
 if(id&&!old)throw Error('找不到這項商品');
 if(!stores.some(x=>x.id===input.store)||(old&&old.store!==input.store))throw Error('請選擇正確示範店家');
 if(!input.name.trim()||input.name.trim().length>40)throw Error('商品名稱需為 1～40 字');
 if(!Number.isInteger(input.quantity)||input.quantity<0||input.quantity>9999)throw Error('可預約數量需為 0～9999 的整數');
 if(!Number.isInteger(input.original)||!Number.isInteger(input.price)||input.price<0||input.original<input.price||input.original>100000)throw Error('價格需為整數，優惠價不可高於原價');
 if(!Number.isFinite(input.availableUntil)||input.availableUntil<=now)throw Error('領取截止時間必須在未來');
 const productId=id??'custom-'+(list.length+1);
 const committed=s.reservations.filter(r=>r.product===productId&&(r.status==='waiting'||r.status==='completed')).length;
 const p:Product={id:productId,store:input.store,name:input.name.trim(),original:input.original,price:input.price,stock:input.quantity+committed,kind:input.price===0?'免費':input.kind==='即期'?'即期':'打折',icon:['🍙','🥐','🥗','🍱','🍰','☕'].includes(input.icon)?input.icon:'🍱',availableUntil:input.availableUntil};
 // Preserve existing order details when an older APK's order has no snapshot.
 const reservations=s.reservations.map(r=>{const product=list.find(p=>p.id===r.product);return r.snapshot||!product?r:{...r,snapshot:{name:product.name,store:product.store,price:product.price,icon:product.icon}};});
 return {...s,reservations,catalog:old?list.map(item=>item.id===id?p:item):[...list,p]};
}
