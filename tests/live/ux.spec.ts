import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
async function fixture(page:Page){
 let reads=0,family=0;const id=randomUUID();
 await page.route('https://api.foodsave.test/**',r=>{const path=new URL(r.request().url()).pathname;
  if(path.startsWith('/nearby/'))return r.fulfill({json:{items:[],radius_m:1000,next_cursor:null}});
  if(path==='/auth/login')return r.fulfill({json:{access_token:randomUUID()}});
  if(path==='/me'){reads++;return r.fulfill({json:{id,email:'fixture@example.test',role:'consumer',exp:0,spins:0}});}
  return r.fulfill({json:[]});
 });
 await page.route('https://stamp.family.com.tw/**',r=>{family++;expect(r.request().headers().authorization).toBeUndefined();return r.fulfill({json:{code:1,data:[]}});});
 await page.route('**/*.tile.openstreetmap.org/**',r=>r.abort());
 return {get reads(){return reads;},get family(){return family;}};
}
async function login(page:Page){await page.getByLabel('電子郵件').fill('fixture@example.test');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);}
test('tabs preserve live session and do not refetch the entire account on every navigation',async({page})=>{
 const mock=await fixture(page);await page.goto('/');await page.getByRole('button',{name:'先手動選地區'}).click();const recovery=await page.getByRole('button',{name:'忘記密碼'}).boundingBox(),register=await page.getByRole('button',{name:'第一次使用？建立帳號'}).boundingBox();expect(register!.y-(recovery!.y+recovery!.height)).toBeGreaterThan(32);const inputBox=await page.getByLabel('密碼',{exact:true}).boundingBox(),toggleBox=await page.getByRole('button',{name:'顯示輸入內容'}).boundingBox();expect(Math.abs(inputBox!.y+inputBox!.height-toggleBox!.y-toggleBox!.height)).toBeLessThan(2);await page.screenshot({path:'artifacts/role-customer-login.png',fullPage:true});await login(page);const reads=mock.reads;await expect(page.getByText('尚未定位',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await expect(page.getByText('消費者・惜食用戶',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'我的收藏',exact:true}).click();await page.getByRole('link',{name:'探索地圖',exact:true}).click();
 expect(mock.reads).toBe(reads);expect(mock.family).toBe(0);await expect(page.getByText('尚未定位',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'附近的好食物',exact:true})).toBeVisible();await page.evaluate(()=>window.scrollTo(0,300));await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(300);await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'探索地圖',exact:true}).click();await expect(page.getByRole('heading',{name:'附近的好食物',exact:true})).toBeVisible();await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(300);await page.screenshot({path:'artifacts/role-customer-restored.png',fullPage:true});await expect(page.getByText('正在確認資料…',{exact:true})).toHaveCount(0);
 await expect(page.locator('nav[aria-label="主要導覽"] a')).toHaveCount(4);
});
test('consented location automatically queries FamilyMart once and does not persist coordinates',async({page,context})=>{
 await context.grantPermissions(['geolocation']);await context.setGeolocation({latitude:25.01357,longitude:121.43219});const mock=await fixture(page);await page.goto('/');expect(mock.family).toBe(0);
 await page.getByRole('button',{name:'同意並探索附近'}).click();await login(page);await expect.poll(()=>mock.family).toBe(1);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'探索地圖',exact:true}).click();expect(mock.family).toBe(1);
 const saved=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));expect(saved).not.toContain('25.01357');expect(saved).not.toContain('121.43219');
});
test('password visibility and Unicode limits do not lower new-password policy',async({page})=>{
 await page.route('https://api.foodsave.test/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/auth/options'?{registration_enabled:true,recovery_enabled:true}:{detail:'請查看信件'}}));
 await page.goto('/profile/');await page.getByRole('button',{name:'第一次使用？建立帳號'}).click();await page.getByLabel('電子郵件').fill('fixture@example.test');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'寄送驗證碼'}).click();
 const password=page.getByLabel('新密碼（至少15字元）',{exact:true});await password.fill('🍀'.repeat(14));expect(await password.evaluate((e:HTMLInputElement)=>e.validity.valid)).toBe(false);
 await password.fill('🍀'.repeat(128));expect(await password.evaluate((e:HTMLInputElement)=>e.validity.valid)).toBe(true);
 await page.getByRole('button',{name:'顯示輸入內容',exact:true}).first().click();await expect(password).toHaveAttribute('type','text');await expect(password).toHaveAttribute('autocomplete','new-password');
 const storage=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));expect(storage).not.toContain('🍀');
});
