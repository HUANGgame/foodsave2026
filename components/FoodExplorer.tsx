'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import dynamic from 'next/dynamic';
import type {Point} from '../lib/location';
import {watchLocation} from '../lib/location-follow';
import type {ExplorerFilter} from '../lib/explorer-catalog';
import {distanceMeters} from '../lib/explorer-catalog';
import type {ExternalStore} from '../lib/familymart';
import styles from './FoodExplorer.module.css';
const ExplorerMap=dynamic(()=>import('./ExplorerMap'),{ssr:false,loading:()=> <p role="status">地圖載入中…</p>});
export type ExplorerMarker={id:string;name:string;lat:number;lng:number;count:number|null;source:'foodsave'|'family'};
const AREAS=[
 {id:'taipei-station',name:'台北車站',point:[25.0478,121.517] as Point},
 {id:'taipei-xinyi',name:'臺北市信義區',point:[25.0375197,121.5636704] as Point},
 {id:'banqiao',name:'新北市板橋區',point:[25.014,121.464] as Point},
 {id:'taoyuan',name:'桃園市桃園區',point:[24.993,121.301] as Point},
 {id:'taichung',name:'臺中市西區',point:[24.141,120.663] as Point},
 {id:'tainan',name:'臺南市中西區',point:[22.994,120.196] as Point},
 {id:'kaohsiung',name:'高雄市苓雅區',point:[22.625,120.314] as Point},
];
type Props={familyOpen:boolean;center:Point|null;gpsPoint:Point|null;active:boolean;busy:boolean;stores:ExplorerMarker[];familyStores:ExternalStore[];query:string;filter:ExplorerFilter;onQuery:(query:string)=>void;onFilter:(filter:ExplorerFilter)=>void;onCenter:(point:Point)=>void;onLocate:()=>void;onSelect:(id:string)=>void;onFamilySelection:(selected:boolean)=>void};
export default function FoodExplorer({familyOpen,center,gpsPoint,active,busy,stores,familyStores,query,filter,onQuery,onFilter,onCenter,onLocate,onSelect,onFamilySelection}:Props){
 const [area,setArea]=useState(AREAS[0].id),[device,setDevice]=useState<Point|null>(gpsPoint),[heading,setHeading]=useState<number|null>(null),[follow,setFollow]=useState(false),[viewport,setViewport]=useState<Point|null>(center),[message,setMessage]=useState(''),[recenter,setRecenter]=useState(0),[familySelected,setFamilySelected]=useState('');
 const stopRef=useRef<null|(()=>void)>(null),watchEpoch=useRef(0);
 const stop=useCallback(()=>{watchEpoch.current++;stopRef.current?.();stopRef.current=null;setFollow(false);},[]);
 useEffect(()=>{setDevice(gpsPoint);if(gpsPoint)setRecenter(v=>v+1);},[gpsPoint]);
 useEffect(()=>{if(center)setViewport(center);},[center]);
 useEffect(()=>{if(!active)stop();const hide=()=>{if(document.visibilityState!=='visible')stop();};document.addEventListener('visibilitychange',hide);return()=>{document.removeEventListener('visibilitychange',hide);stop();};},[active,stop]);
 function start(){
  if(!active||follow)return;stop();const epoch=++watchEpoch.current;setMessage('跟隨已開啟；拖曳地圖會停止跟隨。查詢範圍仍以最後確認的中心為準。');setFollow(true);
  const cleanup=watchLocation(fix=>{if(watchEpoch.current!==epoch)return;setDevice(fix.point);setHeading(fix.heading);},text=>{if(watchEpoch.current!==epoch)return;setMessage(text);stop();});
  if(watchEpoch.current!==epoch)cleanup();else stopRef.current=cleanup;
 }
 function confirm(point:Point){stop();setViewport(point);setFamilySelected('');onFamilySelection(false);onCenter(point);}
 function select(id:string){if(id.startsWith('family:')){setFamilySelected(id.slice(7));onFamilySelection(true);}else{setFamilySelected('');onFamilySelection(false);onSelect(id);}}
 const family=familyOpen?familyStores.find(s=>s.id===familySelected):undefined;
 const km=family&&center?distanceMeters(center,[family.latitude,family.longitude]):null;
 useEffect(()=>{if(familySelected&&!family){setFamilySelected('');onFamilySelection(false);}},[familySelected,family,onFamilySelection]);
 return <section className={styles.explorer} aria-label="探索篩選與地圖">
  <div className={styles.toolbar}>
   <label className={styles.search}>搜尋本次店家或商品<input aria-label="搜尋本次店家或商品" value={query} onChange={e=>onQuery(e.target.value)} placeholder="店名、商品；全家也可搜尋地址"/>{query&&<button type="button" onClick={()=>onQuery('')} aria-label="清除搜尋">清除</button>}</label>
   <div className={styles.filters} role="group" aria-label="商品價格篩選">{([['all','全部'],['free','免費'],['discount','折扣']] as const).map(([value,label])=><button type="button" key={value} aria-pressed={filter===value} onClick={()=>onFilter(value)}>{label}</button>)}</div>
   <div className={styles.manual}><label>選擇公開地區<select aria-label="選擇公開地區" value={area} onChange={e=>setArea(e.target.value)}>{AREAS.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><button type="button" disabled={busy} onClick={()=>confirm(AREAS.find(a=>a.id===area)!.point)}>查詢這個地區</button></div>
   <p className={styles.hint}>手選僅使用公開地區座標，不需要裝置定位。FoodSave 查詢中心 1 公里；全家僅篩選本次已取得資料，並非全台搜尋。距離為直線距離。</p>
  </div>
  {center?<ExplorerMap center={center} devicePosition={device} stores={stores} onSelect={select} onManualMove={stop} onViewportCenter={setViewport} recenterVersion={recenter} heading={heading} follow={follow}/>:<p className={styles.placeholder}>尚未定位。選一個公開地區，即可拖曳地圖找附近店家。</p>}
  <div className={styles.actions}>
   <button type="button" disabled={busy} onClick={()=>{stop();onLocate();}}>重新定位</button>
   <button type="button" disabled={!active||busy} aria-pressed={follow} onClick={()=>follow?stop():start()}>{follow?'停止跟隨':'開啟跟隨'}</button>
   {center&&viewport&&<button type="button" disabled={busy} onClick={()=>confirm(viewport)}>搜尋此區域</button>}
  </div>
  <p className={styles.hint}>跟隨只在探索頁前景使用定位，不保存位置歷程；拖曳、切頁或背景會停止。底圖服務 OpenStreetMap 可能推知位置區域；點「搜尋此區域」才將查詢中心座標送給 FoodSave 與全家。</p>
  {message&&<p role="status">{message}</p>}
  <p className={styles.hint}>共顯示 {stores.filter(s=>s.source==='foodsave').length} 間 FoodSave 店家、{stores.filter(s=>s.source==='family').length} 間全家門市。全家目前最多保留本次 200 店、每店 200 項來源商品；查無結果不代表已售完。</p>
  {family&&<section className={styles.familyCard} aria-label="選取的全家門市"><h2>{family.name}</h2><p>{family.address}{km!==null?' · 距查詢中心 '+Math.round(km)+' 公尺':''}</p><p>友善食光資訊；是否適用與售價以門市結帳為準。不能在此預約或核銷。</p><p>來源更新：{family.sourceUpdatedAt?new Date(family.sourceUpdatedAt).toLocaleString('zh-TW'):'未知'}；資料可能已變動。</p><a className="secondary" href={'https://www.google.com/maps/dir/?api=1&destination='+family.latitude+','+family.longitude+'&travelmode=walking'} target="_blank" rel="noreferrer">步行導航</a>{family.products.map(p=><article key={p.id}><h3>{p.name}</h3><p>{p.quantity===null?'數量未知':p.quantity+' 份（來源回報）'}</p></article>)}<button type="button" onClick={()=>{setFamilySelected('');onFamilySelection(false);}}>收起門市</button></section>}
 </section>;
}
