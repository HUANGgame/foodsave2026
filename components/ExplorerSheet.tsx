'use client';
import {useRef,useState} from 'react';
import styles from './FoodExplorer.module.css';
export default function ExplorerSheet({children,storeId}:{children:React.ReactNode;storeId:string}){
 const [open,setOpen]=useState(true),start=useRef<{y:number;pointer:number}|null>(null),dragged=useRef(false);
 return <section className={styles.sheet} data-store-id={storeId}>
  <button className={styles.sheetHandle} aria-expanded={open} aria-label={open?'收起店家詳情':'展開店家詳情'}
   onPointerDown={e=>{start.current={y:e.clientY,pointer:e.pointerId};dragged.current=false;e.currentTarget.setPointerCapture(e.pointerId);}}
   onPointerUp={e=>{const s=start.current;start.current=null;if(!s||s.pointer!==e.pointerId)return;const d=e.clientY-s.y;if(Math.abs(d)>24){dragged.current=true;setOpen(d<0);}if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
   onPointerCancel={()=>{start.current=null;dragged.current=false;}}
   onClick={()=>{if(dragged.current){dragged.current=false;return;}setOpen(v=>!v);}}>
   <span aria-hidden="true"/>{open?'收起店家詳情':'展開店家詳情'}
  </button>
  {open?<div>{children}</div>:<p className={styles.collapsed}>已收起商品卡。點上方按鈕，或向上滑動把手查看。</p>}
 </section>;
}
