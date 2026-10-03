'use client';
import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from '../lib/api';
import PickupScanner from './PickupScanner';
type Review={id:string;name:string;quantity:number;total_price_minor:number;review_token:string;review_expires_at:string;key:string};
export default function MerchantPickup({onComplete,onBusy}:{onComplete:()=>Promise<void>;onBusy:(busy:boolean)=>void}){
 const [scanning,setScanning]=useState(true),[manual,setManual]=useState(false),[review,setReview]=useState<Review|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[retry,setRetry]=useState(false);const lock=useRef(false),autoScan=useRef(true);
 useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
 // Component is mounted only after the merchant explicitly chooses scan.
 async function preview(credential:string){if(lock.current)return;lock.current=true;setBusy(true);setScanning(false);setMessage('');setReview(null);setRetry(false);
  try{if(!/^(FS1\.[A-Za-z0-9_-]{43}|[A-F0-9]{12})$/.test(credential))throw Error('這不是取貨碼，請重試或手動輸入');const key=crypto.randomUUID();const result=await api.request<Omit<Review,'key'>>('/vendor/pickups/preview','POST',{credential},key);setReview({...result,key});}
  catch(e){setMessage(e instanceof Error?e.message:'尚未確認，請重試');setManual(true);}finally{lock.current=false;setBusy(false);}
 }
 async function confirm(){if(lock.current||!review)return;lock.current=true;setBusy(true);setMessage('');let next=false;
  try{const result=await api.mutate<{state:string}>(`pickup-confirm:${review.key}`,'/vendor/pickups/confirm',{review_key:review.key,review_token:review.review_token});setReview(null);setRetry(false);setMessage(result.state==='completed'?'交付成功，請掃下一位':'預約已逾時，沒有完成交付');setManual(!autoScan.current);next=result.state==='completed'&&autoScan.current;void onComplete().catch(()=>setMessage('交付成功；訂單列表更新失敗，請重新載入'));}
  catch(e){setMessage(e instanceof Error?e.message:'尚未確認');setRetry(true);if(e instanceof ApiError&&[400,403,404,409,422].includes(e.status)){setReview(null);setRetry(false);setManual(true);}}finally{lock.current=false;setBusy(false);if(next&&!document.hidden)setScanning(true);}
 }
 return <section className="card"><h2>掃碼取貨</h2><p role="status">{message}</p>{busy&&<p role="status">正在確認，請勿重複交付…</p>}
 {scanning&&!review&&<PickupScanner onScan={preview} onStop={message=>{autoScan.current=false;setScanning(false);setManual(true);setMessage(message);}}/>}
 {review&&<><h3>{review.name}</h3><p className="pickup-summary">{review.quantity}份 · 成交總價 ${review.total_price_minor/100}</p><button className="primary pickup-big" disabled={busy} onClick={confirm}>{retry?'尚未確認，重試交付':'確認交付'}</button>{!retry&&<button className="secondary" disabled={busy} onClick={()=>{setReview(null);setScanning(true);}}>重新掃碼</button>}</>}
 {!scanning&&!review&&<button className="primary pickup-big" disabled={busy} onClick={()=>{autoScan.current=true;setScanning(true);setManual(false);setMessage('');}}>重新掃碼</button>}
 {manual&&!review&&<form className="live-form" onSubmit={e=>{e.preventDefault();preview(String(new FormData(e.currentTarget).get('code')).trim().toUpperCase());}}><label>手動取貨碼<input name="code" required pattern="[a-fA-F0-9]{12}" maxLength={12} autoComplete="off"/></label><button className="secondary" disabled={busy}>核對取貨碼</button></form>}
 </section>;
}
