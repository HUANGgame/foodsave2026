import {test,expect} from '@playwright/test';
const endpoint='https://stamp.family.com.tw/api/maps/MapProductInfo';
const data={code:1,data:[{oldPKey:'00123',name:'合成契約門市',address:'臺北測試地址',latitude:25.0375,longitude:121.5636,updateDate:'2026-10-03 19:10:01',info:[{categories:[{name:'餐盒',qty:999,products:[{code:'0001',name:'合成友善便當',qty:2},{code:'0002',name:'數量未知合成商品'}]}]}]}]};
test('guest sees source-only FamilyMart cards and map; no reservation/pickup or invented prices',async({page})=>{
 let calls=0;
 await page.route(endpoint,r=>{calls++;expect(r.request().headers().authorization).toBeUndefined();expect(r.request().postDataJSON()).toEqual({ProjectCode:'202106302',OldPKeys:[],PostInfo:'',Latitude:25.0375197,Longitude:121.5636704});return r.fulfill({json:data});});
 await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
 await page.goto('/convenience/');await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);expect(calls).toBe(0);
 await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'合成契約門市'})).toBeVisible();await expect(page.getByText('2份（來源回報）',{exact:true})).toBeVisible();await expect(page.locator('.product').first()).toContainText('友善食光・折扣商品');await expect(page.locator('.product').first()).toContainText('折扣與售價依門市結帳為準');await expect(page.getByText('數量未知',{exact:true})).toBeVisible();await expect(page.getByText(/^來源更新：/)).toContainText('19:10:01');
 await expect(page.getByText(/是否適用及金額以門市收銀機判讀為準/)).toBeVisible();await expect(page.getByRole('button',{name:/預約|核銷|取貨/})).toHaveCount(0);await expect(page.locator('img')).toHaveCount(0);
 await page.getByRole('button',{name:'顯示公開區域地圖'}).click();await expect(page.getByLabel('附近店家地圖')).toBeVisible();await expect(page.locator('.store-marker')).toContainText('？');await page.screenshot({path:'artifacts/role-customer-family-unknown.png',fullPage:true});
 await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);await page.reload();await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);
 await expect(page.getByRole('link',{name:'前往 OPENPOINT 官方 App'})).toHaveAttribute('href','https://play.google.com/store/apps/details?id=tw.net.pic.m.openpoint');
 await expect(page.getByText(/尚未完成庫存整合/)).toBeVisible();await page.getByRole('link',{name:'返回自營店家與攤販'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
});
for(const status of [403,429])test(`source ${status} stays unknown and is not retried`,async({page})=>{
 let calls=0;await page.route(endpoint,r=>{calls++;return r.fulfill({status,json:{}});});
 await page.goto('/convenience/');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByText('全家來源暫時無法取得，庫存未知；請稍後再試。')).toBeVisible();await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);await expect(page.getByText('0份（來源回報）')).toHaveCount(0);
});
test('changing public area ignores delayed old response and keeps separate cache',async({page})=>{
 let release:()=>void=()=>{};const held=new Promise<void>(r=>{release=r;});let calls=0;
 await page.route(endpoint,async r=>{calls++;const latitude=r.request().postDataJSON().Latitude;if(latitude===25.0375197)await held;await r.fulfill({json:{code:1,data:[{...data.data[0],name:latitude===25.0375197?'舊區門市':'新區門市'}]}});});
 await page.goto('/convenience/');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect.poll(()=>calls).toBe(1);
 await page.getByLabel('手動選擇公開地區').selectOption('kaohsiung-lingya-v1');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'新區門市'})).toBeVisible();release();await expect(page.getByRole('heading',{name:'舊區門市'})).toHaveCount(0);
 await page.getByLabel('手動選擇公開地區').selectOption('taipei-xinyi-public-v1');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'舊區門市'})).toBeVisible();expect(calls).toBe(2);
});
test('nearby requires separate consent and keeps GPS/cache out of storage',async({page})=>{
 await page.addInitScript(()=>{(window as any).__locationCalls=0;Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(resolve:any)=>{(window as any).__locationCalls++;resolve({coords:{latitude:24.123456,longitude:120.654321}});}}});});
 let calls=0;await page.route(endpoint,r=>{calls++;expect(r.request().postDataJSON().Latitude).toBe(24.123456);expect(r.request().headers().authorization).toBeUndefined();return r.fulfill({json:data});});
 await page.goto('/convenience/');await page.getByRole('button',{name:'查詢我的附近'}).click();await expect(page.getByRole('dialog')).toContainText('stamp.family.com.tw');expect(await page.evaluate(()=>(window as any).__locationCalls)).toBe(0);await page.getByRole('button',{name:'取消',exact:true}).click();expect(calls).toBe(0);
 await page.getByRole('button',{name:'查詢我的附近'}).click();await page.getByRole('button',{name:'同意傳送位置並查詢'}).click();await expect(page.getByRole('heading',{name:'合成契約門市'})).toBeVisible();expect(calls).toBe(1);expect(await page.evaluate(()=>JSON.stringify(localStorage))).not.toContain('24.123456');expect(await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.includes('familymart')))).toEqual([]);
 await page.reload();await expect(page.getByText('查詢區域：臺北市信義區（公開測試區域）')).toBeVisible();expect(calls).toBe(1);
});
for(const code of [1,2])test(`location failure ${code} sends nothing and manual selection remains usable`,async({page})=>{
 await page.addInitScript(code=>{Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(_:any,reject:any)=>reject({code})}});},code);
 let calls=0;await page.route(endpoint,r=>{calls++;return r.fulfill({json:data});});await page.goto('/convenience/');await page.getByRole('button',{name:'查詢我的附近'}).click();await page.getByRole('button',{name:'同意傳送位置並查詢'}).click();await expect(page.getByText(/未傳送座標/)).toBeVisible();expect(calls).toBe(0);await page.getByLabel('手動選擇公開地區').selectOption('taichung-west-v1');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'合成契約門市'})).toBeVisible();expect(calls).toBe(1);
});
test('cancel while location is pending never sends its eventual coordinates',async({page})=>{
 await page.addInitScript(()=>{Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(resolve:any)=>{(window as any).__resolveLocation=resolve;}}});});let calls=0;await page.route(endpoint,r=>{calls++;return r.fulfill({json:data});});
 await page.goto('/convenience/');await page.getByRole('button',{name:'查詢我的附近'}).click();await page.getByRole('button',{name:'同意傳送位置並查詢'}).click();await page.getByRole('button',{name:'取消定位',exact:true}).click();await page.evaluate(()=>(window as any).__resolveLocation({coords:{latitude:24.123456,longitude:120.654321}}));await expect(page.getByText('已取消定位，不會傳送這次取得的座標。')).toBeVisible();expect(calls).toBe(0);
});
