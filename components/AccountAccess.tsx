'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {api} from '../lib/api';

export default function AccountAccess({mode,onClose}:{mode:'register'|'reset';onClose:()=>void}){
 const [email,setEmail]=useState(''),[requested,setRequested]=useState(false),[busy,setBusy]=useState(false),[done,setDone]=useState(false),[message,setMessage]=useState(''),[enabled,setEnabled]=useState(false),[loaded,setLoaded]=useState(false);
 const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;api.request<{registration_enabled:boolean;recovery_enabled:boolean}>('/auth/options').then(r=>{if(alive.current)setEnabled(mode==='register'?r.registration_enabled:r.recovery_enabled);}).catch(()=>{if(alive.current)setMessage('無法確認帳號服務設定，請稍後再試。');}).finally(()=>{if(alive.current)setLoaded(true);});return()=>{alive.current=false;};},[mode]);
 async function submit(form:HTMLFormElement){
  if(lock.current||!enabled)return;lock.current=true;setBusy(true);setMessage('');const values=new FormData(form);
  try{
   if(!requested){const r=await api.request<{detail:string}>(mode==='register'?'/auth/register':'/auth/forgot-password','POST',{email});if(alive.current){setRequested(true);setMessage(r.detail);}}
   else{
    const password=String(values.get('password')),confirm=String(values.get('confirm'));
    if(password!==confirm)throw new Error('兩次新密碼不一致。');
    const r=await api.request<{detail:string}>(mode==='register'?'/auth/verify-email':'/auth/reset-password','POST',{email,code:String(values.get('code')).trim(),password});
    if(alive.current){setDone(true);setMessage(r.detail);}
   }
  }catch(e){if(alive.current)setMessage(e instanceof Error?e.message:'操作未完成，請稍後再試。');}
  finally{if(requested)form.reset();lock.current=false;if(alive.current)setBusy(false);}
 }
 return <section className="live-form"><h1>{mode==='register'?'驗證信箱並建立帳號':'找回密碼'}</h1><p>{mode==='register'?'先驗證你能收信，再由你設定密碼；只會建立消費者帳號。':'郵件不會顯示原密碼。重設成功後，所有裝置的舊登入都會失效。'}</p><p>驗證碼15分鐘有效、只能用一次；再次寄信會讓前一封失效。不要把驗證碼或密碼交給他人。若送出新密碼後斷線，請先嘗試新密碼登入。</p>{loaded&&!enabled&&<p role="alert">後端尚未開放此帳號服務，請聯絡管理者；不會略過信箱驗證。</p>}{!done&&<form onSubmit={e=>{e.preventDefault();void submit(e.currentTarget);}}><label>電子郵件<input name="email" type="email" required maxLength={254} autoComplete="email" value={email} readOnly={requested} disabled={busy} onChange={e=>setEmail(e.target.value)}/></label>{requested&&<><label>信箱驗證碼<input name="code" required minLength={43} maxLength={43} pattern="[A-Za-z0-9_-]{43}" autoComplete="one-time-code" autoCapitalize="none" spellCheck={false}/></label><label>新密碼（至少15字元）<input name="password" type="password" minLength={15} maxLength={128} required autoComplete="new-password"/></label><label>再次輸入新密碼<input name="confirm" type="password" minLength={15} maxLength={128} required autoComplete="new-password"/></label></>}{mode==='register'&&<label><input type="checkbox" required/>我已閱讀<Link href="/privacy/">隱私及帳號刪除說明</Link></label>}<button className="primary" disabled={busy||!enabled}>{busy?'正在確認…':requested?(mode==='register'?'驗證並建立帳號':'確認重設密碼'):'寄送驗證碼'}</button></form>}<p role="status">{message}</p>{requested&&!done&&<button className="secondary" disabled={busy} onClick={()=>{setRequested(false);setMessage('重新寄信仍受配額限制，舊碼將失效。');}}>重新申請驗證碼／更換信箱</button>}<button className="text-button" disabled={busy} onClick={onClose}>返回登入</button></section>;
}

export function ChangePassword({onChanged}:{onChanged:()=>void}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');const lock=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 async function submit(form:HTMLFormElement){if(lock.current)return;lock.current=true;setBusy(true);setMessage('');const values=new FormData(form);
  try{const password=String(values.get('password'));if(password!==String(values.get('confirm')))throw new Error('兩次新密碼不一致。');await api.request('/auth/change-password','POST',{current_password:String(values.get('current_password')),password});api.clear();if(alive.current)onChanged();}
  catch(e){if(alive.current)setMessage(e instanceof Error?e.message:'操作未完成。');}
  finally{form.reset();lock.current=false;if(alive.current)setBusy(false);}
 }
 return <section><button className="secondary" onClick={()=>setOpen(!open)} disabled={busy}>變更密碼</button>{open&&<form className="card live-form" onSubmit={e=>{e.preventDefault();void submit(e.currentTarget);}}><p>需確認目前密碼；成功後所有裝置都會登出。若連線回覆遺失，請先嘗試新密碼登入，勿反覆送出。</p><label>目前密碼<input name="current_password" type="password" minLength={12} maxLength={128} autoComplete="current-password" required/></label><label>新密碼（至少15字元）<input name="password" type="password" minLength={15} maxLength={128} autoComplete="new-password" required/></label><label>再次輸入新密碼<input name="confirm" type="password" minLength={15} maxLength={128} autoComplete="new-password" required/></label><button className="primary" disabled={busy}>確認變更密碼</button><p role="status">{message}</p></form>}</section>;
}
