# 帳號刪除執行工具（預設停用）

這是待審查開發成果，未對 Azure 執行。帳號停用不等於資料抹除；SQL 清除也不等於備份、記錄與外部圖片已刪除。正式保存政策及逐案安全審查仍須使用者確認，不能把本工具視為法遵證明。

## 執行前必要條件

- owner 套用 `004_erasure.sql`；這是向後相容的附加 migration。HTTP runtime 仍只需 001–003，權限不新增，不自動啟動刪除。
- 營運者核定真實政策：版本、申請寬限天數、個資清理後業務紀錄保存天數、SQL 回執保存天數，以及備份／存取記錄／外部照片處理程序。所有天數需明確有限，程式不提供正式預設值。
- 每案確認法律保存例外、其他人交易、待取訂單與自由文字中的個資後，由 owner 明確設定該筆 `deletion_requests.approved_for_erasure=1`。預設 0；runtime 沒有 UPDATE 權限。遇到例外應人工訂定期限及追蹤，不能當作可無限保存的批准。
- 政策 JSON 的 `enabled` 預設 false；正式執行還需 `--apply`，且必須已获实际永久删除授权。本輪只有開發／測試授權，**不得啟用或跑真實清除**。

政策欄位為 `version`、`grace_days`、`business_retention_days`、`receipt_days`、`external_procedure`、`enabled`。前五項必填；沒有可直接複製為正式政策的範例天數。`external_procedure` 是已核定外部處理程序的識別或文字，不是執行成功證明；政策檔放在 Git 忽略的 `.env.erasure-policy.json`。

## 工具與狀態

owner ZIP 包含 `owner_erase.py`，與 `owner_migrate.py` 共用既有 Azure CLI owner 登入；不建立憑證、不改 GRANT、只允許專用 `foodsave`。先以既有的 server／driver 參數及 `--database foodsave --policy .env.erasure-policy.json` 執行 dry-run；省略 `--apply` 時全部都是 SELECT。未配置政策即失敗，不會先取得 token。

批次只選取已經逐案批准且到期的申請；未批准案保持pending。每批預設最多 10 案，上限 100；是帳號數上限，不保證個別帳號資料量／交易耗時。每案每階段獨立交易，5 秒鎖等待；失敗回滾並標 `failed_retryable`，其他案繼續，下次重跑。真SQL鎖／FK／回滾仍待隔離資料庫驗證，不能直接以真用戶試跑。

1. 申請受理：現有 API 立即停用並撤銷 session，取消本人等待訂單。商家的其他消費者等待訂單必須先由既有流程完成／取消／到期；工具不擅自終止它們。
2. 寬限期及個案審查通過：`clear_pii` 移除 email、密碼、session、本人評論／收藏／冪等回應；清除商家名稱／照片URL／座標及交易快照中的商家文字。保留記錄仍有內部識別碼，屬於假名化，不能聲稱完全匿名。原密碼此後不能用於公開狀態查詢；營運者須依申請回執協助，不能因此再保留密碼。
3. `pii_cleared_business_retained`：依此次固定政策版本及計算好的 `purge_after` 等待；换政策不會縮短既有期限，版本不符阻擋並要求人工審查。
4. 到期 `purge_business`：依 FK 順序刪除本人券／抽獎／發放／EXP／排行／預約／稽核／使用者及申請。其他消費者交易不刪除；其必要商品／店家留已清理文字的空殼，owner_id 設 NULL。沒有交易引用的本人商品／店家移除。
5. `sql_completed`：僅保存不含 user_id/email 的 request_id、政策版本及到期時間回執，重跑不重做。回執到期每批最多清100筆，之後查詢 `not_found` 不表示未曾完成。對持有原申請的營運者而言，request_id 仍可間接識別，必須限制存取／遵守期限。

## 清理邊界與必要人工工作

程式不能辨識其他人評論、管理員自由文字或外部檔案內的所有個資。逐案審查必須涵蓋它們，不能只靠欄位清單。IP／帳號雜湊節流桶也不是匿名證明：本人 email 對應刪除桶會清除，其餘桶與網站／平台存取記錄須依正式期限處理，不能直接删除所有人的反濫用資料。

SQL 備份、還原副本、匯出、部署／存取記錄、外部圖片或客服資料不在此工具內。營運者需設定到期清除與還原後重新套用刪除的程序；未完成不得標示「完整抹除」。程式每次明確回傳 `external_erasure_verified: false`。無公開回執查詢端點，避免帳號／申請列舉。

測試用交易替身只證明控制流程與 SQL 呼叫計畫；真SQL最後庫存競爭／參照完整性、大資料量、還原後重做、Android 都仍待驗收。未新增付費服務、排程、身份或權限。

005增量：runtime透過僅含request_id/user_id參數的submit_deletion_request程序提交，固定未批准；既有同交易鎖／撤銷邏輯維持。批准與真正清除工具仍owner-only，005不批准任何帳號清除。

## schema011來源相容性（未執行清除）

新版owner工具需要schema011；收藏欄位已由store_id改vendor_id。本人notifications/reservation_terminals於clear_pii清除；其他受件人的店家通知文字／related_vendor_id及terminal.vendor_id清除識別；purge先刪新增FK子列再刪user。grace_days上限30。各批次在既有enabled＋individual approved＋policy門檻下才可執行。

007提出通知及terminal各30天expires_at；enabled owner run每輪各最多100筆到期清理。未配置／部署排程，不宣稱自動準時抹除；保存長度及執行頻率需隨本版一併審查。business_retention_days、receipt_days及外部backup/log/photo程序仍需明確政策，不用此程式宣告隱私流程完成。刪terminal後保留的最小idempotency收據仍阻止同key重新建立訂單。
