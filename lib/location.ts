import {Capacitor} from '@capacitor/core';
import {Geolocation} from '@capacitor/geolocation';
export type Point=[number,number];
export async function currentPosition():Promise<Point>{
 try{
  const native=Capacitor.isNativePlatform();
  if(native){const permission=await Geolocation.requestPermissions();if(permission.location!=='granted'&&permission.coarseLocation!=='granted')throw {code:1};}
  if(!native&&!navigator.geolocation)throw {code:2};
  const result=native?await Geolocation.getCurrentPosition({enableHighAccuracy:true,timeout:10000}):await new Promise<GeolocationPosition>((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:10000}));
  return [result.coords.latitude,result.coords.longitude];
 }catch(error){const code=(error as {code?:number|string})?.code;throw new Error(code===1||code==='OS-PLUG-GLOC-0003'?'未允許定位，請在裝置設定開啟權限。':code===3||code==='OS-PLUG-GLOC-0010'?'定位逾時，請稍後重試。':'目前無法取得位置，請檢查裝置定位服務。');}
}
export function snapshotNavigation(snapshot:unknown):string|null{
 try{
  const data=typeof snapshot==='string'?JSON.parse(snapshot):snapshot;
  if(!data||typeof data!=='object'||data.latitude==null||data.longitude==null)return null;
  const lat=Number(data.latitude),lng=Number(data.longitude);
  if(!Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180)return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=walking`;
 }catch{return null;}
}
