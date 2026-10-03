# 食在可惜操作與發布手冊（整合測試版）

目前：65後端本地測試通過；部署端確認真SQL rollback15項、並發3項及精確QA清理；Android extended fixture通過。App→真Azure端到端、實機及完整營運流程仍未完成。本文件不是正式營運已上線證明。

## 模式與設定

- `NEXT_PUBLIC_APP_MODE=demo`：原本本機示範；沒有正式帳號，不送真實訂單。
- `NEXT_PUBLIC_APP_MODE=live`：使用 `NEXT_PUBLIC_API_BASE_URL` 的HTTPS API，沒有localStorage資料替代路徑。網址未配置就顯示設定錯誤；API失敗保留錯誤與重試入口。
- 正式登入token只在記憶體；重開／重載需重新登入。localStorage只保存未確認寫入的UUID與內容hash，沒有密碼或token。登入與資料過期會要求重新登入。
- 發布前填入 `NEXT_PUBLIC_OPERATOR_NAME`、`NEXT_PUBLIC_PRIVACY_CONTACT`、`NEXT_PUBLIC_RETENTION_SUMMARY`。這些缺少時前台不開放新註冊；後端還需 `FOODSAVE_REGISTRATION_ENABLED=true`，預設關閉。

## 消費者

1. 登入；新用戶先閱讀隱私說明、建立consumer帳號。密碼至少12字元。
2. 探索地圖允許定位後依預設1公里篩選，可改3／5公里。拒絕定位時只列出後端可用店家，不假裝已知道本人位置。底圖由OSM載入，步行導航開外部Google Maps。
3. 點店家看照片商品、剩餘數量及評論；評論可返回商品。收藏按鈕由後端確認後更新。
4. 預約1份成功後，到個人中心→我的預約查看取貨碼與截止時間。訂單價格取成交快照；取消由後端返還庫存。核銷需商家帳號及正確取貨碼。
5. 完成領取後可評分／評論。重複評論由後端拒絕；EXP按已啟用的管理設定計算，不沿用demo固定分數。
6. 惜食任務顯示EXP與可用抽獎次數。按轉盤先等待後端確認，再呈現3.2秒減速；reduced motion立即顯示結果。動畫不決定獎項。零次數不能新抽；已有未確認操作則可「確認上次結果」。
7. 斷線或逾時不要清除App資料；再次按同一操作沿用原識別碼。離開轉盤再返回可讀回獲獎紀錄；兌換碼、規則與期限來自後端。沒有真實配置獎品時不偽造中獎。未量測Android FPS。

## 商家

由受控CLI建立vendor帳號，管理員將店家分配給该帳號。登入→個人中心→商家工作台；上架需商品名稱、已授權HTTPS照片、原價／惜食價、可預約庫存及截止時間。

金額輸入為元，API存最小貨幣單位。商品編輯送revision；庫存已因其他訂單改變時409，重新載入後再編輯。修改不追改既有訂單快照。下方店家預約輸入12位取貨碼核銷；只能操作自己店家，逾期回傳expired而非完成。

## 管理員與DB查看

`API_BASE/admin`登入管理帳號；側欄切換白名單表、分頁、重新載入；右側新增店家／獎品／手動次數／EXP。手動次數source_key須以`manual:`開頭且唯一。最多同時開放6個未到期獎項，店家券為8折；需真實庫存、規則與有效期，不能用示例券冒充。

週排名預設3／2／1次，以 `/admin/ranking-rules` API配置；目前沒有對應圖形編輯表單。週結算／expire命令見backend README。DB查看經獨立viewer連線及欄位白名單，不接受SQL；角色建立與grant尚待批准及實測。runtime包含管理入口，但完整管理CRUD與viewer連線尚未驗收；實際URL僅經核准的私有交接提供。

## 帳號刪除與隱私

個人中心→申請刪除帳號→再次輸入密碼並勾選確認。回202表示受理、立即停用帳號／撤銷session；商家商品同時關閉。受理時會在同一交易內取消本人仍待領取的預約並返還庫存；真SQL競爭情境尚未驗證。**不是已抹除所有資料**；最終資料清除、備份清除與法定保存需營運者批准政策與執行流程。

`/privacy/`可未登入查看資料類別、地圖／圖片來源及App內外刪除路徑。實際營運者、聯絡管道、保存天數、處理地區及公開URL仍待填；沒有這些條件不能宣稱符合商店公開發布要求。

## 發布與檔案驗證

Android compile/target36、min23、AGP8.9.2、Gradle8.11.1、JDK21。release明確debuggable=false、不接debug簽章，未簽署AAB由使用者以自有upload key處理。manifest禁止cleartext與backup。正式package ID待使用者確定，測試仍是tw.foodsave.demo，versionCode3／0.2.0-integration。

從repository根目錄，設定實際營運變數後：

```bash
npm run build:release
npx cap sync android
# 進入android後，foodsaveApplicationId須與FOODSAVE_APPLICATION_ID一致。
./gradlew :app:bundleRelease -PfoodsaveApplicationId=YOUR_APPROVED_PACKAGE_ID
```

`build:release`拒絕缺欄位、demo模式、.test／localhost API與demo package ID；這只是欄位檢查，不能代替健康／權限／隱私內容審核。Gradle仍可單獨build測試產物，交付前必須按上述流程重建並檢查嵌入網址。

本輪編譯驗證用了 `api.foodsave.test` 和隱私fixture，因此產物只留作本地驗證，不是可連真服務的最終APK/AAB，不上傳Library覆蓋舊交付。最新Android CI另有實際安裝／啟動與fixture互動證據，但仍未串真API；詳見ANDROID_CI.md。

## 最後整包交付仍待

App串真API及服務／DB重啟驗收、管理員與viewer身分、公開HTTPS、真獎品與營運政策、完整刪除處理、實機安裝／定位／返回／轉盤順暢度。確認後重建並交付管理站、APK/AAB、受保護DB查看連結、關係圖及本手冊。不得將代理三角色稱為三真人。

## 刪除申請恢復入口

後端 `/account` 提供App外的刪除申請與查詢，用原帳密驗證，不需既有session。回覆遺失可重送；既有申請不重建、不再返還庫存。`/privacy`顯示營運者配置或draft。最終抹除仍未完成，詳見SECURITY_REVIEW.md，不能把requested當completed。

下一階段最小測試、兩組待確認輸入與交付限制見 [LIVE_APP_ACCEPTANCE.md](LIVE_APP_ACCEPTANCE.md)。維持註冊關閉、runtime權限及部署包不變。

## 簡化取貨與最新隱私增量（尚未部署驗收）

商家主頁三入口為快速上架／掃碼取貨／今日訂單；常用商品沿用資料，調整數量、惜食價及截止；inline ±1由後端原子更新。掃碼只核對，唯一「確認交付」才核銷；失敗顯示未確認並沿用原識別碼重試。相機拒絕後用手動碼，仍先核對再確認。舊直接手動核銷API保留相容性，新App不使用；完整變更及驗證範圍見PICKUP_INCREMENT.md。

營運者HUANG、客服413637629@o365.tku.edu.tw；批准立即停用登入及30天內清除可識別個資。這是處理期限，不是已啟用自動清除。必要業務紀錄保存原因／期限與備份流程待定，FOODSAVE_PRIVACY_POLICY_COMPLETE及NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE保持false，FOODSAVE_REGISTRATION_ENABLED保持false。不要自行執行真人永久刪除；owner清除政策所需其他期限不可憑空補值。
