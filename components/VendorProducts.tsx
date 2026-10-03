'use client';
import {useState} from 'react';
import {catalog,DemoState,Product,ProductInput,remaining,saveProduct,stores} from '../lib/demo';
function localTime(ms:number){const d=new Date(ms);return new Date(ms-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
export default function VendorProducts({state,onSave,onMessage}:{state:DemoState;onSave:(s:DemoState)=>void;onMessage:(s:string)=>void}){
 const [editing,setEditing]=useState<Product|null>(null),[formKey,setFormKey]=useState(0),[vendor,setVendor]=useState('rice');
 function edit(p:Product){setEditing(p);setVendor(p.store);setFormKey(k=>k+1);document.getElementById('product-form')?.scrollIntoView({behavior:'smooth',block:'start'});}
 function cancel(){setEditing(null);setFormKey(k=>k+1);}
 return <section className="vendor-products"><h2 className="section-heading">示範商品管理</h2><p className="muted">上架內容會立即出現在此裝置的地圖與商品列表，不會傳送給真實店家。</p>
 <form id="product-form" className="card" key={formKey} onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);const input:ProductInput={store:String(data.get('store')),name:String(data.get('name')),original:Number(data.get('original')),price:Number(data.get('price')),quantity:Number(data.get('quantity')),kind:String(data.get('kind')),icon:String(data.get('icon')),availableUntil:new Date(String(data.get('deadline'))).getTime()};try{onSave(saveProduct(state,input,editing?.id));onMessage(editing?'商品已更新，原有預約與取貨碼保留':'上架成功！可到探索地圖預約');cancel();}catch(err){onMessage((err as Error).message);}}}>
 <h3>{editing?'編輯商品':'上架新商品'}</h3>
 <label>示範店家<select name="store" value={editing?.store??vendor} onChange={e=>setVendor(e.target.value)} aria-readonly={!!editing}>{(editing?stores.filter(s=>s.id===editing.store):stores).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
 <label>商品名稱<input name="name" defaultValue={editing?.name??''} required maxLength={40} placeholder="例如：今日手作便當"/></label>
 <div className="form-grid"><label>原價（元）<input name="original" type="number" inputMode="numeric" min="0" max="100000" step="1" defaultValue={editing?.original??100} required/></label><label>優惠價（元）<input name="price" type="number" inputMode="numeric" min="0" max="100000" step="1" defaultValue={editing?.price??60} required/></label></div>
 <label>可再預約數量<input name="quantity" type="number" inputMode="numeric" min="0" max="9999" step="1" defaultValue={editing?remaining(state,editing.id):3} required/></label><p className="small muted">此欄只調整尚未預約的庫存，不會取消已建立的訂單；取消／到期的預約會歸還 1 份。</p>
 <div className="form-grid"><label>優惠類別<select name="kind" defaultValue={editing?.kind==='即期'?'即期':'打折'}><option value="打折">限時折扣</option><option value="即期">即期優惠</option></select></label><label>商品圖示<select name="icon" defaultValue={editing?.icon??'🍱'}>{['🍱','🍙','🥐','🥗','🍰','☕'].map(icon=><option key={icon}>{icon}</option>)}</select></label></div>
 <p className="small muted">優惠價設為 0 元會自動標示免費。本版以圖示代替照片上傳。</p>
 <label>領取截止時間<input name="deadline" type="datetime-local" defaultValue={localTime(editing?.availableUntil??Date.now()+24*3600000)} required/></label>
 <button type="submit" className="primary">{editing?'儲存商品變更':'確認上架'}</button>{editing&&<button type="button" className="text-button" onClick={cancel}>取消編輯</button>}
 </form>
 <h3>目前商品</h3>{catalog(state).map(p=><article className="card vendor-item" key={p.id}><div className="row"><h3>{p.icon} {p.name}</h3><span className="tag">{stores.find(s=>s.id===p.store)?.name}</span></div><p>${p.price}・可再預約 {remaining(state,p.id)} 份</p><p className="small">{p.availableUntil?`截止：${new Date(p.availableUntil).toLocaleString('zh-TW',{hour12:false})}`:'示範常態商品'}{p.availableUntil&&p.availableUntil<=Date.now()?'（已截止，前台隱藏）':''}</p><button className="secondary" onClick={()=>edit(p)} aria-label={'編輯 '+p.name}>編輯商品與庫存</button></article>)}
 </section>;
}
