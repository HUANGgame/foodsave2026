'use client';
import {useEffect,useRef,useState} from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {api} from '../lib/api';
import {currentPosition,Point} from '../lib/location';
const LocationPicker=dynamic(()=>import('./LocationPicker'),{ssr:false});
type Draft={name:string;latitude:number;longitude:number};
export default function StoreSetup({initialPoint,onCreated,onError}:{initialPoint:Point|null;onCreated:()=>Promise<void>;onError:(error:unknown)=>void}){
 const retry=api.pendingBody<Draft>('store.create');
 const [name,setName]=useState(retry?.name||''),[point,setPoint]=useState<Point|null>(retry?[retry.latitude,retry.longitude]:initialPoint),[busy,setBusy]=useState(false),[pending,setPending]=useState(Boolean(retry)),[unresolved,setUnresolved]=useState(api.hasPending('store.create')&&!retry);
 const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 async function locate(){if(lock.current)return;lock.current=true;setBusy(true);try{const p=await currentPosition();if(alive.current)setPoint(p);}catch(e){if(alive.current)onError(e);}finally{lock.current=false;if(alive.current)setBusy(false);}}
 async function reconcile(){if(lock.current)return;lock.current=true;setBusy(true);try{await api.reconcileStoreCreation();if(alive.current){setPending(false);setUnresolved(false);await onCreated();}}catch(e){if(alive.current)onError(e);}finally{lock.current=false;if(alive.current)setBusy(false);}}
 async function create(){
  if(lock.current||unresolved||!point||!name.trim())return;lock.current=true;setBusy(true);
  try{await api.mutate('store.create','/vendor/store',api.pendingBody<Draft>('store.create')||{name:name.trim(),latitude:point[0],longitude:point[1]});if(alive.current)await onCreated();}
  catch(e){if(alive.current)onError(e);}
  finally{lock.current=false;if(alive.current){setBusy(false);setPending(Boolean(api.pendingBody('store.create')));}}
 }
 return <form className="card live-form" onSubmit={e=>{e.preventDefault();void create();}}>
  <h3>建立我的店家</h3>
  <label>店家名稱<input required maxLength={100} value={name} disabled={busy||pending||unresolved} onChange={e=>setName(e.target.value)}/></label>
  <button type="button" className="secondary" disabled={busy||pending||unresolved} onClick={()=>void locate()}>使用目前位置</button>
  {point&&<><LocationPicker value={point} onChange={setPoint} disabled={busy||pending||unresolved}/><p className="small">拖曳圖釘調整店址，建立後再確認公開。</p></>}
  {unresolved&&<><p>上次建立結果未確認，請先核對店家。</p><button type="button" className="secondary" disabled={busy} onClick={()=>void reconcile()}>核對店家後繼續</button></>}{pending&&<p role="status">結果未確認，請重試原操作。</p>}
  <button className="primary" disabled={busy||unresolved||!point||!name.trim()}>{pending?'重試建立店家':'建立店家'}</button>
  <Link className="secondary" href="/profile/">返回個人中心</Link>
 </form>;
}
