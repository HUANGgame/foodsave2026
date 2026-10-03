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

## 第二階段：簡化介面及套件（部署前）

已實作三個merchant主入口、商品沿用及收合罕用欄位、庫存±1；consumer預約成功即顯示取貨卡，帶倒數／步行／出示QR與短碼。商家主動按掃碼才要求CAMERA（不要求麥克風），QR在本機解碼；核對時關閉相機，確認成功才進下一位，背景／離頁停止，相機拒絕後保留手動模式而不反覆求權限。按鈕至少44px、無核銷動畫等待。未增加付費或外部掃碼服務。

掃碼採用bundled [ZXing browser](https://github.com/zxing-js/browser) 0.1.5；QR生成採用 [node-qrcode](https://github.com/soldair/node-qrcode) 1.5.4，不從CDN下載、不傳送影像給外部解码站。官方API支持停止掃描；程式另持有stream並停止所有tracks，以處理元件卸載／背景及權限回覆延遲。

驗證：Next靜態建置與TypeScript通過；前端10單元、11 browser fixture tests通過，包括實際QR圖片解碼（合成canvas影像、不是實體相機）、掃碼不核銷、確認連點只一請求、回覆遺失同key重試、成功自動開下一次掃碼、離頁停止tracks、44px確認按鈕、商品沿用及inline庫存防連點。後端再新增異店確認拒絕及核對後逾時不得發EXP兩項測試。新增Android相機拒絕→手動核對→明確確認／同key重試腳本，尚待CI結果，不能先標PASS。

新版runtime／owner ZIP重新打包，見delivery/checksums.json；仍是schema005，不含QA工具、secret或環境設定。只交付可審查部署包，沒有部署或跑新真SQL批次。使用者其後確認營運者HUANG、客服413637629@o365.tku.edu.tw，並批准立即停用登入／30天內清除可識別個資。App及API隱私說明已更新，30天不等於已部署自動清除；業務保存原因／期限、外部副本與備份清除流程仍待完備。新增policy-complete預設false防線，公開註冊保持false，未永久刪除真人資料。

仍待驗：真SQL新preview／confirm與競爭、原生相機允許／真鏡頭解碼、完整真API APK閉環。既有到期release工具需要營運執行通路，不新增自動維運資源；獨立商品保留分鐘、no-show政策／申訴規則未加入新欄位或懲罰。商家領取截止仍可配置，帳號不因一次未取被封。

本輪最新後端91 tests passed（含庫存原子邊界／異店／逾時及政策不完整禁止註冊），1項既有警告。公開非秘密配置見infra/privacy-public-settings.example.json；只有使用者指定客服信箱可公開，不包含實際雲端資源ID。
