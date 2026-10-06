'use client';
import {useEffect,useState} from 'react';
import {snapshotNavigation} from '../lib/location';
import {Order,utc} from '../lib/api';
export default function PickupCard({order}:{order:Order}){
 const [now,setNow]=useState(Date.now()),[show,setShow]=useState(false),[qr,setQr]=useState('');
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
 const seconds=Math.max(0,Math.ceil((utc(order.expires_at).getTime()-now)/1000));
 useEffect(()=>{let alive=true;if(show&&order.pickup_qr)import('qrcode').then(q=>q.toDataURL(order.pickup_qr!,{width:280,margin:4,errorCorrectionLevel:'M'})).then(url=>{if(alive)setQr(url);}).catch(()=>{if(alive)setQr('');});return()=>{alive=false;};},[show,order.pickup_qr]);
 const navigation=snapshotNavigation(order.snapshot);
 return <section className="pickup-card"><p>{seconds>0?`剩餘 ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} 可領取`:'領取期限已到，請重新確認預約狀態'}</p>
 {navigation&&<a className="secondary" target="_blank" rel="noreferrer" href={navigation!}>步行前往</a>}
 <button className="primary pickup-big" disabled={seconds===0} onClick={()=>setShow(!show)}>{show?'收起取貨碼':'出示取貨碼'}</button>
 {show&&seconds>0&&<div>{qr&&<img width={280} height={280} className="pickup-qr" src={qr} alt="供商家掃描的單次取貨碼"/>}<p>取貨碼 <strong>{order.pickup_code||'請重新確認預約'}</strong></p><p>交給商家掃碼，確認商品後再領取。</p></div>}
 </section>;
}
