# 簡化取貨增量：分階段驗證，尚未完整交付

使用者批准consumer一鍵保留、出示碼；merchant掃碼核對→一次確認交付，強調少操作。先前真SQL18項及Android fixture通過是舊版證據，不能沿用為本增量PASS。

## 第一階段：後端可驗

- 新預約回傳256-bit隨機opaque QR字串，不含姓名電話；沿用既有request_results JSON保存與本人預約歷史讀取，不新增DDL／grant／service secrets。
- POST /vendor/pickups/preview接受QR或12字元手動碼，驗證店家、狀態與期限，只返回品名／數量／成交價及短效review token，不核銷。
- POST /vendor/pickups/confirm接受preview的request key及review token；同vendor、2分鐘內且不超過訂單期限才可繼續。再鎖產品／訂單，重新驗歸屬／期限／狀態，走既有一次性核銷及EXP路徑；同idempotency key重試返回原結果。
- 舊manual complete API暫保留相容性；新UI必須先preview再confirm，QR不得交給舊路徑自動核銷。
- 同consumer相同商品未過期waiting訂單禁止用新key重複占單；掃碼及預約有帳號級短期限流，手動猜碼沿用較嚴格限制。no-show不實施懲罚、不永久封號。
- 庫存±1新增原子bounded update及冪等結果，驗證店家所有權。
- 商家領取期限沿用既有商品pickup_deadline；原有最多30分鐘保留及到期釋放工具仍在，未新建排程或聲稱自動維運已部署。

本地84 tests passed（包含19項新增契約／安全控制流測試），1項既有Starlette警告。新增測試是double，未連真SQL；新QR未經真相機或Android驗收。runtime部署包暫不覆寫、未部署新API，schema仍005。

## 下一階段與驗收

merchant首頁僅快速上架／掃碼取貨／今日訂單三主入口；商品重用／少量欄位、inline庫存±1，罕用欄位收合。掃碼後只一次大按鈕確認，成功後接下一位，失敗保留未確認狀態及原key重試；busy時擋連點。consumer成功後就顯示倒數、步行入口、大按鈕取貨碼。

新增驗收：掃碼不交付、異店／過期／已領拒絕、review token綁定及過期、確認與取消競爭、回覆遺失同key僅一次EXP、低庫存雙操作、相機拒絕／離頁／背景關閉、QR圖片解碼、無PII／相機資料不上傳、merchant tap count（進掃碼1下＋确认1下，連續下一位只需確認1下）、手動fallback與busy擋重複請求、44px以上與減少動畫。新真SQL批次及部署仍需獨立範圍確認，不重用已清理的manifest。
