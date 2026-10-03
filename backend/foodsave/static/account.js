'use strict';
const form=document.getElementById('account-form'),status=document.getElementById('status');
let busy=false;
fetch('/privacy',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(p=>{document.getElementById('privacy').textContent=p.status==='configured'?`營運者：${p.operator}。聯絡：${p.contact}。保存說明：${p.retention}`:`已定案測試政策，啟用檢查尚未完成。營運者：${p.operator}。聯絡：${p.contact}。保存說明：${p.retention}`;}).catch(()=>{document.getElementById('privacy').textContent='說明暫時無法載入，請稍後重試。';});
form.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;const action=event.submitter.value,fields=new FormData(form);if(action==='submit'&&!form.elements.confirm.checked){status.textContent='請先勾選確認刪除申請。';return;}
 busy=true;for(const button of form.querySelectorAll('button'))button.disabled=true;
 const body={email:String(fields.get('email')),password:String(fields.get('password'))};if(action==='submit')body.confirm='DELETE';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{const response=await fetch(action==='submit'?'/account/deletion-request':'/account/deletion-status',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',signal:controller.signal,body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.detail||'操作未完成');status.textContent=data.state==='not_requested'?'目前沒有刪除申請。':data.erasure_completed?'系統記錄此申請已完成處理；保存例外請參閱營運政策。':'已受理並停用帳號，資料清除尚未完成。重複送出會取回原申請，不會新增另一筆。';}
 catch(error){status.textContent=error.name==='AbortError'?'回覆逾時，請使用查詢按鈕確認是否已受理。':error.message||'無法確認結果，請稍後查詢。';}
 finally{clearTimeout(timer);form.elements.password.value='';busy=false;for(const button of form.querySelectorAll('button'))button.disabled=false;}
});
