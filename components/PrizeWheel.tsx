'use client';
import {useEffect,useRef,useState} from 'react';
import {api,Draw,Prize,utc} from '../lib/api';
import Frog from './Frog';
const colors=['#daefd7','#fff0c6','#cfe7ed','#ffe3d4','#dce6cb','#e8dded'];
export default function PrizeWheel({spins,onResult,onError}:{spins:number;onResult:()=>void;onError:(e:unknown)=>void}){
 const [prizes,setPrizes]=useState<Prize[]>([]),[busy,setBusy]=useState(false),[result,setResult]=useState<Draw|null>(null),[angle,setAngle]=useState(0),[phase,setPhase]=useState(''),[history,setHistory]=useState<{id:string;prize_snapshot:string;coupon_code?:string}[]>([]);
 const lock=useRef(false),mounted=useRef(true),wheel=useRef<HTMLDivElement>(null);
 const canResume=api.hasPending('draw');
 useEffect(()=>{mounted.current=true;Promise.all([api.request<Prize[]>('/prizes'),api.request<typeof history>('/draws')]).then(([p,h])=>{if(mounted.current){setPrizes(p);setHistory(h);}}).catch(onError);return()=>{mounted.current=false;};},[]);
 async function spin(){if(lock.current)return;lock.current=true;setBusy(true);setResult(null);setPhase('正在確認抽獎結果…');
  try{const draw=await api.mutate<Draw>('draw','/draws',{});if(!mounted.current)return;
   setPrizes(draw.segments);setPhase('結果已保存，正在揭曉');
   const index=draw.segments.findIndex(p=>p.id===draw.prize.id);if(index<0||draw.segments.length===0)throw new Error('獎項顯示資料不完整，請從獲獎紀錄確認。');
   const step=360/draw.segments.length,target=(360-(index+.5)*step)%360;
   const destination=angle+360*5+((target-angle%360+360)%360);
   // Animate only after the authoritative result and all segments have rendered.
   await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
   if(!mounted.current)return;
   const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
   const animation=wheel.current?.animate([{transform:`rotate(${angle}deg)`},{transform:`rotate(${destination}deg)`}],{duration:reduced?0:3200,easing:'cubic-bezier(.12,.72,.12,1)',fill:'forwards'});
   setAngle(destination);
   if(animation)try{await animation.finished;}catch{}
   if(!mounted.current)return;animation?.cancel();setResult(draw);setPhase('獎品已存入獲獎紀錄');onResult();
   setHistory(await api.request<typeof history>('/draws'));
  }catch(e){onError(e);setPhase('請重試或查看獲獎紀錄；不會因重試重複扣除。');}
  finally{lock.current=false;if(mounted.current)setBusy(false);}
 }
 async function recover(){try{setHistory(await api.request<typeof history>('/draws'));onResult();setPhase('已重新讀取後端獲獎紀錄');}catch(e){onError(e);}}
 const count=Math.max(1,prizes.length),background=prizes.length?`conic-gradient(${prizes.map((_,i)=>`${colors[i%6]} ${i*360/count}deg ${(i+1)*360/count}deg`).join(',')})`:'#e6eee1';
 return <section className="wheel-section"><h2>幸運惜食轉盤</h2><p>可用次數 <b>{spins}</b> · 每次成果都值得珍惜</p><div className="wheel-wrap"><span className="wheel-pointer" aria-hidden="true">▼</span><div ref={wheel} className="prize-wheel" style={{background,transform:`rotate(${angle}deg)`}} aria-hidden="true">{prizes.map((p,i)=><span className="wheel-label" key={p.id} style={{transform:`translate(-50%,-50%) rotate(${(i+.5)*360/count}deg) translateY(-98px) rotate(90deg)`}}>{p.name}</span>)}</div><button className="wheel-start" onClick={spin} disabled={busy||(!canResume&&(spins<1||!prizes.length))}>{busy?'揭曉中':canResume?'確認上次結果':'開始惜食抽獎'}</button></div><p role="status">{phase||(!prizes.length?'店家尚未開放獎品，請稍後再來。':spins<1?'完成已開放任務，累積下一次機會。':'點一下，看看這次珍惜了什麼。')}</p><ul className="wheel-prize-list">{prizes.map(p=><li key={p.id}>{p.name}</li>)}</ul>
 {result&&<div className="reward-card" role="status"><Frog harvest/><h3>獲得 {result.prize.name}</h3><p>{result.prize.terms}</p>{result.coupon_code&&<p>兌換碼：<code>{result.coupon_code}</code></p>}{result.prize.expires_at&&<p>有效至 {utc(result.prize.expires_at).toLocaleString('zh-TW')}</p>}</div>}
 <button className="secondary" onClick={recover}>重新確認獲獎紀錄</button><h3>我的獲獎紀錄</h3>{history.length===0?<p>還沒有獲獎紀錄。</p>:history.map(h=>{const p=JSON.parse(h.prize_snapshot) as Prize;return <article className="card" key={h.id}><h3>{p.name}</h3><p>{p.terms}</p>{h.coupon_code&&<code>{h.coupon_code}</code>}{p.expires_at&&<p>有效至 {utc(p.expires_at).toLocaleString('zh-TW')}</p>}</article>;})}</section>;
}
