// Browser contract test only: login and database responses are explicit mocks.
// Start backend locally on 127.0.0.1:4180 before running this script.
const {chromium}=require('@playwright/test');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:4180/admin');
  if(await page.locator('#workspace').isVisible())throw Error('Workspace visible before login');
  await page.route('**/auth/login',r=>r.fulfill({json:{access_token:require('node:crypto').randomUUID()}}));
  await page.route('**/me',r=>r.fulfill({json:{role:'admin'}}));
  await page.route('**/admin/data/**',r=>r.fulfill({json:{rows:[{id:'fixture-only',name:'<img src=x onerror=alert(1)>',available_quantity:2}],page:1}}));
  await page.getByLabel('電子郵件').fill('admin@example.test');
  await page.getByLabel('密碼',{exact:true}).fill(require('node:crypto').randomUUID());
  await page.getByRole('button',{name:'登入',exact:true}).click();
  await page.locator('#data td').first().waitFor();
  if(await page.locator('#data img').count())throw Error('Untrusted data became markup');
  if(await page.locator('#data td').nth(1).textContent()!=='<img src=x onerror=alert(1)>')throw Error('Missing escaped fixture');
  if(!await page.getByLabel('領取或兌換規則（至少10字）').isVisible())throw Error('Prize terms field missing');
  for(const operation of ['spin-grants','stores','exp-rules','prizes'])await page.locator('#operation').selectOption(operation);
  await page.screenshot({path:'artifacts/admin-mock-contract.png',fullPage:true});
  const ready=await page.request.get('http://127.0.0.1:4180/health/ready');
  if(ready.status()!==503)throw Error('This test expects an unconfigured DB to report not ready');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: admin shell, mocked login/data, escaped markup, all editor forms, missing-DB readiness503; no page errors. NOT a SQL integration test.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
