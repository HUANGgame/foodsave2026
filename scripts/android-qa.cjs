const { chromium } = require('playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const adb='/workspace/android-sdk/platform-tools/adb';
function device(...args){return execFileSync(adb,['-s','emulator-5554',...args],{timeout:60000,encoding:'utf8'}).trim()}
async function attach(){const pid=device('shell','pidof','tw.foodsave.demo');device('forward','tcp:9222','localabstract:webview_devtools_remote_'+pid);for(let i=0;i<15;i++){try{return await chromium.connectOverCDP('http://127.0.0.1:9222',{timeout:10000})}catch(e){await new Promise(r=>setTimeout(r,1000));}}throw Error('Cannot attach Android WebView');}
(async()=>{
 const b=await attach();const p=b.contexts()[0].pages()[0];p.setDefaultTimeout(45000);
 const log=[];const check=async(text,fn)=>{await fn();log.push(text);fs.writeFileSync('artifacts/android-qa-results.json',JSON.stringify(log,null,2));console.log('PASS',text)};
 await p.waitForSelector('.brand');
 await check('Android APK starts and renders brand',async()=>{if(!(await p.locator('.brand').innerText()).includes('食在可惜'))throw Error('No brand')});
 await p.getByRole('button',{name:'第一次使用？看 3 個小步驟'}).click();await p.getByRole('button',{name:'開始探索好食物'}).click();
 await p.getByRole('button',{name:'收藏店家',exact:true}).click();await p.getByRole('button',{name:'預約 1 份',exact:true}).first().click();
 await p.getByRole('link',{name:'個人中心',exact:true}).click();await p.getByRole('link',{name:'我的預約'}).click();await p.getByText('100001',{exact:true}).waitFor();
 await p.getByRole('button',{name:'取消預約'}).click();await check('Consumer cancels reservation on Android',async()=>{await p.getByText('已取消',{exact:true}).waitFor()});
 await p.getByRole('link',{name:'個人中心',exact:true}).click();await p.getByRole('link',{name:'示範商家核銷',exact:true}).click();await p.getByLabel('商品名稱',{exact:true}).fill('Android驗收便當');await p.getByLabel('可再預約數量',{exact:true}).fill('2');await p.getByRole('button',{name:'確認上架',exact:true}).click();await p.getByRole('button',{name:'編輯 Android驗收便當',exact:true}).waitFor();
 await check('Vendor creates listing on Android',async()=>{});
 await p.getByRole('button',{name:'編輯 Android驗收便當',exact:true}).click();await p.getByLabel('可再預約數量',{exact:true}).fill('3');await p.getByRole('button',{name:'儲存商品變更'}).click();
 await p.getByRole('link',{name:'探索地圖',exact:true}).click();const card=p.locator('.product').filter({has:p.getByRole('heading',{name:'Android驗收便當',exact:true})});await card.getByText('剩餘 3 份').waitFor();await card.getByRole('button',{name:'預約 1 份'}).click();
 await check('Vendor edited stock visible to consumer in same APK',async()=>{});
 await p.getByRole('link',{name:'個人中心',exact:true}).click();await p.getByRole('link',{name:'我的預約'}).click();await p.getByText('100002',{exact:true}).waitFor();await p.getByRole('link',{name:'示範商家核銷',exact:true}).click();await p.getByLabel('輸入 6 位示範取貨碼').fill('999999');await p.getByRole('button',{name:'確認示範領取'}).click();await p.getByRole('status').filter({hasText:'找不到'}).waitFor();
 await p.getByLabel('輸入 6 位示範取貨碼').fill('100002');await p.getByRole('button',{name:'確認示範領取'}).click();await p.getByRole('status').filter({hasText:'核銷成功'}).waitFor();await check('Invalid code rejected, valid code completes pickup on Android',async()=>{});
 await p.getByRole('link',{name:'查看預約與領取紀錄'}).click();await p.getByLabel('評論內容').fill('Android模擬器取貨驗收完成');await p.getByRole('button',{name:'送出評論'}).click();await p.getByRole('link',{name:'惜食任務',exact:true}).click();await p.getByText('230 EXP',{exact:true}).waitFor();await check('Consumer review and 230 EXP consistent on Android',async()=>{});
 await p.screenshot({path:'artifacts/android-missions-webview.png'});
 await check('Product owner validates disabled lottery, no horizontal overflow',async()=>{if(!(await p.getByRole('button',{name:'尚未開放抽獎'}).isDisabled()))throw Error('Lottery active');if(!(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)))throw Error('Horizontal overflow');});
 device('shell','am','force-stop','tw.foodsave.demo');device('shell','am','start','-n','tw.foodsave.demo/.MainActivity');
 const b2=await attach();const p2=b2.contexts()[0].pages()[0];p2.setDefaultTimeout(45000);await p2.getByRole('link',{name:'惜食任務',exact:true}).click();await p2.getByText('230 EXP',{exact:true}).waitFor();log.push('Android force-stop and relaunch preserves 230 EXP and stored state');fs.writeFileSync('artifacts/android-qa-results.json',JSON.stringify(log,null,2));console.log('PASS Android force-stop/relaunch persistence');
 await p2.screenshot({path:'artifacts/android-relaunch-webview.png'});
 await b2.close();try{await b.close()}catch{};
})().catch(e=>{console.error(e);process.exitCode=1});
