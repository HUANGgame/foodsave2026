'use client';
import {useEffect,useRef,useState} from 'react';
import dynamic from 'next/dynamic';
import {api,ApiError,RequestCancelled} from '../lib/api';
import {currentPosition,Point} from '../lib/location';
const LocationPicker=dynamic(()=>import('./LocationPicker'),{ssr:false});
type Location={id:string;latitude:number;longitude:number;location_revision:number;location_confirmed:boolean;pending_orders:number;can_move:boolean};
type Save={latitude:number;longitude:number;expected_revision:number;confirm:'SAVE_LOCATION'};
export default function StoreLocationEditor({storeId,onClose,onSaved,onError}:{storeId:string;onClose:()=>void;onSaved:()=>Promise<void>;onError:(error:unknown)=>void}){
 const operation=`store-location:${storeId}`;
 const [location,setLocation]=useState<Location|null>(null),[point,setPoint]=useState<Point|null>(null),[busy,setBusy]=useState(false),[pending,setPending]=useState(Boolean(api.pendingBody(operation))),[conflict,setConflict]=useState(false),[message,setMessage]=useState(''),[unresolved,setUnresolved]=useState(api.hasPending(operation)&&!api.pendingBody(operation));
 const alive=useRef(true),lock=useRef(false),read=useRef<AbortController|null>(null),epoch=useRef(0);
 async function load(reconcile=false){
  read.current?.abort();const controller=new AbortController();read.current=controller;const serial=++epoch.current;
  try{const value=await (reconcile?api.reconcileStoreLocation<Location>(storeId):api.request<Location>(`/vendor/stores/${storeId}/location`,'GET',undefined,undefined,controller.signal));if(!alive.current||serial!==epoch.current)return;
   const retry=api.pendingBody<Save>(operation);setLocation(value);setPoint(retry?[retry.latitude,retry.longitude]:[Number(value.latitude),Number(value.longitude)]);setPending(Boolean(retry));setUnresolved(api.hasPending(operation)&&!retry);setConflict(false);setMessage('');
  }catch(e){if(alive.current&&!(e instanceof RequestCancelled))onError(e);}
 }
 useEffect(()=>{alive.current=true;void load();return()=>{alive.current=false;epoch.current++;read.current?.abort();};},[storeId]);
 async function locate(){if(lock.current)return;lock.current=true;setBusy(true);const serial=++epoch.current;try{const p=await currentPosition();if(alive.current&&serial===epoch.current)setPoint(p);}catch(e){if(alive.current)onError(e);}finally{lock.current=false;if(alive.current)setBusy(false);}}
 async function save(){
  if(lock.current||!point||!location||conflict||unresolved)return;lock.current=true;setBusy(true);setMessage('');
  try{await api.mutate(operation,`/vendor/stores/${storeId}/location`,api.pendingBody<Save>(operation)||{latitude:point[0],longitude:point[1],expected_revision:location.location_revision,confirm:'SAVE_LOCATION'},'PUT');if(alive.current){await onSaved();if(alive.current)onClose();}}
  catch(e){if(alive.current){if(e instanceof ApiError&&e.status===409)setConflict(true);setMessage(e instanceof Error?e.message:'保存未完成');onError(e);}}
  finally{lock.current=false;if(alive.current){setBusy(false);setPending(Boolean(api.pendingBody(operation)));}}
 }
 const blocked=location&&!location.can_move;
 return <section className="card live-form" aria-label="編輯店址">
  <h3>{location?.location_confirmed?'調整店址':'確認公開店址'}</h3>
  {!location&&<p role="status">正在讀取店址…</p>}
  {blocked&&<p role="alert">還有待領或過期未結算訂單，暫時不能移動。</p>}
  {point&&<LocationPicker value={point} onChange={setPoint} disabled={busy||pending||unresolved||Boolean(blocked)||conflict}/>}
  <button className="secondary" disabled={!location||busy||pending||unresolved||Boolean(blocked)||conflict} onClick={()=>void locate()}>使用目前位置</button>
  {message&&<p role="status">{message}</p>}
  {unresolved&&<><p>上次保存結果未確認，請核對目前店址後重新編輯。</p><button className="secondary" disabled={busy} onClick={()=>void load(true)}>核對店址後重新編輯</button></>}{pending&&<p>結果未確認，請重試原操作。</p>}
  {(conflict||blocked)&&<button className="secondary" disabled={busy||pending} onClick={()=>void load()}>重新載入店址</button>}
  <button className="primary" disabled={busy||unresolved||!point||!location||conflict||Boolean(blocked&&!pending)} onClick={()=>void save()}>{pending?'重試保存店址':'確認保存店址'}</button>
  <button className="secondary" disabled={busy} onClick={onClose}>返回工作台</button>
 </section>;
}
