import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
const snapshot=(revision:number)=>({enabled:true,demonstration:true,notice:'示範，暫不可兌換',revision,prizes:Array.from({length:6},(_,i)=>({id:`demo-${i+1}`,name:`v${revision}獎品${i+1}`,icon:'leaf',terms:'示範，暫不可兌換'}))});
async function setup(page:Page){
 let revision=1,reads=0,posts=0,hold=false,fail=false;let release=()=>{};
 await page.clock.install();await page.emulateMedia({reducedMotion:'reduce'});
 await page.route('https://api.foodsave.test/**',async r=>{const path=new URL(r.request().url()).pathname;
  if(path==='/demo-prizes'){reads++;const pool=snapshot(revision);if(hold){hold=false;await new Promise<void>(resolve=>{release=resolve;});}if(fail){fail=false;return r.fulfill({status:503,json:{detail:'Synthetic unavailable'}});}return r.fulfill({json:pool});}
  if(path==='/demo-draws'){posts++;const pool=snapshot(revision);if(r.request().postDataJSON().revision!==revision)return r.fulfill({status:409,json:{...pool,code:'pool_changed',detail:'獎池已更新'}});return r.fulfill({json:{...pool,prize:pool.prizes[0],redeemable:false,consumes_real_spin:false}});}
  if(path==='/auth/login')return r.fulfill({json:{access_token:randomUUID()}});
  if(path==='/me')return r.fulfill({json:{id:'synthetic-consumer',email:'fixture@example.invalid',role:'consumer',spins:0,exp:0}});
  return r.fulfill({json:[]});
 });
 await page.goto('/missions/');await page.getByLabel('電子郵件').fill('fixture@example.invalid');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.locator('.demo-wheel .wheel-label')).toHaveCount(6);
 return {get reads(){return reads;},get posts(){return posts;},version:(n:number)=>{revision=n;},hold:()=>{hold=true;},fail:()=>{fail=true;},release:()=>release()};
}
async function visibility(page:Page,state:'visible'|'hidden'){await page.evaluate(state=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:state});document.dispatchEvent(new Event('visibilitychange'));},state);}
test('visible 30s poll, background pause, foreground refresh and late responses cannot roll version back',async({page})=>{
 const state=await setup(page);state.version(2);state.hold();await page.clock.fastForward(30000);await expect.poll(()=>state.reads).toBe(2);
 state.version(3);await visibility(page,'hidden');await page.clock.fastForward(90000);expect(state.reads).toBe(2);await visibility(page,'visible');await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v3獎品1');expect(state.reads).toBe(3);
 state.release();await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v3獎品1');await page.screenshot({path:'artifacts/wheel-refresh-visible-v3.png',fullPage:true});
 state.version(4);await page.clock.fastForward(30000);await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v4獎品1');expect(state.reads).toBe(4);
});
test('refresh failure disables draw, retry recovers and visible revision is submitted',async({page})=>{
 const state=await setup(page);state.fail();await page.clock.fastForward(30000);await expect(page.getByText(/無法更新獎池，暫停抽獎/)).toBeVisible();await expect(page.getByRole('button',{name:'體驗示範轉盤'})).toBeDisabled();expect(state.posts).toBe(0);
 state.version(2);await page.getByRole('button',{name:'重新讀取獎池'}).click();await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v2獎品1');await page.getByRole('button',{name:'確認新版並體驗'}).click({clickCount:2});await expect(page.getByRole('dialog')).toBeVisible();expect(state.posts).toBe(1);
 const reads=state.reads;state.version(3);await page.clock.fastForward(60000);await visibility(page,'hidden');await visibility(page,'visible');expect(state.reads).toBe(reads);await expect(page.getByRole('dialog').getByRole('heading')).toHaveText('v2獎品1');await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v2獎品1');
 await page.getByRole('button',{name:'知道了'}).click();await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v3獎品1');
});
test('account switch clears pending refresh and a new account cannot receive its response',async({page})=>{
 const state=await setup(page);state.version(9);state.hold();await page.clock.fastForward(30000);await expect.poll(()=>state.reads).toBe(2);await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'切換帳號',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();state.release();await expect(page.locator('.demo-wheel')).toHaveCount(0);
 state.version(10);await page.getByLabel('電子郵件').fill('next@example.invalid');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.locator('.demo-wheel .wheel-label').first()).toHaveText('v10獎品1');await expect(page.getByRole('dialog')).toHaveCount(0);
});
