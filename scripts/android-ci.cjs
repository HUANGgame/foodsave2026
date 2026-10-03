// Actual installed Android WebView + intercepted synthetic API. Never Azure/SQL.
const {expect}=require('@playwright/test');
const {_android}=require('playwright');
const {execFileSync}=require('node:child_process');
const {randomUUID,randomBytes}=require('node:crypto');
const fs=require('node:fs');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
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
 let vendorStage='existing',role='consumer',account='consumer',mode='reservation',pending=1,showProducts=true,favorite=false,noticeRead=false,modeRequests=0,lossRequests=0,pickupState='completed',offlineLogout=false,order=null,stock=2,submitted=null,drawRequests=0,pickupPreviews=0,pickupConfirms=0;const confirmKeys=[];
 const draws=[],drawKeys=new Map();
 const segments=Array.from({length:6},(_,i)=>({id:`qa-prize-${i}`,name:i===2?'Fixture8折券':`Fixture獎品${i}`}));
 const prize={...segments[2],kind:'coupon',terms:'Synthetic fixture; no redemption value',expires_at:'2027-01-01T00:00:00',discount_percent:20};
 const productId='11111111-1111-1111-1111-111111111111',storeId='33333333-3333-3333-3333-333333333333';
 const password=randomUUID(),token=randomUUID(),pickup=randomBytes(6).toString('hex').toUpperCase(),reviewToken=randomBytes(32).toString('base64url');
 await page.route('https://api.foodsave.test/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname,method=req.method();const json=(body,status=200)=>route.fulfill({json:body,status});
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  if(path==='/auth/login'){const data=req.postDataJSON();account=data.email.split('@')[0];role=account==='consumer2'?'consumer':account;if(!['consumer','consumer2','vendor','admin'].includes(account)||data.password!==password)return json({detail:'Fixture拒絕登入'},401);return json({access_token:token});}
  if(path==='/auth/logout'&&offlineLogout)return route.abort('failed');
  if(path==='/auth/logout')return json({logged_out:true});
  if(path==='/me')return json({id:account+'-fixture',email:account+'@example.test',role,spins:2-draws.length,exp:0});
  if(path==='/vendor/pickups/preview'){pickupPreviews++;expect(req.postDataJSON().credential).toBe(pickup);return json({id:'fixture-pickup',name:'Fixture便當',quantity:1,total_price_minor:5000,review_token:reviewToken,review_expires_at:'2027-01-01T12:00:00'});}
  if(path==='/vendor/pickups/confirm'){pickupConfirms++;confirmKeys.push(req.headers()['idempotency-key']);expect(req.postDataJSON().review_token).toBe(reviewToken);if(pickupConfirms===1)return route.abort('failed');return json({id:'fixture-pickup',state:pickupState,...(pickupState==='expired'?{terminal_reason:'expired'}:{})});}
  if(path==='/products'&&!showProducts)return json([]);
  if(path==='/products')return json([{id:productId,store_id:storeId,store_name:'Fixture店家',name:'Fixture便當',photo_url:'https://images.example.test/meal.png',latitude:25.033,longitude:121.541,source:'foodsave',service_mode:mode,available_quantity:stock,original_price_minor:10000,sale_price_minor:5000,pickup_deadline:'2027-01-01T12:00:00',revision:1}]);
  if(path==='/stores')return json([{id:storeId,vendor_id:'fixture-vendor',name:'Fixture店家',latitude:25.033,longitude:121.541,service_mode:mode,product_count:showProducts?1:0}]);
  if(path==='/notifications')return json(account==='consumer'?[{id:'fixture-notice',kind:'vendor_out_of_stock',body:'Fixture缺貨通知：請勿再前往取貨。',created_at:'2026-10-03T08:00:00',read_at:noticeRead?'2026-10-03T09:00:00':null}]:[]);
  if(path==='/notifications/fixture-notice/read'){expect(account).toBe('consumer');noticeRead=true;return json({read:true});}
  if(path==='/favorites')return json(account==='consumer'&&favorite?['fixture-vendor']:[]);
  if(path==='/favorites/fixture-vendor'){favorite=req.postDataJSON().enabled;return json({vendor_id:'fixture-vendor',enabled:favorite});}
  if(path.startsWith('/stores/'))return json({average:null,count:0,items:[]});
  if(path==='/reservations'&&method==='GET')return json(account==='consumer'&&order?[order]:[]);
  if(path==='/reservations'&&method==='POST'){stock--;order={id:'fixture-order',state:'waiting',quantity:1,product_id:productId,snapshot:{name:'Fixture便當',sale_price_minor:5000},pickup_code:pickup,expires_at:'2027-01-01T12:00:00'};return json(order,201);}
  if(path==='/reservations/fixture-order/cancel'){if(order.state==='waiting')stock++;order.state='cancelled';return json(order);}
  if(path==='/prizes')return json(segments);
  if(path==='/draws'&&method==='GET')return json(draws.map(d=>({id:d.id,prize_snapshot:JSON.stringify(d.prize),coupon_code:d.coupon_code})));
  if(path==='/draws'&&method==='POST'){drawRequests++;const key=req.headers()['idempotency-key'];if(drawKeys.has(key))return json(drawKeys.get(key),201);if(draws.length>=2)return json({detail:'Fixture spins exhausted'},409);const draw={id:randomUUID(),prize,segments,coupon_code:randomUUID()};draws.push(draw);drawKeys.set(key,draw);return json(draw,201);}
  if(path==='/vendor/catalog'&&vendorStage==='unassigned')return json({stores:[],products:[]});
  if(path==='/vendor/catalog'&&vendorStage==='empty')return json({stores:[{id:storeId,name:'Fixture店家',service_mode:mode,pending_orders:0}],products:[]});
  if(path==='/vendor/catalog')return json({stores:[{id:storeId,name:'Fixture店家',service_mode:mode,pending_orders:pending}],products:[{id:productId,store_id:storeId,name:'Fixture便當',photo_url:'https://images.example.test/meal.png',original_price_minor:10000,sale_price_minor:5000,available_quantity:stock,pickup_deadline:'2027-01-01T12:00:00',revision:1,active:true}]});
  if(path===`/vendor/stores/${storeId}/mode`){modeRequests++;const next=req.postDataJSON().service_mode;if(next==='information'&&pending>0)return json({detail:'Fixture仍有待領預約，不能切換模式'},409);mode=next;return json({id:storeId,service_mode:mode});}
  if(path===`/vendor/products/${productId}/stock-loss-preview`)return json({id:productId,name:'Fixture便當',revision:1,available_quantity:stock,pending_count:pending});
  if(path===`/vendor/products/${productId}/stock-loss`){lossRequests++;expect(req.postDataJSON()).toEqual({expected_revision:1,expected_pending:1,actual_available:0,confirm:'CANCEL_AFFECTED'});stock=0;pending=0;noticeRead=false;return json({cancelled_count:1});}
  if(path==='/vendor/reservations')return json([]);
  if(path==='/vendor/products'){submitted=req.postDataJSON();return json({id:productId,revision:1},201);}
  return json({detail:'Unexpected synthetic route'},500);
 });
 await page.route('https://images.example.test/**',r=>r.abort());
 await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
 async function login(as){await page.getByLabel('電子郵件').fill(as+'@example.test');await page.getByLabel('密碼（至少12字元）').fill(password);await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);}
 return {login,pickup,token,confirmKeys,setVendorStage(value){vendorStage=value;},setMode(value){mode=value;},setZeroProducts(){showProducts=false;favorite=true;},restoreProducts(){showProducts=true;},setOfflineLogout(value){offlineLogout=value;},setExpiredPickup(){pickupState='expired';},get mode(){return mode;},get modeRequests(){return modeRequests;},get lossRequests(){return lossRequests;},get pickupPreviews(){return pickupPreviews;},get pickupConfirms(){return pickupConfirms;},get draws(){return draws;},get drawRequests(){return drawRequests;},get submitted(){return submitted;},get stock(){return stock;}};
}
async function denyLocationDialog(){
 for(let attempt=0;attempt<4;attempt++){
  let xml='';
  try{
   // A transient null accessibility root produces no file. Retry within the
   // existing four attempts, never reuse a stale permission-dialog snapshot.
   device('shell','rm','-f','/sdcard/foodsave-qa-ui.xml');
   device('shell','uiautomator','dump','/sdcard/foodsave-qa-ui.xml');
   xml=device('shell','cat','/sdcard/foodsave-qa-ui.xml');
  }catch{console.log('Permission hierarchy not ready; bounded retry');await pause(500);continue;}
  const node=(xml.match(/<node[^>]*>/g)||[]).find(n=>/resource-id="[^"]*:id\/permission_deny_button"/.test(n));
  const bounds=node?.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
  if(bounds){device('shell','input','tap',String(Math.floor((+bounds[1]+ +bounds[3])/2)),String(Math.floor((+bounds[2]+ +bounds[4])/2)));return;}
  await pause(500);
 }
 throw Error('Expected native location permission denial control');
}
function nativeWindowFocus(){
 const lines=device('shell','dumpsys','window').split('\n').filter(l=>/mCurrentFocus=|mFocusedApp=/.test(l));
 return (lines.length?lines:device('shell','dumpsys','activity','activities').split('\n').filter(l=>/mCurrentFocus=|mFocusedApp=/.test(l))).join('\n');
}
async function ensureFoodSaveForeground(){
 let dismissed=false;const observations=[];
 try{await expect.poll(()=>{
  const focus=nativeWindowFocus();
  if(observations.at(-1)!==focus)observations.push(focus);
  if(/mCurrentFocus=.*com\.google\.android\.gms.*LocationOffWarningActivity/.test(focus)&&!dismissed){
   dismissed=true;console.log('Dismissing known emulator LocationOffWarningActivity with Back (no consent accepted)');device('shell','input','keyevent','KEYCODE_BACK');return false;
  }
  return /mCurrentFocus=.*tw\.foodsave\.demo\/tw\.foodsave\.demo\.MainActivity/.test(focus);
 }).toBe(true);}catch(error){
  console.log('Native foreground assertion failed; observed focus fields',JSON.stringify(observations.slice(-6)));
  console.log('Native foreground activity fields',device('shell','dumpsys','activity','activities').split('\n').filter(l=>/mCurrentFocus=|mFocusedApp=|topResumedActivity=|mResumedActivity=/.test(l)).join('\n'));
  console.log('Native foreground power fields',device('shell','dumpsys','power').split('\n').filter(l=>/mWakefulness=|mInteractive=/.test(l)).join('\n'));
  throw error;
 }
 if(dismissed)pass('Known Google location-off system warning dismissed; FoodSave native focus restored without granting permission');
}
async function focusEmailNatively(page){
 await ensureFoodSaveForeground();
 await expect(page.getByLabel('電子郵件')).toBeVisible();
 console.log('Initial WebView metrics',JSON.stringify(await page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scrollY,visualWidth:visualViewport?.width,visualHeight:visualViewport?.height,emailRect:document.querySelector('input[name="email"]').getBoundingClientRect().toJSON()}))));
 for(let attempt=0;attempt<4;attempt++){
  let xml='';try{device('shell','rm','-f','/sdcard/foodsave-qa-input.xml');device('shell','uiautomator','dump','/sdcard/foodsave-qa-input.xml');xml=device('shell','cat','/sdcard/foodsave-qa-input.xml');}catch{await pause(500);continue;}
  const node=(xml.match(/<node[^>]*>/g)||[]).find(n=>/class="android.widget.EditText"/.test(n)&&/package="tw.foodsave.demo"/.test(n)&&/enabled="true"/.test(n)&&/password="false"/.test(n));
  const b=node?.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
  if(b&&+b[3]>+b[1]&&+b[4]>+b[2]){console.log('Native email input bounds',b.slice(1).join(','));device('shell','input','tap',String(Math.floor((+b[1]+ +b[3])/2)),String(Math.floor((+b[2]+ +b[4])/2)));return;}
  await pause(500);
 }
 throw Error('Visible native email input unavailable');
}
async function profileAfterResume(page){
 const link=page.getByRole('link',{name:'個人中心',exact:true});await expect(link).toBeVisible();
 await ensureFoodSaveForeground();
 await page.evaluate(()=>{window.__qaFrames=0;const tick=()=>{window.__qaFrames++;if(window.__qaFrames<20)requestAnimationFrame(tick);};requestAnimationFrame(tick);});
 const samples=[];for(let i=0;i<3;i++){samples.push(await link.boundingBox());await pause(200);}
 const state=await page.evaluate(()=>({visibility:document.visibilityState,focused:document.hasFocus(),frames:window.__qaFrames,animations:document.getAnimations().filter(a=>a.playState==='running').length}));
 console.log('Post-resume frame/layout diagnostic',JSON.stringify({state,navBounds:samples}));
 await expect.poll(()=>page.evaluate(()=>window.__qaFrames)).toBeGreaterThan(1);
 await link.click();
 await expect(page.getByRole('heading',{name:'個人中心',exact:true})).toBeVisible();await expect(page).toHaveURL(/\/profile\/$/);
 pass('Normal profile click is actionable after HOME/resume with frame progress; no forced click');
}
async function nativeInteractionChecks(page,mock){
 await page.getByRole('link',{name:'探索地圖',exact:true}).click();
 await page.getByRole('button',{name:'使用目前位置'}).click();
 await denyLocationDialog();await expect(page.getByText(/未允許定位/)).toBeVisible();
 await expect(page.getByRole('heading',{name:'Fixture便當'})).toBeVisible();
 pass('Native Android location permission denied; Chinese feedback and fixture list remain');
 try{
  device('shell','cmd','location','set-location-enabled','false');
  await page.getByRole('button',{name:'使用目前位置'}).click();
  await expect(page.getByText(/目前無法取得位置/)).toBeVisible();
  await expect(page.getByRole('heading',{name:'Fixture便當'})).toBeVisible();
  pass('Native location service disabled; actionable feedback without fake position');
 }finally{device('shell','cmd','location','set-location-enabled','true');}
 await ensureFoodSaveForeground();
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();
 await expect(page).toHaveURL(/\/reservations\/$/);await expect(page.getByRole('heading',{name:'我的預約',exact:true})).toBeVisible();
 const keyboardShown=()=>/mInputShown=true|isInputViewShown=true/.test(device('shell','dumpsys','input_method'));
 console.log('Before native Back',JSON.stringify({keyboardShown:keyboardShown(),historyLength:await page.evaluate(()=>history.length)}));
 const windowFocus=nativeWindowFocus;
 console.log('Before native Back window',windowFocus());
 console.log('Before native Back power',device('shell','dumpsys','power').split('\n').filter(l=>/mWakefulness=|mInteractive=/.test(l)).join(' '));
 await ensureFoodSaveForeground();
 if(keyboardShown()){
  device('shell','input','keyevent','KEYCODE_BACK');await expect.poll(keyboardShown).toBe(false);await expect(page).toHaveURL(/\/reservations\/$/);
  pass('First native Back dismisses visible IME without navigating; subsequent Back must navigate');
 }
 device('shell','input','keyevent','KEYCODE_BACK');
 try{await expect(page).toHaveURL(/\/profile\/$/);await expect(page.getByRole('heading',{name:'個人中心',exact:true})).toBeVisible();}
 catch(error){
  console.log('After native Back window',windowFocus());
  console.log('Native Back failure state',JSON.stringify(await page.evaluate(()=>({path:location.pathname,visibility:document.visibilityState,focused:document.hasFocus(),historyLength:history.length}))));
  try{const cdp=await page.context().newCDPSession(page);const h=await cdp.send('Page.getNavigationHistory');console.log('Native Back history',JSON.stringify({currentIndex:h.currentIndex,paths:h.entries.map(e=>new URL(e.url).hostname==='localhost'?new URL(e.url).pathname:'external')}));await cdp.detach();}catch{console.log('Navigation history diagnostic unavailable');}
  throw error;
 }
 pass('Native Android Back returns from reservations to profile without exiting');
 await page.getByRole('link',{name:'惜食任務',exact:true}).click();
 await page.getByRole('button',{name:'開始惜食抽獎'}).click({clickCount:2});
 await expect.poll(()=>mock.drawRequests).toBe(1);
 await expect(page.getByText('結果已保存，正在揭曉',{exact:true})).toBeVisible();
 device('shell','input','keyevent','KEYCODE_HOME');
 await expect.poll(()=>/topResumedActivity[^\n]*tw\.foodsave\.demo/.test(device('shell','dumpsys','activity','activities'))).toBe(false);
 device('shell','am','start','-W','-n','tw.foodsave.demo/.MainActivity');
 await expect.poll(()=>/topResumedActivity[^\n]*tw\.foodsave\.demo/.test(device('shell','dumpsys','activity','activities'))).toBe(true);
 await expect(page.getByRole('heading',{name:'獲得 Fixture8折券'})).toBeVisible({timeout:15000});
 const landing=await page.locator('.prize-wheel').evaluate(el=>{const m=new DOMMatrix(getComputedStyle(el).transform);return (Math.atan2(m.b,m.a)*180/Math.PI+360)%360;});
 expect(landing).toBeCloseTo(210,2);expect(mock.draws.length).toBe(1);expect(mock.drawRequests).toBe(1);
 pass('Actual WebView wheel double-tap sends one draw; HOME/resume preserves result and 210-degree landing');
 await profileAfterResume(page);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.getByRole('link',{name:'惜食任務',exact:true}).click();
 await expect(page.getByText(mock.draws[0].coupon_code,{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'開始惜食抽獎'}).click();
 await expect(page.getByRole('heading',{name:'獲得 Fixture8折券'})).toBeVisible();
 expect(await page.locator('.prize-wheel').evaluate(el=>el.getAnimations().length)).toBe(0);
 expect(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
 expect(mock.draws.length).toBe(2);expect(mock.drawRequests).toBe(2);
 pass('Reduced-motion media honored in Android WebView; saved draw history restored after navigation');
}
(async()=>{
 let browser=await attach();
 try{
  const page=browser.page;if(!page)throw Error('No actual WebView page');page.setDefaultTimeout(20000);
  page.on('crash',()=>console.log('Native diagnostic: Playwright page crash event'));
  page.on('close',()=>console.log('Native diagnostic: Playwright page close event'));
  page.context().on('close',()=>console.log('Native diagnostic: Playwright context close event'));
  await expect(page.locator('.brand')).toContainText('食在可惜');
  if(!page.url().startsWith('https://localhost'))throw Error('Not Capacitor local APK assets');
  pass('APK installed, native activity launched and Capacitor WebView rendered');
  const mock=await fixture(page);
  device('shell','settings','put','secure','show_ime_with_hard_keyboard','1');
  await focusEmailNatively(page);
  await expect.poll(()=>/mInputShown=true|isInputViewShown=true/.test(device('shell','dumpsys','input_method')),{timeout:15000}).toBe(true);
  device('shell','input','text','keyboard-check@example.test');
  await expect(page.getByLabel('電子郵件')).toHaveValue('keyboard-check@example.test');
  device('shell','input','keyevent','KEYCODE_BACK');
  await expect.poll(()=>/mInputShown=true|isInputViewShown=true/.test(device('shell','dumpsys','input_method')),{timeout:15000}).toBe(false);
  await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
  pass('Native soft keyboard accepts adb input; Back hides keyboard without leaving login');
  await mock.login('consumer');await page.getByRole('button',{name:'預約1份'}).click();await expect(page.getByText(/預約成功/)).toBeVisible();
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();await page.getByRole('button',{name:'出示取貨碼'}).click();await expect(page.getByText(mock.pickup,{exact:true})).toBeVisible();await page.getByRole('button',{name:'取消預約',exact:true}).click();await expect(page.getByText('已取消',{exact:true})).toBeVisible();expect(mock.stock).toBe(2);
  pass('Consumer reserve, order navigation and cancellation in Android WebView (API fixture)');
  mock.setMode('information');await page.getByRole('link',{name:'探索地圖',exact:true}).click();
  await expect(page.getByText('僅提供資訊，數量以現場為準')).toBeVisible();await expect(page.getByRole('button',{name:'預約1份'})).toHaveCount(0);
  pass('Information-mode product has no reservation control in installed Android WebView');
  mock.setZeroProducts();await page.getByRole('link',{name:'我的收藏',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Fixture店家',exact:true})).toBeVisible();await expect(page.getByText('目前沒有可供應的商品，仍可收藏店家並稍後查看。')).toBeVisible();
  await page.getByRole('button',{name:'取消收藏',exact:true}).click();await expect(page.getByRole('heading',{name:'這裡還沒有可用的好店'})).toBeVisible();
  pass('Vendor-account favorite remains visible without products and can be removed');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'通知中心（1則未讀）'}).click();
  await expect(page.getByText('Fixture缺貨通知：請勿再前往取貨。')).toBeVisible();await page.getByRole('button',{name:'標示已讀'}).click();await expect(page.getByText('已讀',{exact:true})).toBeVisible();
  pass('In-app notification displays and explicit read updates its fixture state');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();mock.setOfflineLogout(true);await page.getByRole('button',{name:'切換帳號',exact:true}).click();await expect(page.getByText(/已清除本機登入/)).toBeVisible();
  await mock.login('consumer2');await page.getByRole('link',{name:'通知中心（0則未讀）'}).click();await expect(page.getByText('目前沒有通知。')).toBeVisible();await expect(page.getByText('Fixture缺貨通知：請勿再前往取貨。')).toHaveCount(0);
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();await expect(page.getByText('目前沒有預約。')).toBeVisible();
  pass('Offline account switch clears local login; second consumer sees neither first account orders nor notices');
  mock.setOfflineLogout(false);mock.restoreProducts();mock.setMode('reservation');
  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'切換帳號',exact:true}).click();await mock.login('vendor');
  mock.setVendorStage('unassigned');await page.getByRole('link',{name:'商家工作台',exact:true}).click();
  await expect(page.getByRole('heading',{name:'等待管理者指派店家'})).toBeVisible();await expect(page.getByRole('button',{name:'快速上架',exact:true})).toHaveCount(0);
  mock.setVendorStage('empty');await page.getByRole('button',{name:'重新載入商家資料'}).click();await expect(page.getByRole('heading',{name:'等待管理者指派店家'})).toHaveCount(0);await expect(page.getByRole('heading',{name:'開始上架第一件商品'})).toBeVisible();await page.getByRole('button',{name:'上架第一件商品',exact:true}).click();await expect(page.getByLabel('商品名稱',{exact:true})).toBeVisible();
  pass('Unassigned vendor refreshes into assigned store and existing first product form');mock.setVendorStage('existing');await page.getByLabel('商品名稱',{exact:true}).fill('Android Fixture便當');await page.getByLabel('已授權商品照片網址').fill('https://images.example.test/food.jpg');await page.getByLabel('原價（元）').fill('100');await page.getByLabel('惜食價（元）').fill('50');await page.getByLabel('剩餘數量').fill('2');await page.getByLabel('領取截止').fill('2027-01-01T12:00');await page.getByRole('button',{name:'儲存商品'}).click();await expect(page.getByText('商品已儲存')).toBeVisible();expect(mock.submitted).toMatchObject({original_price_minor:10000,sale_price_minor:5000,available_quantity:2});
  pass('Vendor form submits expected product contract from Android WebView (API fixture)');
  const modeSelect=page.getByLabel('Fixture店家 服務模式');await expect(modeSelect.locator('option[value="information"]')).toHaveJSProperty('disabled',true);expect(mock.modeRequests).toBe(0);
  // Synthetic server409 exercises rejection even if an altered client enables the option.
  await modeSelect.locator('option[value="information"]').evaluate(el=>el.disabled=false);await modeSelect.selectOption('information');await expect(page.getByText('Fixture仍有待領預約，不能切換模式')).toBeVisible();await expect(modeSelect).toHaveValue('reservation');expect(mock.mode).toBe('reservation');expect(mock.modeRequests).toBe(1);
  pass('Pending mode option disabled; synthetic API409 also leaves reservation mode unchanged');
  await page.getByRole('button',{name:'實際缺貨，無法履約',exact:true}).click();await expect(page.getByText(/將取消並移除 1 筆待領預約/)).toBeVisible();expect(mock.lossRequests).toBe(0);
  await page.getByRole('checkbox',{name:'我確認上述預約均無法履約'}).check();await page.getByRole('button',{name:'確認缺貨並通知顧客'}).click();await expect(page.getByText(/已移除 1 筆無法履約預約/)).toBeVisible();expect(mock.lossRequests).toBe(1);expect(mock.stock).toBe(0);
  pass('Explicit stock-loss confirmation sends revision/pending/actual contract once; fixture inventory remains zero');

  await page.getByRole('button',{name:'掃碼取貨',exact:true}).click();
  await denyLocationDialog(); // Same Android permission controller denial button, now CAMERA.
  await expect(page.getByLabel('手動取貨碼')).toBeVisible({timeout:15000});
  await page.getByLabel('手動取貨碼').fill(mock.pickup);await page.getByRole('button',{name:'核對取貨碼'}).click();
  await expect(page.getByText('1份 · 成交總價 $50')).toBeVisible();expect(mock.pickupPreviews).toBe(1);expect(mock.pickupConfirms).toBe(0);
  await page.getByRole('button',{name:'確認交付',exact:true}).click({clickCount:2});
  await expect(page.getByRole('button',{name:'尚未確認，重試交付'})).toBeVisible();expect(mock.pickupConfirms).toBe(1);
  await page.getByRole('button',{name:'尚未確認，重試交付'}).click();await expect(page.getByText('交付成功，請掃下一位')).toBeVisible();
  expect(mock.pickupConfirms).toBe(2);expect(mock.confirmKeys[0]).toBe(mock.confirmKeys[1]);
  await expect(page.getByLabel('手動取貨碼')).toBeVisible();
  pass('Native camera denial offers manual fallback; preview does not fulfill; one confirm intent retries same key after lost reply');
  mock.setExpiredPickup();await page.getByLabel('手動取貨碼').fill(mock.pickup);await page.getByRole('button',{name:'核對取貨碼'}).click();await page.getByRole('button',{name:'確認交付',exact:true}).click();
  await expect(page.getByText('預約已逾時，沒有完成交付',{exact:true})).toBeVisible();await expect(page.getByText(/交付成功/)).toHaveCount(0);
  pass('Expired confirm response displays no handover success in Android WebView');


  await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('button',{name:'登出',exact:true}).click();await mock.login('admin');await expect(page.getByRole('link',{name:'管理中心',exact:true})).toHaveAttribute('href','https://api.foodsave.test/admin');await expect(page.getByRole('link',{name:'商家工作台',exact:true})).toHaveCount(0);
  pass('Admin account sees its management link; vendor link absent (fixture, not admin CRUD acceptance)');
  await page.getByRole('button',{name:'切換帳號',exact:true}).click();await mock.login('consumer');
  await nativeInteractionChecks(page,mock);
  await expect(page.getByRole('button',{name:'開始惜食抽獎'})).toBeDisabled();
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(mock.token);
  expect(await page.evaluate(()=>localStorage.getItem('foodsave-demo-v1'))).toBeNull();
  pass('Zero-spin guard, memory-only token and no demo fallback on fixture session');

  // Intercept the native HTTP bridge BEFORE visiting the guest screen. This CI
  // never contacts the real FamilyMart endpoint and does not claim live transport.
  await page.evaluate(()=>{
   const cap=window.Capacitor,original=cap.nativePromise.bind(cap);window.__qaFamilyCalls=0;
   cap.nativePromise=(plugin,method,options)=>{
    if(plugin!=='CapacitorHttp')return original(plugin,method,options);
    if(method!=='post'||options.url!=='https://stamp.family.com.tw/api/maps/MapProductInfo'||options.data.Latitude!==25.0375197||options.data.Longitude!==121.5636704||options.data.ProjectCode!=='202106302'||options.headers.Authorization)throw Error('Unexpected native public-source contract');
    window.__qaFamilyCalls++;
    return Promise.resolve({status:200,headers:{},url:options.url,data:{code:1,data:[{oldPKey:'00123',name:'Android 合成全家',address:'合成契約地址',latitude:25.0375,longitude:121.5636,updateDate:'2026-10-03 19:10:01',info:[{categories:[{qty:999,products:[{code:'0001',name:'Android 合成友善便當',qty:2},{code:'0002',name:'Android 未知數量商品'}]}]}]}]}});
   };
  });
  await page.getByRole('link',{name:'超商資訊',exact:true}).click();await expect(page.getByRole('heading',{name:'超商惜食資訊',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'查詢全家公開區域'}).click();await expect(page.getByRole('heading',{name:'Android 合成全家',exact:true})).toBeVisible();await expect(page.getByText('2份（來源回報）',{exact:true})).toBeVisible();await expect(page.getByText('數量未知',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'顯示公開區域地圖'}).click();await expect(page.getByLabel('附近店家地圖')).toBeVisible();await expect(page.locator('.store-marker')).toContainText('？');
  await expect(page.getByText('折扣以門市結帳為準。')).toBeVisible();await expect(page.getByRole('button',{name:/預約|核銷|取貨/})).toHaveCount(0);
  await page.getByRole('button',{name:'查詢全家公開區域'}).click();expect(await page.evaluate(()=>window.__qaFamilyCalls)).toBe(1);
  await expect(page.getByRole('link',{name:'前往 OPENPOINT 官方 App'})).toHaveAttribute('href','https://play.google.com/store/apps/details?id=tw.net.pic.m.openpoint');
  await page.getByRole('link',{name:'返回自營店家與攤販'}).click();await expect(page.getByRole('heading',{name:'附近的好食物',exact:true})).toBeVisible();
  pass('Guest FamilyMart cards/cache/unknown quantities and 7-ELEVEN official entry; native bridge intercepted, no real source request');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  device('shell','am','force-stop','tw.foodsave.demo');
  try{await browser.close();}catch{}
  device('shell','am','start','-W','-n','tw.foodsave.demo/.MainActivity');
  browser=await attach();const reopened=browser.page;await expect(reopened.getByRole('button',{name:'登入',exact:true})).toBeVisible();
  pass('Native force-stop/relaunch renders login and does not retain bearer session');
 }catch(error){
  // Native process/focus evidence only: no page HTML, credentials or network logs.
  try{console.log('Failure native focus',nativeWindowFocus());}catch{console.log('Native focus unavailable');}
  try{console.log('Failure native exit reasons',device('shell','dumpsys','activity','exit-info','tw.foodsave.demo').split('\n').filter(l=>/reason=|subreason=|status=|importance=|timestamp=|process=|pss=|rss=/.test(l)).slice(-24).join('\n'));}catch{console.log('Native exit info unavailable');}
  try{console.log('Failure native crash markers',device('logcat','-d','-v','brief','AndroidRuntime:E','chromium:E','ActivityManager:I','*:S').split('\n').filter(l=>/FATAL EXCEPTION|Process: tw\.foodsave\.demo|Fatal signal|onRenderProcessGone|Render process|renderer.*crash|Killing .*tw\.foodsave\.demo|Force finishing activity.*tw\.foodsave\.demo/.test(l)).slice(-24).join('\n'));}catch{console.log('Native crash markers unavailable');}
  throw error;
 }finally{try{await browser.close();}catch{console.log('Android connection already closed during cleanup');}}
})().catch(e=>{console.error('FAIL Android fixture:',e.message);process.exitCode=1;});
