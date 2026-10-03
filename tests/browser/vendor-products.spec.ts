import {test,expect} from '@playwright/test';
test('merchant listing and editing → consumer reservation → merchant pickup',async({page})=>{
 await page.goto('/vendor/');await page.getByLabel('商品名稱',{exact:true}).fill('驗收手作便當');await page.getByLabel('原價（元）',{exact:true}).fill('100');await page.getByLabel('優惠價（元）',{exact:true}).fill('60');await page.getByLabel('可再預約數量',{exact:true}).fill('2');
 await page.getByRole('button',{name:'確認上架',exact:true}).click();await expect(page.getByRole('status')).toContainText('上架成功');
 await page.getByRole('link',{name:'探索地圖',exact:true}).click();const product=page.locator('.product').filter({has:page.getByRole('heading',{name:'驗收手作便當',exact:true})});await expect(product).toBeVisible();await expect(product.getByText('剩餘 2 份')).toBeVisible();await product.getByRole('button',{name:'預約 1 份'}).click();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'示範商家核銷',exact:true}).click();await page.getByRole('button',{name:'編輯 驗收手作便當',exact:true}).click();
 await page.getByLabel('優惠價（元）',{exact:true}).fill('120');await page.getByRole('button',{name:'儲存商品變更'}).click();await expect(page.getByRole('status')).toContainText('優惠價不可高於原價');
 await page.getByLabel('優惠價（元）',{exact:true}).fill('50');await page.getByLabel('可再預約數量',{exact:true}).fill('4');await page.getByRole('button',{name:'儲存商品變更'}).click();await expect(page.getByRole('status')).toContainText('商品已更新');
 await page.getByRole('button',{name:'編輯 驗收手作便當',exact:true}).click();await page.getByLabel('商品名稱',{exact:true}).fill('不應儲存');await page.getByRole('button',{name:'取消編輯'}).click();await expect(page.getByRole('button',{name:'編輯 驗收手作便當',exact:true})).toBeVisible();
 await page.reload();await expect(page.getByRole('button',{name:'編輯 驗收手作便當',exact:true})).toBeVisible();
 await page.getByLabel('輸入 6 位示範取貨碼').fill('100001');await page.getByRole('button',{name:'確認示範領取'}).click();await expect(page.getByRole('status')).toContainText('核銷成功');
 await page.getByRole('link',{name:'查看預約與領取紀錄'}).click();await expect(page.getByText('幸福飯糰・1 份・$60',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'探索地圖',exact:true}).click();const card=page.locator('.product').filter({has:page.getByRole('heading',{name:'驗收手作便當',exact:true})});await expect(card.getByText('剩餘 4 份')).toBeVisible();await expect(card.getByText('$50',{exact:true})).toBeVisible();
 await page.screenshot({path:'artifacts/qa-vendor-listing.png',fullPage:true});
});
