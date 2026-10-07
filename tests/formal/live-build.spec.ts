import {test,expect} from '@playwright/test';
const API='https://foodsave-web-tku-aqhxdnhpe8fdhfee.eastasia-01.azurewebsites.net';
test('formal-URL artifact retains live login and same-account merchant flow; all remote traffic intercepted',async({page})=>{
 const paths:string[]=[],errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{
  const u=new URL(r.request().url());if(u.origin==='http://127.0.0.1:4176')return r.continue();
  if(u.origin!==API)return r.abort(); // No external service is contacted.
  paths.push(u.pathname);
  if(u.pathname==='/auth/login')return r.fulfill({json:{access_token:'synthetic-formal-build-test'}});
  if(u.pathname==='/me')return r.fulfill({json:{id:'owner',email:'owner@example.invalid',role:'consumer',is_vendor:false,exp:0,spins:0}});
  return r.fulfill({json:[]});
 });
 await page.goto('/profile/');await expect(page.getByRole('heading',{name:'歡迎回來'})).toBeVisible();
 await page.getByLabel('電子郵件').fill('owner@example.invalid');await page.getByLabel('密碼',{exact:true}).fill('synthetic-password-123');await page.getByRole('button',{name:'登入',exact:true}).click();
 await expect(page.getByText('owner@example.invalid',{exact:true})).toBeVisible();await page.getByRole('link',{name:'我要上架'}).click();await expect(page.getByRole('heading',{name:'建立我的店家'})).toBeVisible();
 expect(paths).toContain('/auth/login');expect(paths).toContain('/me');expect(paths).not.toContain('/auth/logout');expect(paths).not.toContain('/auth/register');expect(errors).toEqual([]);
});


test('approved policy shows persisted location disclosures and version',async({page})=>{
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('/privacy/');
 await expect(page.getByText('政策版本：foodsave-test-20261007-v2')).toBeVisible();
 await expect(page.getByText(/FoodSave 附近查詢會將本次查詢座標送至 FoodSave 後端/)).toBeVisible();
 await expect(page.getByText(/取貨地點快照/)).toBeVisible();
 await expect(page.getByText(/關閉或重新載入 App 而清除/)).toBeVisible();
 await expect(page.getByText(/限時授權/)).toHaveCount(0);
});
