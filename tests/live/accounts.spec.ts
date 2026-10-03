import {test,expect} from '@playwright/test';
import {randomBytes,randomUUID} from 'node:crypto';
const code=()=>randomBytes(32).toString('base64url');
test('registration is email-first; code/password never persisted and successful verification does not auto-login',async({page})=>{
 const secret=code(),password=randomUUID();let requested=0,finished=0,logins=0;
 await page.route('https://api.foodsave.test/**',r=>{const path=new URL(r.request().url()).pathname,body=r.request().postDataJSON();
  if(path==='/auth/options')return r.fulfill({json:{registration_enabled:true,recovery_enabled:true}});
  if(path==='/auth/register'){requested++;expect(body).toEqual({email:'owner@example.test'});return r.fulfill({status:202,json:{detail:'若此信箱可完成此操作，請查看信件並依指示繼續。'}});}
  if(path==='/auth/verify-email'){finished++;expect(body).toEqual({email:'owner@example.test',password,code:secret});return r.fulfill({json:{detail:'已完成。請使用新密碼重新登入。'}});}
  if(path==='/auth/login')logins++;return r.fulfill({status:503,json:{detail:'fixture endpoint unavailable'}});
 });
 await page.goto('/');await page.getByRole('button',{name:'第一次使用？建立帳號'}).click();await page.getByLabel('電子郵件').fill('owner@example.test');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'寄送驗證碼'}).click();expect(requested).toBe(1);await page.getByLabel('信箱驗證碼').fill(secret);await page.getByLabel('新密碼（至少15字元）',{exact:true}).fill(password);await page.getByLabel('再次輸入新密碼').fill(password);await page.getByRole('checkbox').check();await page.getByRole('button',{name:'驗證並建立帳號'}).click();await expect(page.getByText('已完成。請使用新密碼重新登入。')).toBeVisible();expect(finished).toBe(1);expect(logins).toBe(0);
 const stored=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));expect(stored).not.toContain(secret);expect(stored).not.toContain(password);await page.getByRole('button',{name:'返回登入'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
});
test('reset rejects expired code honestly and resend requires explicit action',async({page})=>{
 let requests=0,resets=0;await page.route('https://api.foodsave.test/**',r=>{const path=new URL(r.request().url()).pathname;if(path==='/auth/options')return r.fulfill({json:{registration_enabled:false,recovery_enabled:true}});if(path==='/auth/forgot-password'){requests++;return r.fulfill({status:202,json:{detail:'請查看信件。'}});}if(path==='/auth/reset-password'){resets++;return r.fulfill({status:400,json:{detail:'驗證碼無效、已使用或已過期，請重新申請。'}});}return r.abort();});
 await page.goto('/');await page.getByRole('button',{name:'忘記密碼'}).click();await page.getByLabel('電子郵件').fill('owner@example.test');await page.getByRole('button',{name:'寄送驗證碼'}).click();await page.getByLabel('信箱驗證碼').fill(code());const password=randomUUID();await page.getByLabel('新密碼（至少15字元）',{exact:true}).fill(password);await page.getByLabel('再次輸入新密碼').fill(password);await page.getByRole('button',{name:'確認重設密碼'}).click();await expect(page.getByText('驗證碼無效、已使用或已過期，請重新申請。')).toBeVisible();expect(requests).toBe(1);expect(resets).toBe(1);await expect(page.getByLabel('新密碼（至少15字元）',{exact:true})).toHaveValue('');await page.getByRole('button',{name:'重新申請驗證碼／更換信箱'}).click();await page.getByRole('button',{name:'寄送驗證碼'}).click();expect(requests).toBe(2);
});
test('unconfigured account services cannot submit or silently skip verification',async({page})=>{
 let posts=0;await page.route('https://api.foodsave.test/**',r=>{if(r.request().method()==='POST')posts++;return r.fulfill({json:{registration_enabled:false,recovery_enabled:false}});});await page.goto('/');await page.getByRole('button',{name:'第一次使用？建立帳號'}).click();await expect(page.getByRole('alert').filter({hasText:'不會略過信箱驗證'})).toContainText('不會略過信箱驗證');await expect(page.getByRole('button',{name:'寄送驗證碼'})).toBeDisabled();expect(posts).toBe(0);
});
test('change password confirms current password and clears local session after success',async({page})=>{
 const old=randomUUID(),password=randomUUID(),bearer=randomUUID();let changed=false,submitted=0;
 await page.route('https://api.foodsave.test/**',r=>{const path=new URL(r.request().url()).pathname;
  if(path==='/auth/login')return r.fulfill({json:{access_token:bearer}});
  if(path==='/me')return r.fulfill({json:{id:'consumer',email:'owner@example.test',role:'consumer',exp:0,spins:0}});
  if(path==='/auth/change-password'){submitted++;expect(r.request().headers().authorization).toBe('Bearer '+bearer);expect(r.request().postDataJSON()).toEqual({current_password:old,password});changed=true;return r.fulfill({json:{sessions_revoked:true}});}
  return r.fulfill({json:[]});
 });
 await page.goto('/profile/');await page.getByLabel('電子郵件').fill('owner@example.test');await page.getByLabel('密碼（至少12字元）').fill(old);await page.getByRole('button',{name:'登入',exact:true}).click();await page.getByRole('button',{name:'變更密碼',exact:true}).click();await page.getByLabel('目前密碼').fill(old);await page.getByLabel('新密碼（至少15字元）',{exact:true}).fill(password);await page.getByLabel('再次輸入新密碼').fill(password);await page.getByRole('button',{name:'確認變更密碼'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();expect(changed).toBe(true);expect(submitted).toBe(1);const stored=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));for(const secret of [old,password,bearer])expect(stored).not.toContain(secret);
});


test('shared installed-Android account fixture completes register reset and password change',async({page})=>{
 await page.goto('/');
 await require('../../scripts/account-fixture.cjs')(page,()=>{});
});
