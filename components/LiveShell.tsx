'use client';
import {usePathname} from 'next/navigation';
import {useLayoutEffect,useRef} from 'react';
import LiveApp from './LiveApp';
const screens=new Set(['','favorites','missions','profile','reservations','vendor','notifications','coupons']);
export default function LiveShell({children}:{children:React.ReactNode}){
 const pathname=usePathname(),name=pathname.replace(/^\/+|\/+$/g,'');
 const active=process.env.NEXT_PUBLIC_APP_MODE==='live'&&screens.has(name);
 const previous=useRef(pathname),positions=useRef(new Map<string,number>()),scroll=useRef(0),navigating=useRef(false);
 useLayoutEffect(()=>{
  const save=()=>{positions.current.set(previous.current,window.scrollY);navigating.current=true;};
  const click=(e:MouseEvent)=>{const anchor=(e.target as Element)?.closest?.('a[href]');if(!anchor||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;const target=new URL(anchor.getAttribute('href')!,location.href);if(target.origin===location.origin&&target.pathname!==previous.current)save();};
  const track=()=>{if(!navigating.current)scroll.current=window.scrollY;};
  document.addEventListener('click',click,true);window.addEventListener('popstate',save);window.addEventListener('scroll',track,{passive:true});
  return()=>{document.removeEventListener('click',click,true);window.removeEventListener('popstate',save);window.removeEventListener('scroll',track);};
 },[]);
 useLayoutEffect(()=>{if(!navigating.current)positions.current.set(previous.current,scroll.current);previous.current=pathname;const y=positions.current.get(pathname)||0;scroll.current=y;window.scrollTo(0,y);scroll.current=y;navigating.current=false;},[pathname]);
 return active?<LiveApp screen={name||'map'}/>:children;
}
