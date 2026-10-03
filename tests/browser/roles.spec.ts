import {test,expect} from '@playwright/test';

test('consumer: double tap, cancellation, back navigation, expiry and restart',async({page})=>{
 await page.clock.install();await page.goto('/');
 await page.getByRole('button',{name:'預約 1 份',exact:true}).first().click({clickCount:2});
 expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('foodsave-demo-v1')!).reservations.length)).toBe(1);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約'}).click();await expect(page.getByRole('heading',{name:'我的預約',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'取消預約',exact:true}).click();await expect(page.getByText('已取消',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'探索地圖',exact:true}).click();await expect(page.getByText('剩餘 4 份',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'預約 1 份',exact:true}).first().click();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約'}).click();await expect(page.getByRole('heading',{name:'我的預約',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'示範商家核銷',exact:true}).click();await expect(page.getByLabel('輸入 6 位示範取貨碼')).toBeVisible();await page.goBack();await expect(page.getByText('100002',{exact:true})).toBeVisible();
 await page.clock.fastForward(31*60*1000);await expect(page.getByText('已逾時',{exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText('已逾時',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('foodsave-demo-v1')!).exp.length)).toBe(0);
 await page.screenshot({path:'artifacts/qa-consumer.png',fullPage:true});
});

test('vendor demo: invalid code, completion once, stock consistency and persistence',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'預約 1 份',exact:true}).first().click();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'示範商家核銷',exact:true}).click();
 await page.getByLabel('輸入 6 位示範取貨碼').fill('999999');await page.getByRole('button',{name:'確認示範領取'}).click();await expect(page.getByRole('status')).toContainText('找不到');
 await page.getByLabel('輸入 6 位示範取貨碼').fill('100001');await page.getByRole('button',{name:'確認示範領取'}).click();await expect(page.getByRole('status')).toContainText('核銷成功');
 await page.getByLabel('輸入 6 位示範取貨碼').fill('100001');await page.getByRole('button',{name:'確認示範領取'}).click();await expect(page.getByRole('status')).toContainText('找不到');
 await page.getByRole('link',{name:'查看預約與領取紀錄'}).click();await expect(page.getByText('已完成',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'取消預約'})).toHaveCount(0);
 await page.getByRole('link',{name:'探索地圖',exact:true}).click();await expect(page.getByText('剩餘 3 份',{exact:true})).toBeVisible();
 await page.reload();expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('foodsave-demo-v1')!).exp.reduce((n:number,e:{amount:number})=>n+e.amount,0))).toBe(100);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'示範商家核銷',exact:true}).click();await page.screenshot({path:'artifacts/qa-vendor.png',fullPage:true});
});

test('product owner: intro, feedback animation, reduced motion, small screen and honest feature boundaries',async({page})=>{
 await page.setViewportSize({width:360,height:800});await page.goto('/');
 await page.getByRole('button',{name:'第一次使用？看 3 個小步驟'}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.screenshot({path:'artifacts/qa-introduction.png',fullPage:true,animations:'disabled'});await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).not.toBeVisible();
 const favorite=page.getByRole('button',{name:'收藏店家',exact:true});await favorite.scrollIntoViewIfNeeded();await favorite.click();await expect(page.getByRole('button',{name:'已收藏',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('status')).toHaveCSS('animation-name','toast-in');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 const target=page.getByRole('button',{name:'預約 1 份',exact:true}).first();expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
 await page.emulateMedia({reducedMotion:'reduce'});await expect(page.locator('.welcome-leaf')).toHaveCSS('animation-name','none');
 await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.getByRole('button',{name:'尚未開放抽獎'})).toBeDisabled();await expect(page.getByText('本版不發放真實優惠券或抽獎結果。')).toBeVisible();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await expect(page.getByText('正式登入、資料庫、即時庫存及管理後台尚未串接。')).toBeVisible();
 await page.screenshot({path:'artifacts/qa-product-owner.png',fullPage:true});
});
