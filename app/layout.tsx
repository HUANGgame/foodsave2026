import './globals.css';
import LiveShell from '../components/LiveShell';
import type { Metadata, Viewport } from 'next';
export const metadata:Metadata={title:'食在可惜｜好食物・不浪費',description:'食在可惜核心流程測試版'};
export const viewport:Viewport={width:'device-width',initialScale:1,viewportFit:'cover',themeColor:'#12684b'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="zh-Hant"><body><LiveShell>{children}</LiveShell></body></html>}
