import {Capacitor} from '@capacitor/core';
import {Geolocation} from '@capacitor/geolocation';
import type {Point} from './location';
export type LocationFix={point:Point;heading:number|null;accuracy:number|null};
export function validLocation(latitude:number,longitude:number){return Number.isFinite(latitude)&&Number.isFinite(longitude)&&Math.abs(latitude)<=90&&Math.abs(longitude)<=180;}
/** Explicitly started foreground watch. The returned stop handles late native IDs. */
export function watchLocation(onFix:(fix:LocationFix)=>void,onError:(message:string)=>void):()=>void{
 let stopped=false,webId:number|undefined,nativeId:string|undefined;
 const receive=(coords:{latitude:number;longitude:number;heading?:number|null;accuracy?:number})=>{
  if(stopped||!validLocation(coords.latitude,coords.longitude))return;
  onFix({point:[coords.latitude,coords.longitude],heading:typeof coords.heading==='number'&&Number.isFinite(coords.heading)?((coords.heading%360)+360)%360:null,accuracy:typeof coords.accuracy==='number'&&Number.isFinite(coords.accuracy)?coords.accuracy:null});
 };
 const failed=()=>{if(!stopped)onError('定位中斷，已停止跟隨。仍可拖曳地圖或手選地區。');};
 if(Capacitor.isNativePlatform()){
  void (async()=>{
   const permission=await Geolocation.requestPermissions();
   if(stopped)return;
   if(permission.location!=='granted'&&permission.coarseLocation!=='granted'){failed();return;}
   const id=await Geolocation.watchPosition({enableHighAccuracy:true,timeout:15000,maximumAge:5000},(position,error)=>{
    if(error||!position){failed();return;}receive(position.coords);
   });
   nativeId=id;if(stopped)await Geolocation.clearWatch({id});
  })().catch(failed);
 }else if(typeof navigator!=='undefined'&&navigator.geolocation){
  webId=navigator.geolocation.watchPosition(p=>receive(p.coords),failed,{enableHighAccuracy:true,timeout:15000,maximumAge:5000});
 }else failed();
 return()=>{if(stopped)return;stopped=true;if(webId!==undefined)navigator.geolocation.clearWatch(webId);if(nativeId!==undefined)void Geolocation.clearWatch({id:nativeId}).catch(()=>{});};
}
