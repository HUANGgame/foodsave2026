// Actual installed Android WebView + intercepted synthetic API. Never Azure/SQL.
const {expect}=require('@playwright/test');
const {_android}=require('playwright');
const {execFileSync}=require('node:child_process');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs');
const adb=process.env.ANDROID_HOME+'/platform-tools/adb';
function device(...args){return execFileSync(adb,['-s','emulator-5554',...args],{timeout:30000,encoding:'utf8'}).trim();}
function pass(message){console.log('PASS',message);if(process.env.GITHUB_STEP_SUMMARY)fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,`- PASS ${message}\n`);}
async function attach(){
 const devices=await _android.devices();
 const target=devices.find(d=>d.serial()==='emulator-5554');
 if(!target)throw Error('Expected actual emulator-5554');
 target.setDefaultTimeout(30000);
 try{const view=await target.webView({pkg:'tw.foodsave.demo'});return {page:await view.page(),close:()=>target.close()};}
 catch(e){
  console.log('Detected WebViews:',target.webViews().map(v=>({pkg:v.pkg(),pid:v.pid()})));
  // Still before fixture login; only startup errors, no account/session data.
  try{console.log(device('logcat','-d','-v','brief','AndroidRuntime:E','chromium:E','Capacitor:E','*:S').split('\n').slice(-100).join('\n'));}catch{}
  await target.close();throw e;
 }
}
async function fixture(page){
 let role='consumer',order=null,stock=2,submitted=null;
 const productId='11111111-1111-1111-1111-111111111111',storeId='33333333-3333-3333-3333-333333333333';
 const password=randomUUID(),token=randomUUID(),pickup=randomUUID();
 await page.route('https://api.foodsave.test/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname,method=req.method();const json=(body,status=200)=>route.fulfill({json:body,status});
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  if(path==='/auth/login'){const data=req.postDataJSON();role=data.email.split('@')[0];if(!['consumer','vendor','admin'].includes(role)||data.password!==password)return json({detail:'Fixture拒絕登入'},401);return json({access_token:token});}
  if(path==='/auth/logout')return json({logged_out:true});
  if(path==='/me')return json({id:role+'-fixture',email:role+'@example.test',role,spins:0,exp:0});
  if(path==='/products')return json([{id:productId,store_id:storeId,store_name:'Fixture店家',name:'Fixture便當',photo_url:'https://images.example.test/meal.png',latitude:25.033,longitude:121.541,available_quantity:stock,original_price_minor:10000,sale_price_minor:5000,pickup_deadline:'2027-01-01T12:00:00',revision:1}]);
  if(path==='/favorites')return json([]);
  if(path.startsWith('/stores/'))return json({average:null,count:0,items:[]});
  if(path==='/reservations'&&method==='GET')return json(order?[order]:[]);
  if(path==='/reservations'&&method==='POST'){stock--;order={id:'fixture-order',state:'waiting',quantity:1,product_id:productId,snapshot:{name:'Fixture便當',sale_price_minor:5000},pickup_code:pickup,expires_at:'2027-01-01T12:00:00'};return json(order,201);}
  if(path==='/reservations/fixture-order/cancel'){if(order.state==='waiting')stock++;order.state='cancelled';return json(order);}
  if(path==='/prizes'||path==='/draws')return json([]);
  if(path==='/vendor/catalog')return json({stores:[{id:storeId,name:'Fixture店家'}],products:[]});
  if(path==='/vendor/reservations')return json([]);
  if(path==='/vendor/products'){submitted=req.postDataJSON();return json({id:productId,revision:1},201);}
  return json({detail:'Unexpected synthetic route'},500);
 });
 await page.route('https://images.example.test/**',r=>r.abort());
 async function login(as){await page.getByLabel('電子郵件').fill(as+'@example.test');await page.getByLabel('密碼（至少12字元）').fill(password);await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);}
 return {login,pickup,token,get submitted(){return submitted;},get stock(){return stock;}};
}
(async()=>{
 let browser=await attach();
 try{
  const page=browser.page;if(!page)throw Error('No actual WebView page');page.setDefaultTimeout(20000);
  await expect(page.locator('.brand')).toContainText('食在可惜');
  if(!page.url().startsWith('https://localhost'))throw Error('Not Capacitor local APK assets');
  pass('APK installed, native activity launched and Capacitor WebView rendered');
  const mock=await fixture(page);
  await mock.login('consumer');await page.getByRole('button',{name:'預約1份'}).click();await expect(page.getByText(/預約成功/)).toBeVisible();
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();await expect(page.getByText(mock.pickup,{exact:true})).toBeVisible();await page.getByRole('button',{name:'取消預約',exact:true}).click();await expect(page.getByText('已取消',{exact:true})).toBeVisible();expect(mock.stock).toBe(2);
  pass('Consumer reserve, order navigation and cancellation in Android WebView (API fixture)');
  await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.getByRole('button',{name:'開始惜食抽獎'})).toBeDisabled();
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(mock.token);
  expect(await page.evaluate(()=>localStorage.getItem('foodsave-demo-v1'))).toBeNull();
  pass('Zero-spin guard, memory-only token and no demo fallback on fixture session');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'登出',exact:true}).click();await mock.login('vendor');
  await page.getByRole('link',{name:'商家工作台',exact:true}).click();await page.getByLabel('商品名稱',{exact:true}).fill('Android Fixture便當');await page.getByLabel('已授權商品照片網址').fill('https://images.example.test/food.jpg');await page.getByLabel('原價（元）').fill('100');await page.getByLabel('惜食價（元）').fill('50');await page.getByLabel('可預約庫存').fill('2');await page.getByLabel('領取截止').fill('2027-01-01T12:00');await page.getByRole('button',{name:'儲存商品'}).click();await expect(page.getByText('商品已儲存')).toBeVisible();expect(mock.submitted).toMatchObject({original_price_minor:10000,sale_price_minor:5000,available_quantity:2});
  pass('Vendor form submits expected product contract from Android WebView (API fixture)');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'登出',exact:true}).click();await mock.login('admin');await expect(page.getByRole('link',{name:'管理中心',exact:true})).toHaveAttribute('href','https://api.foodsave.test/admin');await expect(page.getByRole('link',{name:'商家工作台',exact:true})).toHaveCount(0);
  pass('Admin account sees its management link; vendor link absent (fixture, not admin CRUD acceptance)');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  device('shell','am','force-stop','tw.foodsave.demo');
  try{await browser.close();}catch{}
  device('shell','am','start','-W','-n','tw.foodsave.demo/.MainActivity');
  browser=await attach();const reopened=browser.page;await expect(reopened.getByRole('button',{name:'登入',exact:true})).toBeVisible();
  pass('Native force-stop/relaunch renders login and does not retain bearer session');
 }finally{await browser.close();}
})().catch(e=>{console.error('FAIL Android fixture:',e.message);process.exitCode=1;});
