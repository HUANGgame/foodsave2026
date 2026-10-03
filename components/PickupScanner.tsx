'use client';
import {useEffect,useRef} from 'react';
export default function PickupScanner({onScan,onStop}:{onScan:(value:string)=>void;onStop:(message:string)=>void}){
 const video=useRef<HTMLVideoElement>(null),scan=useRef(onScan),stop=useRef(onStop);scan.current=onScan;stop.current=onStop;
 useEffect(()=>{let cancelled=false,stream:MediaStream|undefined,controls:{stop:()=>void}|undefined;
  const release=()=>{controls?.stop();stream?.getTracks().forEach(t=>t.stop());};
  const end=(message:string)=>{if(cancelled)return;cancelled=true;release();stop.current(message);};
  const hidden=()=>{if(document.hidden)end('相機已暫停，返回後可重新掃碼');};
  document.addEventListener('visibilitychange',hidden);
  const timeout=setTimeout(()=>end('尚未掃到取貨碼，可重試或手動輸入'),60000);
  (async()=>{try{const {BrowserQRCodeReader}=await import('@zxing/browser');if(cancelled)return;
    stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
    if(cancelled){release();return;}
    controls=await new BrowserQRCodeReader().decodeFromStream(stream,video.current!,result=>{if(cancelled||!result)return;const value=result.getText();cancelled=true;release();scan.current(value);});
    if(cancelled)release();
   }catch{end('無法使用相機，請允許相機權限或手動輸入取貨碼');}})();
  return()=>{cancelled=true;clearTimeout(timeout);document.removeEventListener('visibilitychange',hidden);release();};
 },[]);
 return <div className="pickup-camera"><video ref={video} muted playsInline autoPlay aria-label="取貨碼掃描相機"/><p>對準取貨碼；掃到後還需確認交付。</p><button className="secondary" onClick={()=>stop.current('相機已關閉，可手動輸入取貨碼')}>關閉相機／手動輸入</button></div>;
}
