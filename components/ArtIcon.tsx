import {Coffee,Ticket,Leaf,Gift,Heart} from 'lucide-react';
import Frog from './Frog';
import {artAssets} from '../lib/art-assets';
export default function ArtIcon({name}:{name:string}){
 const asset=artAssets[name]||artAssets.gift;
 if(asset.src)return <img src={asset.src} alt="" className="art-icon"/>;
 if(name==='frog')return <span className="art-icon"><Frog/></span>;
 const Icon=({coffee:Coffee,ticket:Ticket,leaf:Leaf,gift:Gift,heart:Heart} as Record<string,typeof Gift>)[name]||Gift;
 return <Icon className="art-icon" aria-hidden="true"/>;
}
