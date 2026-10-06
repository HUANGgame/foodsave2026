'use client';
import {useEffect,useRef} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type {Point} from '../lib/location';
export default function LocationPicker({value,onChange,disabled=false}:{value:Point;onChange:(point:Point)=>void;disabled?:boolean}){
 const host=useRef<HTMLDivElement>(null),map=useRef<L.Map|null>(null),marker=useRef<L.Marker|null>(null),change=useRef(onChange),locked=useRef(disabled);
 change.current=onChange;locked.current=disabled;
 useEffect(()=>{
  if(!host.current)return;
  const m=L.map(host.current).setView(value,17);map.current=m;
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(m);
  const pin=L.marker(value,{draggable:!locked.current,title:'拖曳調整店址',icon:L.divIcon({className:'location-pin',html:'<span aria-hidden="true">📍</span>',iconSize:[44,44],iconAnchor:[22,40]})}).addTo(m);marker.current=pin;
  pin.on('dragend',()=>{if(!locked.current){const p=pin.getLatLng();change.current([p.lat,p.lng]);}});
  const choose=(e:L.LeafletMouseEvent)=>{if(!locked.current)change.current([e.latlng.lat,e.latlng.lng]);};
  m.on('click',choose);
  return()=>{m.remove();map.current=null;marker.current=null;};
 },[]);
 useEffect(()=>{marker.current?.setLatLng(value);if(map.current&&!map.current.getBounds().contains(value))map.current.panTo(value);},[value]);
 useEffect(()=>{if(disabled)marker.current?.dragging?.disable();else marker.current?.dragging?.enable();},[disabled]);
 return <div ref={host} className="location-map" aria-label="店址草稿地圖"/>;
}
