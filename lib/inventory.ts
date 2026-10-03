/** External providers are information only until an explicit integration exists. */
export type ServiceMode='information'|'reservation';
export type InventoryInfo={source:'foodsave'|'seven-eleven'|'familymart';service_mode:ServiceMode;count:number|null;sourceUpdatedAt:string|null;checkedAt:string|null;stale:boolean;sourceURL:string|null};
export function canReserve(item:{source?:string;service_mode?:string}){return item.source==='foodsave'&&item.service_mode==='reservation';}
export function stockLabel(count:number|null|undefined){return count==null?'數量待確認':`剩餘 ${count} 份`;}
