import ConvenienceApp from './ConvenienceApp';
export default function AppEntry({screen}:{screen:string}){
 if(screen==='convenience')return <ConvenienceApp/>;
 const mode=process.env.NEXT_PUBLIC_APP_MODE||'demo';
 if(mode==='live')return null; // Persistent LiveShell owns live route state.
 // Keep the demo client module out of Next's live client-reference graph.
 // Use the build-time expression directly so webpack can omit the dependency.
 if(process.env.NEXT_PUBLIC_APP_MODE==='demo'||!process.env.NEXT_PUBLIC_APP_MODE){
  const FoodApp=require('./FoodApp').default;
  return <FoodApp screen={screen}/>;
 }
 return <main className="page"><h1>應用程式設定有誤</h1><p>APP_MODE必須明確設為live或demo。</p></main>;
}
