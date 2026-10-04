// Shared browser/installed-Android UI contract. No real email, SQL or credentials.
const {expect}=require('@playwright/test');
const {randomUUID,randomBytes}=require('node:crypto');
module.exports=async function accountFixture(page,pass){
 const email='auth-fixture@example.test',code=randomBytes(32).toString('base64url');
 const initial=randomUUID(),replacement=randomUUID(),changed=randomUUID();
 let password=null,registered=false,mailCount=0,resets=0,changes=0,session=null;
 const pattern='https://api.foodsave.test/**';
 const handler=route=>{
  const request=route.request(),path=new URL(request.url()).pathname,method=request.method();
  const body=method==='POST'?request.postDataJSON():null;
  const json=(data,status=200)=>route.fulfill({json:data,status});
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  if(path==='/auth/options')return json({registration_enabled:true,recovery_enabled:true});
  if(path==='/auth/register'||path==='/auth/forgot-password'){expect(body).toEqual({email});mailCount++;return json({detail:'Fixture：請查看信件。'},202);}
  if(path==='/auth/verify-email'){expect(body).toEqual({email,code,password:initial});registered=true;password=initial;return json({detail:'已完成。請使用新密碼重新登入。'});}
  if(path==='/auth/reset-password'){
   resets++;if(body.code!==code)return json({detail:'驗證碼無效、已使用或已過期，請重新申請。'},400);
   expect(registered).toBe(true);expect(body).toEqual({email,code,password:replacement});password=replacement;session=null;
   return json({detail:'已完成。請使用新密碼重新登入。',sessions_revoked:true});
  }
  if(path==='/auth/login'){
   if(body.email!==email||body.password!==password)return json({detail:'Fixture：帳號或密碼錯誤'},401);
   session=randomUUID();return json({access_token:session});
  }
  if(path==='/auth/change-password'){
   expect(request.headers().authorization).toBe('Bearer '+session);expect(body).toEqual({current_password:replacement,password:changed});
   password=changed;session=null;changes++;return json({sessions_revoked:true});
  }
  if(path==='/auth/logout'){session=null;return json({logged_out:true});}
  if(path==='/me')return json({id:'auth-fixture',email,role:'consumer',exp:0,spins:0});
  if(['/products','/stores','/favorites','/notifications','/reservations','/draws','/prizes'].includes(path))return json([]);
  return json({detail:'Unexpected account fixture route'},500);
 };
 await page.route(pattern,handler);
 try{
  await page.getByRole('button',{name:'第一次使用？建立帳號'}).click();
  await page.getByLabel('電子郵件').fill(email);await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:'寄送驗證碼'}).click();
  async function fillSecret(value,newPassword){
   await page.getByLabel('信箱驗證碼').fill(value);
   await page.getByLabel('新密碼（至少15字元）',{exact:true}).fill(newPassword);
   await page.getByLabel('再次輸入新密碼').fill(newPassword);
  }
  await fillSecret(code,initial);await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:'驗證並建立帳號'}).click();
  await expect(page.getByText('已完成。請使用新密碼重新登入。')).toBeVisible();expect(session).toBeNull();
  await page.getByRole('button',{name:'返回登入'}).click();
  pass('Account fixture: email-first registration requires code, returns to login without auto-session');
  await page.getByRole('button',{name:'忘記密碼'}).click();await page.getByLabel('電子郵件').fill(email);
  await page.getByRole('button',{name:'寄送驗證碼'}).click();
  await fillSecret(randomBytes(32).toString('base64url'),replacement);await page.getByRole('button',{name:'確認重設密碼'}).click();
  await expect(page.getByText('驗證碼無效、已使用或已過期，請重新申請。')).toBeVisible();
  await expect(page.getByLabel('新密碼（至少15字元）',{exact:true})).toHaveValue('');
  await fillSecret(code,replacement);await page.getByRole('button',{name:'確認重設密碼'}).click();
  await expect(page.getByText('已完成。請使用新密碼重新登入。')).toBeVisible();
  await page.getByRole('button',{name:'返回登入'}).click();
  async function login(value){await page.getByLabel('電子郵件').fill(email);await page.getByLabel('密碼',{exact:true}).fill(value);await page.getByRole('button',{name:'登入',exact:true}).click();}
  await login(initial);await expect(page.getByText('Fixture：帳號或密碼錯誤')).toBeVisible();
  await login(replacement);await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);
  pass('Account fixture: invalid reset rejected, successful reset accepts new login and rejects old password');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'變更密碼',exact:true}).click();
  await page.getByLabel('目前密碼').fill(replacement);await page.getByLabel('新密碼（至少15字元）',{exact:true}).fill(changed);await page.getByLabel('再次輸入新密碼').fill(changed);
  await page.getByRole('button',{name:'確認變更密碼'}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
  expect(changes).toBe(1);expect(resets).toBe(2);expect(mailCount).toBe(2);expect(session).toBeNull();
  const stored=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));
  for(const secret of [code,initial,replacement,changed])expect(stored).not.toContain(secret);
  pass('Account fixture: password change submits current password and clears local session; no password/code persisted');
 }finally{await page.unroute(pattern,handler);}
};
