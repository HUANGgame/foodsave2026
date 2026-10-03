import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';
async function setup(page:any,{role='consumer',mode='information',pending=0,source='foodsave',count=3}:any={}){
 let updates=0;
 await page.route('https://api.foodsave.test/**',async(route:any)=>{const req=route.request(),path=new URL(req.url()).pathname;const json=(body:any)=>route.fulfill({json:body});
  if(req.method()==='OPTIONS')return route.fulfill({status:204});
  if(path==='/auth/login')return json({access_token:randomUUID()});
  if(path==='/me')return json({id:role,email:role+'@example.test',role,exp:0,spins:0});
  if(path==='/products')return json([{id:'p',store_id:'s',store_name:'資訊店家',name:'資訊餐盒',latitude:0,longitude:0,photo_url:'https://images.example.test/p.png',original_price_minor:10000,sale_price_minor:5000,available_quantity:count,pickup_deadline:'2027-01-01T12:00:00',revision:1,source,service_mode:mode,sourceUpdatedAt:null,checkedAt:'2026-10-03T08:00:00',stale:true}]);
  if(path==='/vendor/catalog')return json({stores:[{id:'s',name:'資訊店家',service_mode:mode,pending_orders:pending}],products:[]});
  if(path==='/vendor/stores/s/mode'){updates++;mode=req.postDataJSON().service_mode;return json({id:'s',service_mode:mode});}
  if(path==='/vendor/stores/s/expire'){pending=0;return json({expired_count:1});}
  if(path.startsWith('/stores/'))return json({average:null,count:0,items:[]});
  return json([]);
 });
 await page.route('https://images.example.test/**',(r:any)=>r.abort());await page.goto(role==='vendor'?'/vendor/':'/');await page.getByLabel('電子郵件').fill(role+'@example.test');await page.getByLabel('密碼（至少12字元）').fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);
 return {get updates(){return updates;}};
}
for(const source of ['foodsave','seven-eleven','familymart'])test(`${source} information card has no reservation or fulfillment button`,async({page})=>{
 await setup(page,{source,count:null});await expect(page.getByRole('heading',{name:'資訊餐盒'})).toBeVisible();await expect(page.getByText(/數量待確認/)).toBeVisible();await expect(page.getByText(/更新時間未知/)).toBeVisible();await expect(page.getByText('僅提供資訊，數量以現場為準')).toBeVisible();await expect(page.getByRole('button',{name:'預約1份'})).toHaveCount(0);await expect(page.getByRole('button',{name:'出示取貨碼'})).toHaveCount(0);
});
test('merchant information default needs no pickup UI and can choose reservation',async({page})=>{
 const state=await setup(page,{role:'vendor'});await expect(page.getByRole('button',{name:'掃碼取貨',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'快速上架',exact:true})).toBeVisible();await page.getByLabel('資訊店家 服務模式').selectOption('reservation');await expect(page.getByRole('button',{name:'掃碼取貨',exact:true})).toBeVisible();expect(state.updates).toBe(1);
});
test('pending orders block reservation to information until confirmed expired',async({page})=>{
 const state=await setup(page,{role:'vendor',mode:'reservation',pending:1});const select=page.getByLabel('資訊店家 服務模式');await expect(select.locator('option[value="information"]')).toHaveJSProperty('disabled',true);await expect(page.getByRole('button',{name:'管理未完成預約'})).toBeVisible();expect(state.updates).toBe(0);await page.getByRole('button',{name:'確認逾期並更新庫存'}).click();await expect(select.locator('option[value="information"]')).toHaveJSProperty('disabled',false);await select.selectOption('information');await expect(page.getByText('已改為僅提供資訊；歷史訂單保留')).toBeVisible();expect(state.updates).toBe(1);await expect(page.getByRole('button',{name:'掃碼取貨',exact:true})).toHaveCount(0);
});
