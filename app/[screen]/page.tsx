import AppEntry from '../../components/AppEntry';
export function generateStaticParams(){return ['favorites','missions','profile','reservations','vendor','notifications','coupons','convenience'].map(screen=>({screen}));}
export default async function Page({params}:{params:Promise<{screen:string}>}){const {screen}=await params;return <AppEntry screen={screen}/>;}
