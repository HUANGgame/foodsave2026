# schema011 深入驗收：審查候選版

本輪使用者已批准最多10批合成資料，每批最多3帳號／1店／1商品／2訂單，逐批測試後精確永久清理。此文件與腳本本身不是真SQL成功證據。不得在公開CI執行、繞過Azure公開URL policy denial、擴權、建立trigger或接觸真人資料。使用既有受限runtime MI與既有owner分開執行；不修改runtime、migration、grant或公開註冊設定。

## 四個檔案與權限

- `backend/qa/schema011_fixture.py`：固定10批UUIDv5／操作鍵、manifest私有讀寫、seed。
- `backend/qa/schema011_races.py`：runtime MI，預設plan不連DB；每次只執行指定一批。
- `backend/qa/schema011_cleanup.py`：既有owner，schema011專用，預設僅preview；**不可使用舊owner_cleanup.py**。
- `backend/qa/schema011_notification_failure.py`：既有owner，預設plan；到期／缺貨通知唯一鍵衝突，兩個獨立outer transaction，finally rollback，無commit或DDL。

新增腳本透過 `python -m qa.<module>` 執行；從backend目錄並設`PYTHONPATH=.`。需要既有套件、ODBC及owner CLI登入，不自動安裝。核對固定commit及交接SHA256後，獨立審查者才能批准執行。私有runner外層設180秒timeout，先確認無真人流量、其他QA、結算或維護；腳本不改服務設定來強迫安靜時段。

## 私有manifest先於任何提交

由操作者在repo外建立僅本人可讀寫的0700目錄。使用新的UUID4，不要把實際run UUID／manifest內容或SQL例外貼入公開log。下列變數只引用操作者私有環境，不是憑證範例。

```sh
PYTHONPATH=. python -m qa.schema011_races
PYTHONPATH=. python -m qa.schema011_races --mode create-manifest --run-id "$FRESH_QA_RUN_UUID" --manifest "$QA_PRIVATE_MANIFEST"
```

manifest固定format11／scope／10批及全部UUID；讀取須完全符合推導結果。0600檔以exclusive-create保存、fsync檔案及目錄；拒絕symlink、不私有目錄、硬連結與不正確權限。每批開始前另保存不含秘密的`.CASE.started`檔，禁止已清理或結果不明的批次再次執行。保存兩者至全輪核對結束；不要刪start檔繞過重跑限制。

## 一批一驗、一批一清

每批實際建立3帳號／1店／1商品；只會建立最多1筆訂單，低於批准上限2筆。email為example.invalid、名稱帶foodsave-qa011及店UUID。隨機密碼僅留記憶體，不發登入token、不產生session、不改EXP設定。操作回應內的取貨憑證不輸出或寫manifest。

| CASE前綴 | left先完成業務動作、保留鎖 | right先完成業務動作、保留鎖 |
|---|---|---|
| reserve-mode | 預約成功，切模式409 | 資訊模式成功，預約409 |
| reserve-loss | 預約成功，舊revision缺貨409 | 缺貨歸零成功，預約409 |
| cancel-loss | 取消還1份，舊revision缺貨409 | 缺貨release0，晚到取消只回終態 |
| expiry-loss | 到期還1份，舊revision缺貨409 | 缺貨release0，到期返回absent |
| reserve-close | 預約成功，關店移除訂單／通知一次 | 關店成功，預約404 |

完整case名稱為前綴加`-left`或`-right`，共10批。先跑`reserve-mode-left`，清理核對後再逐批；不提供自動執行全部或自動owner清理的迴圈。

```sh
PYTHONPATH=. python -m qa.schema011_races --mode execute --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE" --approved-quiet-window --approved-committed-fixtures
```

兩worker為不同@@SPID。先行操作走原Service／procedure，完成後暫緩commit；另一連線用同一store applock、timeout0證明真實競爭（必須-1），再執行原業務動作，同時放行先行commit。不以sleep猜先後、不把deadlock當預期409、不自動retry。這是**受控交錯的雙連線業務驗收，不是無控制排程壓力測試**。

harness只在隔離Python process中替換Service的隨機UUID allocator，讓reserve／deletion／audit使用manifest事先分配的ID；不替換SQL、Service業務、時鐘或權限。每run有Session applock防止同run平行批次，上一批使用者仍存在時拒絕新批次。不同run／外部服務仍須靠已確認安靜時段隔離。

成功或失敗皆可能留下提交資料。每批停止worker後，由既有owner：

```sh
PYTHONPATH=. python -m qa.schema011_cleanup --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER" --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE"
# 核對counts、case及preview_sha256後，才執行同批限定清理：
PYTHONPATH=. python -m qa.schema011_cleanup --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER" --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE" --apply --approved-preview-sha256 "$REVIEWED_PREVIEW_SHA256"
```

preview持SERIALIZABLE／UPDLOCK／HOLDLOCK，最後rollback。apply重新檢查相同資料及摘要，按捕獲的精確主鍵刪除request_results、notifications、reservation_terminals、reservations、audit_logs、deletion_requests、products、stores、users；每列rowcount必須1，所有scope殘留必須0才commit。procedure產生的notification UUID不由harness指定，必須先滿足精確recipient／event_key／kind／vendor／terminal對應，再固定於preview摘要及主鍵清單。

所有使用者、店商品標記、訂單UUID／身份／snapshot、操作key／fingerprint、關店request／audit UUID均需符合manifest。查詢同時涵蓋**別人指向此批的引用**；任何非synthetic、額外活動、啟用trigger、cascade／不可信FK、變動摘要或SQL失敗均停止並rollback，不擴大刪除條件。session、favorite、review、EXP、spin、draw、coupon、ranking、erasure receipt任一相關資料存在即拒絕；不刪rate_limits或共用設定。

預期完整seed已提交或未提交，不支援猜測修補半批。若commit回覆遺失／timeout／清理已成功但回覆不明，停止後私下唯讀核對，不盲目重跑；已不存在的標記會fail closed。若reviewer擋住清理，回報此case精確UUID/key與counts，不換工具绕過。

## 無DDL通知失敗注入

```sh
PYTHONPATH=. python -m qa.schema011_notification_failure
PYTHONPATH=. python -m qa.schema011_notification_failure --execute --approved-quiet-window --run-id "$DIFFERENT_FRESH_QA_RUN_UUID" --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER"
```

各一個outer transaction建立3帳號／1店／1商品／1待領訂單及衝突通知；原expire_reservation或report_stock_loss必須因通知UNIQUE違反2601／2627失敗，且XACT_STATE=-1；finally rollback後重新查所有scope為0。既有owner才可插入衝突通知，不新增runtime INSERT權限。**此項只證明owner交易失敗回滾，不代替既有runtime41項權限驗收。關店通知使用去重，這種注入無效，所以仍未測，不加trigger。**

## 本地與部署證據分開

本地pytest驗manifest篡改、私有檔案、外部引用、request key／fingerprint替換、已關店資料、preview不寫入、摘要變動拒絕、精確主鍵刪除及中途失敗rollback。這些是Python安全測試，不能證明T-SQL compile、driver rowcount、真鎖競爭或Azure清理成功。執行者必須另外回報每case結果與各批清理remaining=0；失敗只回固定assertion／錯誤class，不公開driver例外、SQL參數或完整row。
