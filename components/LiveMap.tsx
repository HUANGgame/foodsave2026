'use client';
import {useEffect,useRef} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
export type MapStore={id:string;name:string;lat:number;lng:number;count:number|null};
export default function LiveMap({center,stores,onSelect}:{center:[number,number];stores:MapStore[];onSelect:(id:string)=>void}){
 const host=useRef<HTMLDivElement>(null),map=useRef<L.Map|null>(null),layer=useRef<L.LayerGroup|null>(null);
 useEffect(()=>{if(!host.current)return;const m=L.map(host.current).setView(center,15);map.current=m;L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(m);layer.current=L.layerGroup().addTo(m);return()=>{m.remove();map.current=null;};},[]);
 useEffect(()=>{map.current?.setView(center,15);},[center]);
 useEffect(()=>{const group=layer.current;if(!group)return;group.clearLayers();L.circleMarker(center,{radius:7,color:'#fff',fillColor:'#398dcc',fillOpacity:1}).addTo(group);for(const store of stores){const text=document.createElement('span');text.textContent=store.name;L.marker([store.lat,store.lng],{title:store.name,icon:L.divIcon({className:'store-marker',html:`<span>${store.count===null?'？':Math.max(0,Math.floor(store.count))}</span>`,iconSize:[44,44]})}).addTo(group).bindTooltip(text).on('click',()=>onSelect(store.id));}},[stores,center,onSelect]);
 return <div ref={host} className="map-canvas live-map-canvas" aria-label="附近店家地圖"/>;
}
