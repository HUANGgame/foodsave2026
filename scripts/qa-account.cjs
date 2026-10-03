// Browser contract only: start backend at localhost:4180; all account writes mocked.
const {chromium}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});try{
 const page=await browser.newPage(),errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/account/deletion-*',route=>{calls.push(new URL(route.request().url()).pathname);return route.fulfill({status:calls.at(-1).endsWith('request')?202:200,json:{id:'same-request',state:'requested',account_disabled:true,erasure_completed:false}});});
 await page.goto('http://127.0.0.1:4180/account');await page.getByLabel('電子郵件').fill('member@example.test');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'送出刪除申請',exact:true}).click();if(calls.length)throw Error('Deletion submitted without confirmation');
 await page.getByRole('checkbox').check();await page.getByRole('button',{name:'送出刪除申請',exact:true}).click();await page.getByText(/已受理並停用帳號/).waitFor();if(await page.getByLabel('密碼',{exact:true}).inputValue())throw Error('Password retained after request');
 await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'查詢處理狀態'}).click();await page.waitForFunction(()=>!document.querySelector('button').disabled);if(calls.join(',')!=='/account/deletion-request,/account/deletion-status')throw Error('Unexpected request sequence');if(errors.length)throw Error(errors.join('\n'));
 console.log('PASS: public account page requires confirmation, submits/queries mocked deletion status, clears password, and has no page errors. No SQL writes performed.');
}finally{await browser.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
