'use client';
import {useEffect,useState} from 'react';
import {Capacitor} from '@capacitor/core';
type InstallEvent=Event&{prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>};
export default function PwaRegistration(){
 const [offline,setOffline]=useState(false),[install,setInstall]=useState<InstallEvent|null>(null),[update,setUpdate]=useState(false);
 useEffect(()=>{
  if(Capacitor.isNativePlatform())return;
  let alive=true;
  const connectivity=()=>setOffline(!navigator.onLine);
  const available=(event:Event)=>{event.preventDefault();setInstall(event as InstallEvent);};
  const installed=()=>setInstall(null);
  connectivity();window.addEventListener('online',connectivity);window.addEventListener('offline',connectivity);window.addEventListener('beforeinstallprompt',available);window.addEventListener('appinstalled',installed);
  if('serviceWorker' in navigator&&window.isSecureContext){
   void navigator.serviceWorker.register('/sw.js',{scope:'/'}).then(registration=>{
    if(!alive)return;
    if(registration.waiting)setUpdate(true);
    registration.addEventListener('updatefound',()=>{
     const worker=registration.installing;
     worker?.addEventListener('statechange',()=>{if(alive&&worker.state==='installed'&&navigator.serviceWorker.controller)setUpdate(true);});
    });
   }).catch(()=>{});
  }
  return()=>{alive=false;window.removeEventListener('online',connectivity);window.removeEventListener('offline',connectivity);window.removeEventListener('beforeinstallprompt',available);window.removeEventListener('appinstalled',installed);};
 },[]);
 return <>{offline&&<p role="status" style={{margin:0,padding:'10px 16px',background:'#fff0ce',color:'#563d12'}}>目前離線，連線後再操作。</p>}{install&&<button type="button" className="secondary" onClick={async()=>{const event=install;setInstall(null);try{await event.prompt();await event.userChoice;}catch{}}}>安裝到主畫面</button>}{update&&<p role="status">有新版可用。請先完成手邊操作，再關閉所有食在可惜頁面後重新開啟。</p>}</>;
}
