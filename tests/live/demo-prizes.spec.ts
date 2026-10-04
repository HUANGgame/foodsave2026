import {test,expect} from '@playwright/test';
import {spawn,ChildProcess} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
let server:ChildProcess,folder:string;
const backend='http://127.0.0.1:4181';
test.beforeAll(async()=>{
 folder=await mkdtemp(join(tmpdir(),'foodsave-demo-qa-'));
 server=spawn(process.env.FOODSAVE_TEST_PYTHON||'python3',['backend/qa/demo_prize_fixture.py'],{env:{...process.env,PYTHONPATH:'backend',FOODSAVE_QA_LOOPBACK_ONLY:'true',FOODSAVE_DEMO_PRIZES_ENABLED:'true',FOODSAVE_DEMO_PRIZE_STORE:join(folder,'demo-prizes.json')},stdio:'ignore'});
 for(let i=0;i<100;i++){try{const r=await fetch(backend+'/health/live');if(r.ok)return;}catch{}await new Promise(r=>setTimeout(r,50));}
 throw new Error('Local synthetic fixture did not start');
});
test.afterAll(async()=>{server?.kill();if(folder)await rm(folder,{recursive:true,force:true});});
test('admin edits real local demo config; consumer wheel and result use that version without issuing coupons',async({browser,page})=>{
 let formalDraws=0,demoDraws=0,poolReads=0,failNext=false,holdNext=false,captured=false;let release=()=>{};
 await page.route('https://api.foodsave.test/**',async r=>{const path=new URL(r.request().url()).pathname;
  if(path==='/demo-prizes')poolReads++;
  if(path==='/demo-draws'){demoDraws++;if(failNext){failNext=false;return r.abort('failed');}await new Promise(resolve=>setTimeout(resolve,250));}
  if(path.startsWith('/demo-')){const response=await r.fetch({url:backend+path,headers:{'Content-Type':'application/json',Authorization:'Bearer synthetic-consumer'}});if(path==='/demo-draws'&&holdNext){holdNext=false;captured=true;await new Promise<void>(resolve=>{release=resolve;});}return r.fulfill({response});}
  if(path==='/auth/login')return r.fulfill({json:{access_token:'synthetic-consumer'}});
  if(path==='/me')return r.fulfill({json:{id:'synthetic-consumer',email:'fixture@example.invalid',role:'consumer',exp:0,spins:0}});
  if(path==='/draws')formalDraws++;
  return r.fulfill({json:[]});
 });
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/missions/');await page.getByLabel('電子郵件').fill('fixture@example.invalid');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();
 await expect(page.locator('.demo-wheel .wheel-label')).toHaveCount(6);const originalLabels=await page.locator('.demo-wheel .wheel-label').allTextContents();await expect(page.getByText('示範，暫不可兌換',{exact:true})).toBeVisible();
 const admin=await browser.newPage({viewport:{width:1280,height:900}});
 await admin.route(backend+'/auth/login',r=>r.fulfill({json:{access_token:'synthetic-admin'}}));
 await admin.route(backend+'/auth/logout',r=>r.fulfill({json:{logged_out:true}}));
 await admin.route(backend+'/me',r=>r.fulfill({json:{role:'admin'}}));
 await admin.route(backend+'/admin/data/**',r=>r.fulfill({json:{rows:[]}}));
 await admin.goto(backend+'/admin');await admin.getByLabel('電子郵件').fill('admin@example.invalid');await admin.getByLabel('密碼').fill(randomUUID());await admin.getByRole('button',{name:'登入',exact:true}).click();await admin.getByRole('button',{name:'編輯六格示範獎池'}).click();
 for(let i=0;i<6;i++)await admin.locator(`[name="${i}-name"]`).fill('修改示範'+(i+1));
 await admin.getByRole('button',{name:'儲存示範獎池'}).click();await expect(admin.getByRole('status')).toContainText('版本 2');await admin.screenshot({path:'artifacts/ux-demo-admin.png',fullPage:true});await page.waitForTimeout(1000);await expect(page.locator('.demo-wheel .wheel-label')).toHaveText(originalLabels);expect(poolReads).toBe(1);await page.screenshot({path:'artifacts/role-product-owner-open-stale.png',fullPage:true});
 await page.getByRole('button',{name:'體驗示範轉盤'}).click({clickCount:2});await expect(page.getByText('獎池已更新，本次未抽獎。請確認新版內容，再按一次體驗。')).toBeVisible();await expect(page.getByRole('dialog')).toHaveCount(0);expect(demoDraws).toBe(1);await page.getByRole('button',{name:'確認新版並體驗'}).click();const result=page.getByRole('dialog',{name:'示範抽獎結果'});await expect(result).toBeVisible();const box=await result.boundingBox();const viewport=page.viewportSize()!;expect(Math.abs(box!.x+box!.width/2-viewport.width/2)).toBeLessThan(2);expect(Math.abs(box!.y+box!.height/2-viewport.height/2)).toBeLessThan(2);await expect(result.getByRole('heading')).toContainText('修改示範');
 await expect(page.locator('.demo-wheel .wheel-label')).toHaveText(Array.from({length:6},(_,i)=>'修改示範'+(i+1)));await expect(result).toContainText('沒有兌換碼');await page.screenshot({path:'artifacts/ux-demo-result.png',fullPage:true});expect(formalDraws).toBe(0);expect(demoDraws).toBe(2);await result.getByRole('button',{name:'知道了'}).click();await expect(result).toHaveCount(0);await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.locator('.demo-wheel .wheel-label')).toHaveCount(6);await expect(page.getByRole('dialog')).toHaveCount(0);failNext=true;await page.getByRole('button',{name:'體驗示範轉盤'}).click();await expect(page.getByText(/連線未完成/)).toBeVisible();await page.screenshot({path:'artifacts/role-product-owner-recovery.png',fullPage:true});await page.getByRole('button',{name:'體驗示範轉盤'}).click();await expect(result).toBeVisible();await page.keyboard.press('Escape');await expect(result).toHaveCount(0);expect(demoDraws).toBe(4);expect(formalDraws).toBe(0);expect(poolReads).toBeGreaterThanOrEqual(2);holdNext=true;await page.getByRole('button',{name:'體驗示範轉盤'}).click();await expect.poll(()=>captured).toBe(true);for(let i=0;i<6;i++)await admin.locator(`[name="${i}-name"]`).fill('中途新版'+(i+1));await admin.getByRole('button',{name:'儲存示範獎池'}).click();await expect(admin.getByRole('status')).toContainText('版本 3');release();await expect(result).toBeVisible();await expect(result.getByRole('heading')).toContainText('修改示範');await expect(page.locator('.demo-wheel .wheel-label')).toHaveText(Array.from({length:6},(_,i)=>'修改示範'+(i+1)));await page.screenshot({path:'artifacts/role-product-owner-pinned-result.png',fullPage:true});await result.getByRole('button',{name:'知道了'}).click();await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.locator('.demo-wheel .wheel-label')).toHaveText(Array.from({length:6},(_,i)=>'中途新版'+(i+1)));expect(poolReads).toBeGreaterThanOrEqual(3);expect(formalDraws).toBe(0);
 await admin.getByRole('button',{name:'登出',exact:true}).click().catch(()=>{});await admin.close();
});
