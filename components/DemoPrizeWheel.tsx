'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {api,ApiError} from '../lib/api';
import ArtIcon from './ArtIcon';
import PrizeWheel from './PrizeWheel';
export type DemoPrize={id:string;name:string;icon:string;terms:string};
type Pool={enabled:boolean;demonstration?:boolean;notice?:string;revision:number;prizes:DemoPrize[]};
type Result=Pool&{prize:DemoPrize;redeemable:false;consumes_real_spin:false};
const colors=['#dcefd9','#fff0c6','#d6eced','#ffe5d8','#e9e1f2','#e1edd2'];
export default function RewardsPanel(props:Parameters<typeof PrizeWheel>[0]){
 const [pool,setPool]=useState<Pool|null>(null),[unavailable,setUnavailable]=useState(false),[attempt,setAttempt]=useState(0);
 useEffect(()=>{let alive=true;setUnavailable(false);api.request<Pool>('/demo-prizes').then(p=>{if(alive)setPool(p);}).catch(()=>{if(alive)setUnavailable(true);});return()=>{alive=false;};},[attempt]);
 if(unavailable)return <section><p role="status">無法確認獎池設定，尚未抽獎。</p><button className="secondary" onClick={()=>setAttempt(v=>v+1)}>重新讀取獎池</button></section>;
 if(!pool)return <p role="status">正在讀取獎池設定…</p>;
 return pool.enabled?<DemoWheel initial={pool}/>:<PrizeWheel {...props}/>;
}
function DemoWheel({initial}:{initial:Pool}){
 const [pool,setPool]=useState(initial),[result,setResult]=useState<Result|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[angle,setAngle]=useState(0),[ready,setReady]=useState(true),[confirm,setConfirm]=useState(false);
 const version=useRef(initial.revision),sequence=useRef(0),frozen=useRef(false);
 const lock=useRef(false),alive=useRef(true),dialog=useRef<HTMLDialogElement>(null),wheel=useRef<HTMLDivElement>(null);
 const refresh=useCallback(async()=>{
  if(!alive.current||frozen.current||document.visibilityState!=='visible')return;
  const request=++sequence.current;
  try{const next=await api.request<Pool>('/demo-prizes');
   if(!alive.current||request!==sequence.current||frozen.current||document.visibilityState!=='visible')return;
   if(!next.enabled||next.demonstration!==true||next.prizes?.length!==6)throw new Error('示範獎池目前未開放');
   if(next.revision<version.current)return;
   if(next.revision>version.current){setConfirm(true);setMessage('獎池已更新，請確認新版內容後再體驗。');}
   else setMessage('');
   version.current=next.revision;setPool(next);setReady(true);
  }catch(e){if(alive.current&&request===sequence.current&&!frozen.current){setReady(false);setMessage('無法更新獎池，暫停抽獎；請重新讀取或稍後再試。');}}
 },[]);
 useEffect(()=>{alive.current=true;const visible=()=>{sequence.current++;if(document.visibilityState==='visible')void refresh();};const timer=setInterval(()=>{void refresh();},30000);document.addEventListener('visibilitychange',visible);return()=>{alive.current=false;sequence.current++;clearInterval(timer);document.removeEventListener('visibilitychange',visible);};},[refresh]);
 function closeResult(){setResult(null);frozen.current=false;void refresh();}
 useEffect(()=>{if(result)dialog.current?.showModal();},[result]);
 async function spin(){if(lock.current||frozen.current||!ready)return;lock.current=true;frozen.current=true;sequence.current++;setBusy(true);setMessage('');let completed=false;try{
  const next=await api.request<Result>('/demo-draws','POST',{revision:version.current});
  if(!alive.current)return;
  if(next.demonstration!==true||next.redeemable!==false||next.consumes_real_spin!==false||next.prizes.length!==6)throw new Error('示範結果資料不完整');
  const index=next.prizes.findIndex(p=>p.id===next.prize.id);if(index<0)throw new Error('示範獎項不在設定中');
  version.current=next.revision;setPool(next);setConfirm(false);const target=(360-(index+.5)*60)%360,destination=angle+1080+(target-angle%360+360)%360;
  await new Promise<void>(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r())));if(!alive.current)return;
  const animation=wheel.current?.animate([{transform:`rotate(${angle}deg)`},{transform:`rotate(${destination}deg)`}],{duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:1800,easing:'ease-out',fill:'forwards'});
  setAngle(destination);if(animation)try{await animation.finished;}catch{}animation?.cancel();if(alive.current){completed=true;setResult(next);}
 }catch(e){if(alive.current){
  const changed=e instanceof ApiError&&e.status===409?e.data as Pool&{code?:string}:null;
  if(changed?.code==='pool_changed'&&changed.demonstration===true&&changed.prizes?.length===6&&changed.revision>=version.current){version.current=changed.revision;setPool(changed);setConfirm(true);setReady(true);setMessage('獎池已更新，本次未抽獎。請確認新版內容，再按一次體驗。');}
  else setMessage(e instanceof Error?e.message:'示範暫時無法使用');
 }}finally{if(!completed)frozen.current=false;lock.current=false;if(alive.current)setBusy(false);}}
 return <section className="wheel-section"><h2>幸運惜食轉盤</h2><p className="demo-notice">示範，暫不可兌換</p><p>可重複體驗，不扣正式抽獎次數、不發EXP或正式優惠券。</p><div className="wheel-wrap"><span className="wheel-pointer" aria-hidden="true">▼</span><div className="prize-wheel demo-wheel" ref={wheel} style={{transform:`rotate(${angle}deg)`,background:`conic-gradient(${pool.prizes.map((_,i)=>`${colors[i]} ${i*60}deg ${(i+1)*60}deg`).join(',')})`}} aria-label="六個示範獎品扇區">{pool.prizes.map((p,i)=><span className="wheel-label" key={p.id} style={{transform:`translate(-50%,-50%) rotate(${(i+.5)*60}deg) translateY(-96px) rotate(90deg)`}}><ArtIcon name={p.icon}/>{p.name}</span>)}</div><button className="wheel-start" onClick={spin} disabled={busy||!ready}>{busy?'揭曉中':confirm?'確認新版並體驗':'體驗示範轉盤'}</button></div><p className="small">設定版本 {pool.revision} · 可見時每30秒更新，返回前景立即更新；不是即時推送</p><ul className="wheel-prize-list">{pool.prizes.map(p=><li key={p.id}>{p.name}</li>)}</ul><p role="status">{message}</p>{!ready&&<button className="secondary" onClick={()=>void refresh()}>重新讀取獎池</button>}{result&&<dialog ref={dialog} className="demo-result" onClose={closeResult} aria-label="示範抽獎結果"><p className="demo-notice">示範，暫不可兌換</p><ArtIcon name={result.prize.icon}/><h3>{result.prize.name}</h3><p>{result.prize.terms}</p><p>僅為虛構體驗，沒有兌換碼、金錢價值或真實商家權益，不會加入正式券夾。</p><button className="primary" onClick={()=>dialog.current?.close()}>知道了</button></dialog>}</section>;
}
