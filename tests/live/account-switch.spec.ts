import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
async function login(page:Page,email:string){await page.getByLabel('電子郵件').fill(email);await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();}
for(const late of ['success','unauthorized','network'] as const)test(`account switch isolates late ${late} response and private caches`,async({page})=>{
 let current='customer',hold=false,held=false,release=()=>{};
 await page.clock.install();
 await page.route('https://api.foodsave.test/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/auth/login'){current=r.request().postDataJSON().email.startsWith('vendor')?'vendor':'customer';return r.fulfill({json:{access_token:current}});}
  const who=r.request().headers().authorization?.replace('Bearer ','')||current;
  if(path==='/me')return r.fulfill({json:{id:who,email:who+'@example.test',role:who==='vendor'?'vendor':'consumer',exp:0,spins:1,welcome_spin_awarded:true,welcome_spin_available:1}});
  if(path==='/reservations')return r.fulfill({json:who==='customer'?[{id:'old-order',state:'cancelled',quantity:1,snapshot:{name:'PRIVATE OLD ORDER',sale_price_minor:100},expires_at:'2026-10-05T00:00:00Z'}]:[]});
  if(path==='/favorites')return r.fulfill({json:who==='customer'?['old-vendor']:[]});
  if(path==='/stores')return r.fulfill({json:who==='customer'?[{id:'old-store',vendor_id:'old-vendor',name:'PRIVATE OLD FAVORITE',latitude:25,longitude:121,product_count:0,service_mode:'information'}]:[]});
  if(path==='/notifications'){
   if(hold&&who==='customer'){hold=false;held=true;await new Promise<void>(resolve=>release=resolve);if(late==='network')return r.abort();if(late==='unauthorized')return r.fulfill({status:401,json:{detail:'old account expired'}});return r.fulfill({json:[{id:'late',body:'PRIVATE LATE NOTICE',created_at:'2026-10-04T00:00:00Z'}]});}
   return r.fulfill({json:who==='customer'?[{id:'old',body:'PRIVATE OLD NOTICE',created_at:'2026-10-04T00:00:00Z',read_at:null}]:[]});
  }
  return r.fulfill({json:[]});
 });
 await page.goto('/profile/');await login(page,'customer@example.test');await expect(page.getByText('消費者・惜食用戶',{exact:true})).toBeVisible();
 await expect(page.getByText(/首次登入已贈1次歡迎機會/)).toBeVisible();
 await page.getByRole('link',{name:'我的預約',exact:true}).click();await expect(page.getByRole('heading',{name:'PRIVATE OLD ORDER'})).toBeVisible();
 await page.getByRole('link',{name:'我的收藏',exact:true}).click();await expect(page.getByRole('heading',{name:'PRIVATE OLD FAVORITE'})).toBeVisible();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:/通知中心/}).click();await expect(page.getByText('PRIVATE OLD NOTICE')).toBeVisible();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();hold=true;await page.clock.fastForward(30000);await expect.poll(()=>held).toBe(true);
 await page.getByRole('button',{name:'切換帳號',exact:true}).click();await expect(page.getByRole('heading',{name:'歡迎回來'})).toBeVisible();
 await login(page,'vendor@example.test');await expect(page.getByText('商家・合作店家',{exact:true})).toBeVisible();release();await page.waitForTimeout(100);
 await expect(page.getByText('商家・合作店家',{exact:true})).toBeVisible();await expect(page.getByText(/old account expired|連線未完成/)).toHaveCount(0);
 await page.getByRole('link',{name:/通知中心/}).click();await expect(page.getByText('目前沒有通知。')).toBeVisible();await expect(page.getByText('PRIVATE OLD NOTICE')).toHaveCount(0);await expect(page.getByText('PRIVATE LATE NOTICE')).toHaveCount(0);
 await page.getByRole('link',{name:'我的收藏',exact:true}).click();await expect(page.getByRole('heading',{name:'PRIVATE OLD FAVORITE'})).toHaveCount(0);await page.evaluate(()=>{history.pushState(null,'','/reservations/');window.dispatchEvent(new PopStateEvent('popstate'));});await expect(page.getByText('目前沒有預約。')).toBeVisible();await expect(page.getByText('PRIVATE OLD ORDER')).toHaveCount(0);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'切換帳號',exact:true}).click();await expect(page.getByRole('heading',{name:'歡迎回來'})).toBeVisible();
 const storage=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));expect(storage).not.toContain('example.test');expect(storage).not.toContain('PRIVATE OLD NOTICE');
});
