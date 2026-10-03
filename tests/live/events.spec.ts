import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
async function setup(page:Page,role='consumer'){
 let favorite=true,account='first',revision=1,puts=0,created:any=null,loss:any=null,read=false;const paths:string[]=[];
 const product=()=>({id:'p',store_id:'s',name:'原批餐盒',photo_url:'https://images.example.test/a.png',original_price_minor:10000,sale_price_minor:5000,available_quantity:3,pickup_deadline:'2027-01-01T12:00:00',revision,active:true});
 await page.route('https://api.foodsave.test/**',async r=>{const req=r.request(),path=new URL(req.url()).pathname;paths.push(path);const json=(body:unknown,status=200)=>r.fulfill({json:body,status});
  if(req.method()==='OPTIONS')return r.fulfill({status:204});
  if(path==='/auth/login'){account=req.postDataJSON().email.startsWith('second')?'second':'first';return json({access_token:randomUUID()});}
  if(path==='/auth/logout')return r.abort('failed');
  if(path==='/me')return json({id:account,email:account+'@example.test',role,exp:0,spins:0});
  if(path==='/products')return json([]);
  if(path==='/stores')return json([{id:'s',vendor_id:'v',name:'無商品店家',latitude:25,longitude:121,product_count:0,service_mode:'reservation'}]);
  if(path==='/favorites')return json(favorite&&account==='first'?['v']:[]);
  if(path==='/favorites/v'){favorite=req.postDataJSON().enabled;return json({vendor_id:'v',enabled:favorite});}
  if(path==='/notifications')return json(account==='first'?[{id:'n',kind:'vendor_out_of_stock',body:'缺貨測試通知：請勿再前往取貨。',created_at:'2026-10-03T08:00:00',read_at:read?'2026-10-03T09:00:00':null}]:[]);
  if(path==='/notifications/n/read'){read=true;return json({read:true});}
  if(path==='/vendor/catalog')return json({stores:[{id:'s',name:'無商品店家',service_mode:'reservation',pending_orders:2}],products:[product()]});
  if(path==='/vendor/products/p'&&req.method()==='PUT'){puts++;revision=2;return json({detail:'資料已變更，請重新載入'},409);}
  if(path==='/vendor/products'){created=req.postDataJSON();return json({id:'new-p',revision:1},201);}
  if(path==='/vendor/products/p/stock-loss-preview')return json({id:'p',name:'原批餐盒',revision,pending_count:2,available_quantity:3});
  if(path==='/vendor/products/p/stock-loss'){loss=req.postDataJSON();return json({cancelled_count:2});}
  if(path.startsWith('/stores/'))return json({average:null,count:0,items:[]});
  return json([]);
 });
 await page.route('https://images.example.test/**',r=>r.abort());
 return {paths,get created(){return created;},get loss(){return loss;},get puts(){return puts;}};
}
async function login(page:Page,email='first@example.test'){await page.getByLabel('電子郵件').fill(email);await page.getByLabel('密碼（至少12字元）').fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);}

test('favorites use vendor account and keep a store with zero products',async({page})=>{
 const state=await setup(page);await page.goto('/favorites/');await login(page);await expect(page.getByRole('heading',{name:'無商品店家'})).toBeVisible();await expect(page.getByText('目前沒有可供應的商品，仍可收藏店家並稍後查看。')).toBeVisible();await page.getByRole('button',{name:'取消收藏',exact:true}).click();await expect(page.getByRole('heading',{name:'這裡還沒有可用的好店'})).toBeVisible();expect(state.paths).toContain('/favorites/v');expect(state.paths).not.toContain('/favorites/s');
});
test('inbox read and offline account switching never expose first account notices',async({page})=>{
 await setup(page);await page.goto('/profile/');await login(page);await page.getByRole('link',{name:'通知中心（1則未讀）'}).click();await expect(page.getByText('缺貨測試通知：請勿再前往取貨。')).toBeVisible();await page.getByRole('button',{name:'標示已讀'}).click();await expect(page.getByText('已讀',{exact:true})).toBeVisible();await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'切換帳號',exact:true}).click();await expect(page.getByText(/已清除本機登入/)).toBeVisible();await login(page,'second@example.test');await page.getByRole('link',{name:'通知中心（0則未讀）'}).click();await expect(page.getByText('目前沒有通知。')).toBeVisible();await expect(page.getByText('缺貨測試通知：請勿再前往取貨。')).toHaveCount(0);
});
test('revision conflict preserves input; explicit reload; new batch POST and stock loss confirmation',async({page})=>{
 const state=await setup(page,'vendor');await page.goto('/vendor/');await login(page);await page.getByRole('button',{name:'沿用商品／調價期限'}).click();await page.getByLabel('惜食價（元）').fill('42');await page.getByRole('button',{name:'儲存商品',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'伺服器資料已變更'})).toContainText('尚未儲存的輸入仍保留');await expect(page.getByLabel('惜食價（元）')).toHaveValue('42');expect(state.puts).toBe(1);await page.getByRole('button',{name:'丟棄輸入並載入最新版'}).click();await expect(page.getByLabel('惜食價（元）')).toHaveValue('50');await page.getByRole('button',{name:'複製為新批次',exact:true}).click();await expect(page.getByLabel('領取截止')).toHaveValue('');await page.getByLabel('剩餘數量').fill('5');await page.getByLabel('領取截止').fill('2027-01-02T12:00');await page.getByRole('button',{name:'儲存商品',exact:true}).click();await expect(page.getByText('商品已儲存')).toBeVisible();expect(state.created).toMatchObject({revision:1,available_quantity:5,name:'原批餐盒'});expect(state.puts).toBe(1);
 await page.getByRole('button',{name:'實際缺貨，無法履約',exact:true}).click();await expect(page.getByText(/將取消並移除 2 筆待領預約/)).toBeVisible();expect(state.loss).toBeNull();await page.getByRole('checkbox',{name:'我確認上述預約均無法履約'}).check();await page.getByRole('button',{name:'確認缺貨並通知顧客'}).click();await expect(page.getByText(/已移除 2 筆無法履約/)).toBeVisible();expect(state.loss).toEqual({expected_revision:2,expected_pending:2,actual_available:0,confirm:'CANCEL_AFFECTED'});
});
