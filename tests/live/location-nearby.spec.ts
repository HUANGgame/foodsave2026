import {test,expect,Page} from '@playwright/test';
async function login(page:Page){await page.getByLabel('電子郵件').fill('owner@example.test');await page.getByLabel('密碼',{exact:true}).fill('synthetic-password-123');await page.getByRole('button',{name:'登入',exact:true}).click();}
async function merchant(page:Page,{blocked=false,conflict=false,lost=false}={}){
 let revision=2,puts:any[]=[],keys:string[]=[];
 await page.route('**/*.tile.openstreetmap.org/**',r=>r.abort());
 await page.addInitScript(()=>{navigator.geolocation.getCurrentPosition=(ok)=>ok({coords:{latitude:25.012,longitude:121.012}} as GeolocationPosition);});
 await page.route('https://api.foodsave.test/**',r=>{
  const request=r.request(),path=new URL(request.url()).pathname;
  const json=(v:unknown,status=200)=>r.fulfill({json:v,status});
  if(path==='/auth/login')return json({access_token:'synthetic'});
  if(path==='/me')return json({id:'owner',email:'owner@example.test',role:'consumer',is_vendor:true,exp:0,spins:0});
  if(path==='/vendor/catalog')return json({stores:[{id:'mine',name:'我的店',service_mode:'information',location_confirmed:true}],products:[]});
  if(path==='/vendor/stores/mine/location'){
   if(request.method()==='PUT'){puts.push(request.postDataJSON());keys.push(request.headers()['idempotency-key']);if(lost&&puts.length===1)return r.abort();if(conflict&&puts.length===1){revision++;return json({detail:'店址已更新，請重新載入'},409);}return json({id:'mine',location_revision:++revision});}
   return json({id:'mine',latitude:25,longitude:121,location_revision:revision,location_confirmed:true,pending_orders:blocked?1:0,can_move:!blocked});
  }
  return json([]);
 });
 await page.goto('/profile/');await login(page);await page.getByRole('link',{name:'我要上架'}).click();await page.getByRole('button',{name:'調整店址',exact:true}).click();await expect(page.getByRole('button',{name:'確認保存店址'})).toBeEnabled({timeout:blocked?1:5000}).catch(e=>{if(!blocked)throw e;});
 return {puts,keys};
}
test('location stays draft until explicit confirmation; map drag and GPS update submitted revision',async({page})=>{
 const state=await merchant(page);await page.getByRole('button',{name:'使用目前位置'}).click();await expect(page.locator('.location-pin')).toBeVisible();
 const pin=await page.locator('.location-pin').boundingBox();await page.mouse.move(pin!.x+22,pin!.y+22);await page.mouse.down();await page.mouse.move(pin!.x+62,pin!.y+35,{steps:5});await page.mouse.up();
 expect(state.puts).toHaveLength(0);await page.getByRole('button',{name:'確認保存店址'}).dblclick();await expect.poll(()=>state.puts.length).toBe(1);expect(state.puts[0]).toMatchObject({expected_revision:2,confirm:'SAVE_LOCATION'});expect(state.puts[0].longitude).not.toBe(121.012);await expect(page.getByRole('heading',{name:'商家工作台'})).toBeVisible();
});
test('pending orders block location save',async({page})=>{
 const state=await merchant(page,{blocked:true});await expect(page.getByRole('alert').filter({hasText:'暫時不能移動'})).toContainText('暫時不能移動');await expect(page.getByRole('button',{name:'確認保存店址'})).toBeDisabled();expect(state.puts).toHaveLength(0);await page.getByRole('button',{name:'返回工作台'}).click();await expect(page.getByRole('heading',{name:'商家工作台'})).toBeVisible();
});
test('revision conflict requires reload before saving again',async({page})=>{
 const state=await merchant(page,{conflict:true});await page.getByRole('button',{name:'確認保存店址'}).click();await expect(page.getByRole('button',{name:'確認保存店址'})).toBeDisabled();await page.getByRole('button',{name:'重新載入店址'}).click();await expect(page.getByRole('button',{name:'確認保存店址'})).toBeEnabled();await page.getByRole('button',{name:'確認保存店址'}).click();await expect.poll(()=>state.puts.length).toBe(2);expect(state.puts[1].expected_revision).toBe(3);
});
test('lost location reply retries original body and key after closing editor',async({page})=>{
 const state=await merchant(page,{lost:true});await page.getByRole('button',{name:'使用目前位置'}).click();await page.getByRole('button',{name:'確認保存店址'}).click();await expect(page.getByRole('button',{name:'重試保存店址'})).toBeEnabled();await page.getByRole('button',{name:'返回工作台'}).click();await page.getByRole('button',{name:'調整店址',exact:true}).click();await page.getByRole('button',{name:'重試保存店址'}).click();await expect.poll(()=>state.puts.length).toBe(2);expect(state.puts[1]).toEqual(state.puts[0]);expect(state.keys[1]).toBe(state.keys[0]);
});
test('nearby reads every page, disables own item, refreshes at 30 seconds and uses historical snapshot',async({page,context})=>{
 await context.grantPermissions(['geolocation']);await context.setGeolocation({latitude:25,longitude:121});await page.clock.install();let reads=0;
 await page.route('**/*.tile.openstreetmap.org/**',r=>r.abort());await page.route('https://stamp.family.com.tw/**',r=>r.fulfill({json:{code:1,data:[]}}));
 await page.route('https://api.foodsave.test/**',r=>{
  const u=new URL(r.request().url()),path=u.pathname;const json=(v:unknown)=>r.fulfill({json:v});
  if(path==='/auth/login')return json({access_token:'synthetic'});
  if(path==='/me')return json({id:'owner',email:'owner@example.test',role:'consumer',is_vendor:true,exp:0,spins:0});
  if(path==='/reservations')return json([{id:'historical',state:'completed',quantity:1,snapshot:{name:'歷史商品',sale_price_minor:100,latitude:24.5,longitude:120.5},expires_at:'2026-01-01T00:00:00Z'}]);
  if(path.startsWith('/nearby/')){reads++;const offset=Number(u.searchParams.get('cursor')||0);const items=path.endsWith('/stores')?[{id:'mine',vendor_id:'owner',name:'自己的店',latitude:25,longitude:121,product_count:201,service_mode:'reservation'}]:Array.from({length:offset===200?1:100},(_,i)=>({id:String(offset+i),store_id:'mine',vendor_id:'owner',name:'商品'+(offset+i),available_quantity:1,sale_price_minor:100,original_price_minor:200,source:'foodsave',service_mode:'reservation',pickup_deadline:'2030-01-01T00:00:00Z'}));return json({items,radius_m:1000,next_cursor:path.endsWith('/stores')||offset===200?null:String(offset+100)});}
  return json([]);
 });
 await page.goto('/');await page.getByRole('button',{name:'同意並探索附近'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeEnabled();await login(page);await expect(page.getByRole('heading',{name:'商品200',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'自己的商品'})).toHaveCount(201);await expect(page.getByRole('button',{name:'自己的商品'}).last()).toBeDisabled();const before=reads;await page.clock.fastForward(30000);await expect.poll(()=>reads).toBeGreaterThan(before);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();await expect(page.getByRole('link',{name:'訂單取貨點導航'})).toHaveAttribute('href',/destination=24.5,120.5/);
});

test('reload after unknown location result reconciles before a new revision save',async({page})=>{
 const state=await merchant(page,{lost:true});await page.getByRole('button',{name:'確認保存店址'}).click();await expect(page.getByRole('button',{name:'重試保存店址'})).toBeEnabled();
 await page.reload();await login(page);await page.getByRole('button',{name:'調整店址',exact:true}).click();await expect(page.getByRole('button',{name:'確認保存店址'})).toBeDisabled();await page.getByRole('button',{name:'核對店址後重新編輯'}).click();await expect(page.getByRole('button',{name:'確認保存店址'})).toBeEnabled();await page.getByRole('button',{name:'確認保存店址'}).click();await expect.poll(()=>state.puts.length).toBe(2);expect(state.puts[1].expected_revision).toBe(2);expect(state.keys[1]).not.toBe(state.keys[0]);
});

test('a 45 second page chain survives the 30 second foreground timer',async({page,context})=>{
 await context.grantPermissions(['geolocation']);await context.setGeolocation({latitude:25,longitude:121});await page.clock.install();let starts=0,slow=false;const releases=new Map<number,()=>void>();
 await page.route('**/*.tile.openstreetmap.org/**',r=>r.abort());await page.route('https://stamp.family.com.tw/**',r=>r.fulfill({json:{code:1,data:[]}}));
 await page.route('https://api.foodsave.test/**',async r=>{
  const u=new URL(r.request().url()),path=u.pathname;const json=(v:unknown)=>r.fulfill({json:v});
  if(path==='/auth/login')return json({access_token:'synthetic'});if(path==='/me')return json({id:'owner',email:'owner@example.test',role:'consumer',exp:0,spins:0});
  if(path==='/nearby/stores')return json({items:[{id:'store',vendor_id:'other',name:'慢速店',latitude:25,longitude:121,product_count:3,service_mode:'information'}],radius_m:1000,next_cursor:null});
  if(path==='/nearby/products'){const offset=Number(u.searchParams.get('cursor')||0);if(offset===0)starts++;if(slow)await new Promise<void>(resolve=>releases.set(offset,resolve));return json({items:[{id:String(offset),store_id:'store',name:'慢速商品'+offset,available_quantity:1,sale_price_minor:100,original_price_minor:200,service_mode:'information',pickup_deadline:'2030-01-01T00:00:00Z'}],radius_m:1000,next_cursor:offset<2?String(offset+1):null});}
  return json([]);
 });
 await page.goto('/');await page.getByRole('button',{name:'同意並探索附近'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeEnabled();await login(page);
 await expect(page.getByRole('heading',{name:'慢速商品2',exact:true})).toBeVisible();slow=true;await page.clock.fastForward(30000);
 for(let i=0;i<3;i++){await expect.poll(()=>releases.has(i)).toBe(true);await page.clock.fastForward(15000);releases.get(i)!();}
 await expect(page.getByRole('heading',{name:'慢速商品2',exact:true})).toBeVisible();expect(starts).toBe(2);
});
