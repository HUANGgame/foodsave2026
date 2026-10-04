import ConvenienceApp from './ConvenienceApp';
import FoodApp from './FoodApp';
export default function AppEntry({screen}:{screen:string}){
 if(screen==='convenience')return <ConvenienceApp/>;
 const mode=process.env.NEXT_PUBLIC_APP_MODE||'demo';
 if(mode==='live')return null; // Persistent LiveShell owns live route state.
 if(mode==='demo')return <FoodApp screen={screen}/>;
 return <main className="page"><h1>應用程式設定有誤</h1><p>APP_MODE必須明確設為live或demo。</p></main>;
}
