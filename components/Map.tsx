'use client';
import {useEffect,useRef,useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {stores} from '../lib/demo';
export default function Map({center,items,onSelect}:{center:[number,number];items:{id:string;count:number}[];onSelect:(id:string)=>void}){
 const [failed,setFailed]=useState(false);
 const host=useRef<HTMLDivElement>(null),map=useRef<L.Map|null>(null),markers=useRef<L.LayerGroup|null>(null);
 useEffect(()=>{if(!host.current)return;const m=L.map(host.current,{zoomControl:false}).setView(center,16);map.current=m;
 L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',maxZoom:19}).on('tileerror',()=>setFailed(true)).addTo(m);
 L.control.zoom({position:'bottomright'}).addTo(m);markers.current=L.layerGroup().addTo(m);return()=>{m.remove();map.current=null;};},[]);
 useEffect(()=>{map.current?.setView(center,16);},[center]);
 useEffect(()=>{const layer=markers.current;if(!layer)return;layer.clearLayers();L.circleMarker(center,{radius:8,color:'white',weight:3,fillColor:'#3487ec',fillOpacity:1}).addTo(layer).bindTooltip('搜尋中心');
 items.forEach(item=>{const s=stores.find(s=>s.id===item.id)!;L.marker([s.lat,s.lng],{icon:L.divIcon({className:'store-marker',html:`<span>${item.count}</span>`,iconSize:[44,44],iconAnchor:[22,22]}),title:s.name,keyboard:true}).addTo(layer).bindTooltip(s.name).on('click',()=>onSelect(s.id));});},[items,center,onSelect]);
 return <><div className="map-canvas" ref={host} aria-label="附近惜食店家地圖"/>{failed&&<span className="map-unavailable">底圖暫時無法載入，仍可點選店家</span>}</>;
}
