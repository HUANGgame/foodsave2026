import {test,expect} from '@playwright/test';
import QRCode from 'qrcode';
import {randomBytes,randomUUID} from 'node:crypto';
const credential='FS1.'+randomBytes(32).toString('base64url');
const reviewToken=randomBytes(32).toString('base64url');
const password=randomUUID();
async function setup(page:any,drop=false){let previews=0,confirmations=0,stockCalls=0;const keys:string[]=[];
 await page.route('https://api.foodsave.test/**',async(route:any)=>{const req=route.request(),path=new URL(req.url()).pathname;const json=(body:any,status=200)=>route.fulfill({json:body,status});
  if(req.method()==='OPTIONS')return route.fulfill({status:204});
  if(path==='/auth/login')return json({access_token:randomUUID()});
  if(path==='/me')return json({id:'vendor',email:'vendor@example.test',role:'vendor',exp:0,spins:0});
  if(path==='/vendor/catalog')return json({stores:[{id:'s',name:'QA store'}],products:[{id:'p',store_id:'s',name:'QA meal',photo_url:'https://images.example.test/meal.png',original_price_minor:10000,sale_price_minor:5000,available_quantity:2+stockCalls,pickup_deadline:'2027-01-01T12:00:00',revision:1,active:true}]});
  if(['/products','/favorites','/reservations','/vendor/reservations'].includes(path))return json([]);
  if(path==='/vendor/pickups/preview'){previews++;expect(req.postDataJSON().credential).toBe(credential);return json({id:'order',name:'QA meal',quantity:1,total_price_minor:5000,review_token:reviewToken,review_expires_at:'2027-01-01T12:00:00'});}
  if(path==='/vendor/pickups/confirm'){confirmations++;keys.push(req.headers()['idempotency-key']);expect(req.postDataJSON().review_token).toBe(reviewToken);await new Promise(r=>setTimeout(r,350));if(drop&&confirmations===1)return route.abort();return json({id:'order',state:'completed'});}
  if(path==='/vendor/products/p/stock'){stockCalls++;await new Promise(r=>setTimeout(r,250));return json({id:'p',available_quantity:2+stockCalls,revision:2});}
  return json({detail:'Unexpected fixture route'},500);
 });
 const qr=await QRCode.toDataURL(credential,{width:400,margin:4});
 await page.addInitScript(({qr}:any)=>{const state={starts:0,stops:0};(window as any).__camera=state;
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async(constraints:any)=>{if(constraints.audio!==false)throw Error('audio forbidden');state.starts++;
   const canvas=document.createElement('canvas');canvas.width=canvas.height=500;const ctx=canvas.getContext('2d')!;ctx.fillStyle='#fff';ctx.fillRect(0,0,500,500);
   if(state.starts===1){const img=new Image();img.src=qr;await img.decode();ctx.drawImage(img,50,50,400,400);}
   const stream=canvas.captureStream(10);for(const track of stream.getTracks()){const stop=track.stop.bind(track);track.stop=()=>{state.stops++;stop();};}return stream;
  }});
 },{qr});
 await page.goto('/vendor/');await page.getByLabel('電子郵件').fill('vendor@example.test');await page.getByLabel('密碼（至少12字元）').fill(password);await page.getByRole('button',{name:'登入',exact:true}).click();await expect(page.getByRole('heading',{name:'商家工作台'})).toBeVisible();
 return {keys,get previews(){return previews;},get confirmations(){return confirmations;},get stockCalls(){return stockCalls;}};
}

test('QR scan only previews; one explicit handover; lost response retries same key and resumes scanning',async({page})=>{
 const state=await setup(page,true);await expect(page.getByRole('navigation',{name:'商家主要操作'}).getByRole('button')).toHaveCount(3);
 expect(await page.evaluate(()=>(window as any).__camera.starts)).toBe(0);
 await page.getByRole('button',{name:'掃碼取貨',exact:true}).click(); // first primary tap
 await expect(page.getByText('1份 · 成交總價 $50')).toBeVisible();expect(state.previews).toBe(1);expect(state.confirmations).toBe(0);
 await expect.poll(()=>page.evaluate(()=>(window as any).__camera.stops)).toBeGreaterThan(0);
 const confirm=page.getByRole('button',{name:'確認交付',exact:true});expect((await confirm.boundingBox())!.height).toBeGreaterThanOrEqual(44);
 await confirm.click({clickCount:2}); // single intent despite double click
 await expect(page.getByRole('button',{name:'尚未確認，重試交付'})).toBeVisible();expect(state.confirmations).toBe(1);
 await page.getByRole('button',{name:'尚未確認，重試交付'}).click();await expect(page.getByText('交付成功，請掃下一位')).toBeVisible();expect(state.confirmations).toBe(2);expect(state.keys[0]).toBe(state.keys[1]);
 await expect.poll(()=>page.evaluate(()=>(window as any).__camera.starts)).toBe(2);
 expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(reviewToken);
 await page.getByRole('button',{name:'今日訂單',exact:true}).click();await expect(page.getByLabel('取貨碼掃描相機')).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>(window as any).__camera.stops)).toBeGreaterThan(1);
});

test('merchant inline stock double click is one intent; reuse keeps rare fields collapsed',async({page})=>{
 const state=await setup(page);await page.getByRole('button',{name:'增加 QA meal 庫存'}).click({clickCount:2});await expect(page.getByText('剩餘 3 份 · $50')).toBeVisible();expect(state.stockCalls).toBe(1);
 await page.getByRole('button',{name:'沿用商品／調價期限'}).click();await expect(page.getByLabel('惜食價（元）')).toHaveValue('50');await expect(page.getByLabel('可預約庫存')).toHaveValue('3');await expect(page.getByLabel('商品名稱',{exact:true})).not.toBeVisible();expect(await page.evaluate(()=>(window as any).__camera.starts)).toBe(0);
});
