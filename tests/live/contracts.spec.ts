import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
const sessionFixture=randomUUID(),passwordFixture=randomUUID();
const productId='11111111-1111-1111-1111-111111111111',userId='22222222-2222-2222-2222-222222222222';
async function fixture(page:Page,{drop=false,spins=1,role='consumer'}={}){
 let draws=0,requests=0,stock=1,order:any=null,deleted=false;const keys:string[]=[];
 const prize={id:'p2',name:'測試用8折券',kind:'coupon',terms:'此為mock契約測試，沒有真實兌換價值',expires_at:'2027-01-01T00:00:00',discount_percent:20};
 const segments=Array.from({length:6},(_,i)=>({id:`p${i}`,name:i===2?prize.name:`測試獎品${i}`}));
 const couponCode=randomUUID();
 const completed={id:'draw-one',prize,segments,coupon_code:couponCode};
 await page.route('https://api.foodsave.test/**',async route=>{const req=route.request(),path=new URL(req.url()).pathname,method=req.method();const json=(body:unknown,status=200)=>route.fulfill({status,json:body});
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  if(path==='/auth/login')return json({access_token:sessionFixture});
  if(path==='/auth/register')return json({id:userId,role:'consumer'},201);
  if(path==='/auth/logout')return json({logged_out:true});
  if(path==='/me')return deleted?json({detail:'請重新登入'},401):json({id:userId,email:'test@example.test',role,exp:0,spins:spins-draws});
  if(path==='/products')return json([{id:productId,store_id:'33333333-3333-3333-3333-333333333333',store_name:'測試店家',name:'真API契約測試商品',photo_url:'https://images.example.test/food.jpg',latitude:25.033,longitude:121.541,original_price_minor:10000,sale_price_minor:5000,source:'foodsave',service_mode:'reservation',available_quantity:stock,pickup_deadline:'2027-01-01T00:00:00',revision:1}]);
  if(path==='/favorites')return json([]);
  if(path.startsWith('/stores/'))return json({average:4.5,count:2,items:[{rating:5,body:'mock評論'}]});
  if(path==='/reservations'&&method==='GET')return json(order?[order]:[]);
  if(path==='/reservations'&&method==='POST'){stock=0;order={id:'order1',state:'waiting',product_id:productId,quantity:1,snapshot:JSON.stringify({name:'真API契約測試商品',sale_price_minor:5000}),pickup_code:'ABCDEF123456',expires_at:'2027-01-01T00:00:00'};return json(order,201);}
  if(path==='/reservations/order1/cancel'){stock=1;order.state='cancelled';return json({id:'order1',state:'cancelled'});}
  if(path==='/prizes')return json(segments);
  if(path==='/draws'&&method==='GET')return json(draws?[{id:'draw-one',prize_snapshot:JSON.stringify(prize),coupon_code:completed.coupon_code}]:[]);
  if(path==='/draws'&&method==='POST'){requests++;keys.push(req.headers()['idempotency-key']);if(!draws)draws++;if(drop&&requests===1)return route.abort('failed');return json(completed,201);}
  if(path==='/account/deletion-requests'){deleted=true;return json({state:'requested',account_disabled:true,erasure_completed:false},202);}
  return json({detail:`Unexpected mock route ${method} ${path}`},500);
 });
 await page.route('https://images.example.test/**',r=>r.abort());
 return {keys,couponCode,get draws(){return draws;},get requests(){return requests;},get stock(){return stock;},get deleted(){return deleted;}};
}
async function login(page:Page){await page.getByLabel('電子郵件').fill('test@example.test');await page.getByLabel('密碼（至少12字元）').fill(passwordFixture);await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('button',{name:'登入',exact:true})).toHaveCount(0);}

test('live mode reserves/cancels via API and never stores a session token',async({page})=>{
 const mock=await fixture(page);await page.goto('/');await login(page);await page.getByRole('button',{name:'預約1份'}).click();await expect(page.getByText('預約成功，請到我的預約查看取貨碼。')).toBeVisible();expect(mock.stock).toBe(0);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'我的預約',exact:true}).click();await page.getByRole('button',{name:'出示取貨碼'}).click();await expect(page.getByText('ABCDEF123456')).toBeVisible();await page.getByRole('button',{name:'取消預約',exact:true}).click();await expect(page.getByText('已取消',{exact:true})).toBeVisible();expect(mock.stock).toBe(1);
 expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(sessionFixture);
 expect(await page.evaluate(()=>localStorage.getItem('foodsave-demo-v1'))).toBeNull();await page.reload();await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
});

test('wheel retries committed-but-lost response with same key and one deduction',async({page})=>{
 const mock=await fixture(page,{drop:true});await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/missions/');await login(page);
 await page.getByRole('button',{name:'開始惜食抽獎'}).click();await expect(page.getByText(/連線未完成/)).toBeVisible();
 await page.getByRole('button',{name:'確認上次結果'}).click();await expect(page.getByRole('heading',{name:'獲得 測試用8折券'})).toBeVisible();await expect(page.getByText(/連線未完成/)).toHaveCount(0);expect(mock.requests).toBe(2);expect(mock.draws).toBe(1);expect(mock.keys[0]).toBe(mock.keys[1]);
 await expect(page.locator('.prize-wheel')).toHaveCSS('transform',/matrix/);expect(await page.locator('.prize-wheel').evaluate(el=>el.getAnimations().length)).toBe(0);
 const landing=await page.locator('.prize-wheel').evaluate(el=>{const m=new DOMMatrix(getComputedStyle(el).transform);return (Math.atan2(m.b,m.a)*180/Math.PI+360)%360;});expect(landing).toBeCloseTo(210,2);
 await page.screenshot({path:'artifacts/live-wheel-mock.png',fullPage:true});
});

test('wheel close/reopen recovers result; zero chances disables new draw',async({page})=>{
 const mock=await fixture(page);await page.goto('/missions/');await login(page);await page.getByRole('button',{name:'開始惜食抽獎'}).click({clickCount:2});await expect.poll(()=>mock.requests).toBe(1);
 await page.getByRole('link',{name:'個人中心',exact:true}).click();await page.getByRole('link',{name:'惜食任務',exact:true}).click();await expect(page.getByText(mock.couponCode,{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'開始惜食抽獎'})).toBeDisabled();expect(mock.draws).toBe(1);
});

test('failed API login never falls back to a demo account',async({page})=>{
 await page.route('https://api.foodsave.test/**',r=>r.fulfill({status:503,json:{detail:'SQL service unavailable'}}));await page.goto('/');await page.getByLabel('電子郵件').fill('test@example.test');await page.getByLabel('密碼（至少12字元）').fill(passwordFixture);await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByText('SQL service unavailable')).toBeVisible();await expect(page.getByRole('button',{name:'預約1份'})).toHaveCount(0);expect(await page.evaluate(()=>localStorage.getItem('foodsave-demo-v1'))).toBeNull();
});

test('incomplete policy keeps registration closed; deletion is still only a request',async({page})=>{
 const mock=await fixture(page);await page.goto('/profile/');await page.getByRole('button',{name:'第一次使用？建立帳號'}).click();await page.getByLabel('電子郵件').fill('new@example.test');await page.getByLabel('密碼（至少12字元）').fill(passwordFixture);await page.getByRole('checkbox').check();await expect(page.getByRole('button',{name:'建立帳號',exact:true})).toBeDisabled();await page.getByRole('button',{name:'已有帳號？登入'}).click();await page.getByRole('button',{name:'登入',exact:true}).click();await page.getByRole('button',{name:'申請刪除帳號',exact:true}).click();await page.getByLabel('再次輸入密碼').fill(passwordFixture);await page.getByRole('checkbox').check();await page.getByRole('button',{name:'確認送出刪除申請'}).click();await expect(page.getByText(/尚未完成抹除/)).toBeVisible();expect(mock.deleted).toBe(true);await expect(page.getByRole('button',{name:'登入',exact:true})).toBeVisible();
});

test('vendor API form loads after login and sends matching product contract',async({page})=>{
 await fixture(page,{role:'vendor'});const store='33333333-3333-3333-3333-333333333333';let submitted:any=null;
 await page.route('https://api.foodsave.test/vendor/catalog',r=>r.fulfill({json:{stores:[{id:store,name:'測試商家',service_mode:'reservation'}],products:[]}}));
 await page.route('https://api.foodsave.test/vendor/reservations',r=>r.fulfill({json:[]}));
 await page.route('https://api.foodsave.test/vendor/products',r=>{submitted=r.request().postDataJSON();return r.fulfill({status:201,json:{id:productId,revision:1}});});
 await page.goto('/vendor/');await login(page);await page.getByRole('button',{name:'快速上架',exact:true}).click();await page.getByLabel('商品名稱',{exact:true}).fill('測試便當');await page.getByLabel('已授權商品照片網址').fill('https://images.example.test/food.jpg');await page.getByLabel('原價（元）').fill('100');await page.getByLabel('惜食價（元）').fill('50');await page.getByLabel('剩餘數量').fill('2');await page.getByLabel('領取截止').fill('2027-01-01T12:00');await page.getByRole('button',{name:'儲存商品'}).click();await expect(page.getByText('商品已儲存')).toBeVisible();expect(submitted).toMatchObject({store_id:store,original_price_minor:10000,sale_price_minor:5000,available_quantity:2,active:true,revision:1});expect(submitted.pickup_deadline).toMatch(/Z$/);
});

for(const code of [1,2,3])test(`GPS error ${code} keeps actual API list and review return works`,async({page})=>{
 await page.addInitScript(code=>{Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(_ok:unknown,fail:(v:unknown)=>void)=>fail({code})}});},code);
 await fixture(page);await page.goto('/');await login(page);
 await page.getByRole('button',{name:'使用目前位置'}).click();
 await expect(page.getByText(code===1?/未允許定位/:code===3?/定位逾時/:/目前無法取得位置/)).toBeVisible();
 await expect(page.getByRole('heading',{name:'真API契約測試商品'})).toBeVisible();
 await page.getByRole('button',{name:/則評論/}).click();await expect(page.getByText('mock評論',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'返回商品'}).click();await expect(page.getByRole('heading',{name:'真API契約測試商品'})).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('foodsave-demo-v1'))).toBeNull();
});
