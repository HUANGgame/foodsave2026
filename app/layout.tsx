import './globals.css';
import LiveShell from '../components/LiveShell';
import PwaRegistration from '../components/PwaRegistration';
import type { Metadata, Viewport } from 'next';
export const metadata:Metadata={title:'食在可惜｜好食物・不浪費',description:'食在可惜核心流程測試版',manifest:'/manifest.webmanifest',icons:{icon:'/icons/foodsave.svg'},appleWebApp:{capable:true,title:'食在可惜',statusBarStyle:'default'}};
export const viewport:Viewport={width:'device-width',initialScale:1,viewportFit:'cover',themeColor:'#12684b'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="zh-Hant"><body><PwaRegistration/><LiveShell>{children}</LiveShell></body></html>}
