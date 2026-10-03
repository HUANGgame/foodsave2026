import {test,expect} from '@playwright/test';
const endpoint='https://stamp.family.com.tw/api/maps/MapProductInfo';
const data={code:1,data:[{oldPKey:'00123',name:'合成契約門市',address:'臺北測試地址',latitude:25.0375,longitude:121.5636,updateDate:'2026-10-03 19:10:01',info:[{categories:[{name:'餐盒',qty:999,products:[{code:'0001',name:'合成友善便當',qty:2},{code:'0002',name:'數量未知合成商品'}]}]}]}]};
test('guest sees source-only FamilyMart cards and map; no reservation/pickup or invented prices',async({page})=>{
 let calls=0;
 await page.route(endpoint,r=>{calls++;expect(r.request().headers().authorization).toBeUndefined();expect(r.request().postDataJSON()).toEqual({ProjectCode:'202106302',OldPKeys:[],PostInfo:'',Latitude:25.0375197,Longitude:121.5636704});return r.fulfill({json:data});});
 await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
 await page.goto('/convenience/');await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);expect(calls).toBe(0);
 await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'合成契約門市'})).toBeVisible();await expect(page.getByText('2份（來源回報）',{exact:true})).toBeVisible();await expect(page.getByText('數量未知',{exact:true})).toBeVisible();await expect(page.getByText(/^來源更新：/)).toContainText('19:10:01');
 await expect(page.getByText('折扣以門市結帳為準。')).toBeVisible();await expect(page.getByRole('button',{name:/預約|核銷|取貨/})).toHaveCount(0);await expect(page.locator('img')).toHaveCount(0);
 await page.getByRole('button',{name:'顯示公開區域地圖'}).click();await expect(page.getByLabel('附近店家地圖')).toBeVisible();await expect(page.locator('.store-marker')).toContainText('？');
 await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);await page.reload();await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);
 await expect(page.getByRole('link',{name:'前往 OPENPOINT 官方 App'})).toHaveAttribute('href','https://play.google.com/store/apps/details?id=tw.net.pic.m.openpoint');
 await expect(page.getByText(/尚未完成庫存整合/)).toBeVisible();await page.getByRole('link',{name:'返回自營店家與攤販'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
});
for(const status of [403,429])test(`source ${status} stays unknown and is not retried`,async({page})=>{
 let calls=0;await page.route(endpoint,r=>{calls++;return r.fulfill({status,json:{}});});
 await page.goto('/convenience/');await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByText('全家來源暫時無法取得，庫存未知；請稍後再試。')).toBeVisible();await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(calls).toBe(1);await expect(page.getByText('0份（來源回報）')).toHaveCount(0);
});
