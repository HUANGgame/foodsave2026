# FoodSave 公開測試版隱私與刪除說明（已定案，啟用驗證另計）

使用者已確認由HUANG負責人工追蹤，grace_days=0、business_retention_days=0、receipt_days=30，立即停用、30天內人工清除。聯絡：413637629@o365.tku.edu.tw。這是低流量測試政策，不是法律認證或商店上架保證。

App與公開 `/privacy-policy` 同讀 `backend/foodsave/static/privacy-policy.json`；`/privacy` 回傳同一政策。owner參數見 `infra/erasure-policy-approved-test.json`，enabled=false僅防止誤執行真刪除，不表示政策未核准。

## 帳號與寄信

email、密碼雜湊及登入會話用於帳號驗證；密碼使用加鹽scrypt雜湊，不保存可還原密碼。登入憑證只留App記憶體。重設或改密碼成功會撤銷原有登入。請自行在App設定密碼，不在聊天提供密碼或驗證碼。

驗證郵件使用Microsoft Azure Communication Services，供應商處理收件地址、郵件內容及傳送所需資訊；寄信資源資料位置為AsiaPacific，互動追蹤已關閉。平台內部投遞／安全／服務紀錄的保存期限未由目前設定揭露，不代表供應商不保留紀錄。

## 驗證碼與安全計數

一次性碼15分鐘有效，資料庫保存碼與email衍生的雜湊及期限；再次寄信使舊碼失效。失效不等於立即物理刪除。系統於新請求有限量補清舊過期資料，營運者也以人工工具有限量補清；目前沒有自動清除排程。

防濫用限流使用email／帳號／共用入口衍生識別與計數；雜湊不代表不可關聯。刪帳不重設尚有效的安全計數，營運者待窗口結束後按原申請補清該email識別。共用全站成本配額及已核准單次寄信測試防重控制不因刪帳清零，不把處理中的安全紀錄誤稱已完全清除。

## 既有服務資料

預約、收藏、評論、EXP與獎勵紀錄用於服務及避免重複發放；操作紀錄用於管理與問題追查。未整合廣告、付款或推播SDK。裝置只保留未完成操作的隨機識別碼與內容雜湊；照片HTTPS來源可能接收IP與請求資訊。

## 定位、相機與外部服務

定位需授權，用於裝置上的附近篩選，不把定位歷程寫入FoodSave資料庫。商家點選掃碼取貨才請求相機；影像只在裝置解碼，不上傳保存、不錄音，核對、離頁或切到背景即停止相機。隨機取貨憑證送後端核對，不含姓名電話。

全家手動查詢傳送所選公開地區中心座標；附近查詢須另行同意將裝置座標傳給全家，再請求系統定位權限。取消或拒絕可手選；附近位置與結果僅留本頁記憶體，離頁清除，不寫FoodSave資料庫或裝置儲存、不傳FoodSave登入憑證。公開門市／商品按地區在裝置快取30分鐘，失敗不代表零庫存。來源可能收到一般連線資訊。開地圖會向OpenStreetMap底圖連線，步行導航連Google Maps；7-ELEVEN庫存整合尚未完成。

## 刪除與人工責任

刪帳受理後立即停用並撤銷登入，由HUANG追蹤並於30天內人工完成清除；訂單與通知處理完後不額外保留業務資料，清除處理紀錄保留30天。SQL備份依現有7天週期到期，寄信供應商內部紀錄期限未由目前設定揭露。

在個人中心申請刪帳並確認密碼，或使用公開帳號刪除頁；無法操作時聯絡HUANG完成身分核對。受理不等於全部清除。HUANG負責追蹤請求、執行既有兩階段清除與到期補清，不宣稱有自動排程。

處理商家刪帳與過期訂單時，先完成既有顧客通知及訂單處理；不新增業務保留需求。清理包括帳號驗證資料、本人challenge與已過期限流識別，不以刪帳重設全站配額。清除紀錄僅證明應用資料庫範圍，不代表供應商／備份副本同時清除。

## 備份與日誌

部署端已確認SQL短期備份保存7天、差異備份間隔12小時，未設定每週／每月／每年長期保留備份；不可變備份未啟用。刪除營運資料不會立刻移除既存備份，依備份生命週期到期。若復原備份，HUANG須先重新套用已受理的停用／刪除結果，再提供服務。

App Service應用與HTTP檔案／blob日誌、詳細錯誤及失敗追蹤未啟用；App與ACS未設定Azure Monitor診斷匯出目的地。這不等於平台完全無紀錄；HTTP保留天數為null也不是0天保證。寄信服務內部紀錄期限未知，依Microsoft適用資料處理說明。

## 測試範圍

本政策已由HUANG定案，適用低流量公開測試，不代表正式商店上架或所有功能已全面驗收。註冊可用性以App向後端即時查詢為準；真實驗信、登入與重設仍由使用者本人完成。寄信量與服務可用性受全站配額及限時授權影響。

## 本輪開啟條件

1. Azure以固定tracked QA完成合成資料rollback且三表零殘留；不以本機fake測試代替。
2. 部署本輪固定runtime包，核對公開`/privacy-policy`與`/privacy`版本、HUANG/contact/retention內容；既有FOODSAVE_RETENTION_SUMMARY若仍是舊文案，需同步成canonical summary。
3. 沿用已批准MI、配額與共用入口限流設定，保持Azure Students spending limit；USD1提醒不是硬上限。
4. 由部署端於實際啟用時設定FOODSAVE_MAIL_AUTHORIZED_UNTIL為明確UTC時間，距設定時刻不超過24小時；保留既有MAIL_APPROVED及已核對ACS設定。不可直接複用過期deadline。到期會拒絕新的郵件送出，不會自動把功能旗標改為false、不撤銷已發碼；既有登入／改密碼不因寄信deadline自動停用，已發驗證碼仍按原15分鐘期限失效。
5. 在上述驗證完成後，按既有授權核對並開啟FOODSAVE_PRIVACY_POLICY_COMPLETE、FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED及FOODSAVE_REGISTRATION_ENABLED；回讀`/auth/options`確認可用。私人APK已採live模式，依即時後端判定；不需要把APK編譯時privacyReady當作新的開放程序。
6. 使用者本人在私人APK完成註冊驗信、登入及重設；未完成前不宣稱真實端到端驗收。

本輪不建立排程、不真刪除、不修改備份或grant、不自行翻線上開關。

### 部署端已回報的實證

Azure worker於2026-10-03 17:40:03 UTC以4951b295固定QA完成真SQL合成資料rollback：19 checks PASS、errors=[]、exit0；三個獨立連線查本批users/account_challenges/rate_limits均為0，manifest0600、私有目錄0700。涵蓋本人email/UUID範圍、900秒過期、安全有效計數保留與savepoint；沒有執行真人清除。此為部署端回報，不是本機重跑或真人刪除／完整端到端證據。

非秘密範本 `infra/privacy-public-settings.example.json` 的後端與前端摘要均同步canonical policy；其中false是安全預設，不代表線上現況，也不應整份套用來覆蓋已核准的線上開關。
