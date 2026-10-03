# schema011 深入驗收：審查候選版

本輪使用者已批准累計最多10批合成資料（8批競態＋2批通知回滾；失敗也占用），每批最多3帳號／1店／1商品／2訂單，逐批測試後精確永久清理。此文件與腳本本身不是真SQL成功證據。不得在公開CI執行、繞過Azure公開URL policy denial、擴權、建立trigger或接觸真人資料。使用既有受限runtime MI與既有owner分開執行；不修改runtime、migration、grant或公開註冊設定。

## 四個檔案與權限

- `backend/qa/schema011_fixture.py`：同一manifest固定8批競態＋2批通知回滾的UUIDv5／操作鍵、manifest私有讀寫、seed。
- `backend/qa/schema011_races.py`：runtime MI，預設plan不連DB；每次只執行指定一批。
- `backend/qa/schema011_cleanup.py`：既有owner，schema011專用，預設僅preview；**不可使用舊owner_cleanup.py**。
- `backend/qa/schema011_notification_failure.py`：既有owner，預設plan；到期／缺貨通知唯一鍵衝突，每次一個指定case的outer transaction，finally rollback，無commit或DDL。

新增腳本透過 `python -m qa.<module>` 執行；從backend目錄並設`PYTHONPATH=.`。需要既有套件、ODBC及owner CLI登入，不自動安裝。核對固定commit及交接SHA256後，獨立審查者才能批准執行。私有runner外層設180秒timeout，先確認無真人流量、其他QA、結算或維護；腳本不改服務設定來強迫安靜時段。

## 私有manifest先於任何提交

由操作者在repo外建立僅本人可讀寫的0700目錄。使用新的UUID4，不要把實際run UUID／manifest內容或SQL例外貼入公開log。下列變數只引用操作者私有環境，不是憑證範例。

```sh
PYTHONPATH=. python -m qa.schema011_races
PYTHONPATH=. python -m qa.schema011_races --mode create-manifest --run-id "$FRESH_QA_RUN_UUID" --manifest "$QA_PRIVATE_MANIFEST"
```

manifest固定format11／scope=`schema011-eight-races-two-rollback-injections`／10批及全部UUID；舊十批race manifest不相容，尚未執行的舊版不得使用；讀取須完全符合推導結果。0600檔以exclusive-create保存、fsync檔案及目錄；拒絕symlink、不私有目錄、硬連結與不正確權限。每批開始前另保存不含秘密的`.CASE.started`檔，禁止已清理或結果不明的批次再次執行。保存兩者至全輪核對結束；不要刪start檔繞過重跑限制。

## 一批一驗、一批一清

每批實際建立3帳號／1店／1商品；只會建立最多1筆訂單，低於批准上限2筆。email為example.invalid、名稱帶foodsave-qa011及店UUID。隨機密碼僅留記憶體，不發登入token、不產生session、不改EXP設定。操作回應內的取貨憑證不輸出或寫manifest。

| CASE前綴 | left先完成業務動作、保留鎖 | right先完成業務動作、保留鎖 |
|---|---|---|
| reserve-mode | 預約成功，切模式409 | 資訊模式成功，預約409 |
| reserve-loss | 預約成功，舊revision缺貨409 | 缺貨歸零成功，預約409 |
| cancel-loss | 取消還1份，舊revision缺貨409 | 缺貨release0，晚到取消只回終態 |
| expiry-loss | 到期還1份，舊revision缺貨409 | 缺貨release0，到期返回absent |

競態case名稱為前綴加`-left`或`-right`，共8批；另保留`notification-expiry`與`notification-loss`兩批給通知回滾。**十批是本輪累計上限，只准一份manifest；失敗批次也占用該case，不另建run／manifest／批次補跑。**先跑`reserve-mode-left`，清理核對後再逐批；不提供自動執行全部或自動owner清理的迴圈。

```sh
PYTHONPATH=. python -m qa.schema011_races --mode execute --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE" --approved-quiet-window --approved-committed-fixtures
```

兩worker為不同@@SPID。先行操作走原Service／procedure，完成後暫緩commit；另一連線用同一store applock、timeout0證明真實競爭（必須-1），再執行原業務動作，同時放行先行commit。不以sleep猜先後、不把deadlock當預期409、不自動retry。這是**受控交錯的雙連線業務驗收，不是無控制排程壓力測試**。

harness只在隔離Python process中替換Service的隨機UUID allocator，讓reserve使用manifest事先分配的ID；不替換SQL、Service業務、時鐘或權限。每run有Session applock防止同run平行批次，上一批使用者仍存在時拒絕新批次。不同run／外部服務仍須靠已確認安靜時段隔離。

競態成功或失敗皆可能留下提交資料。每批停止worker後，由既有owner：

```sh
PYTHONPATH=. python -m qa.schema011_cleanup --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER" --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE"
# 核對counts、case及preview_sha256後，才執行同批限定清理：
PYTHONPATH=. python -m qa.schema011_cleanup --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER" --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_CASE" --apply --approved-preview-sha256 "$REVIEWED_PREVIEW_SHA256"
```

preview先取得與worker相同run guard（timeout0），worker仍執行就拒絕清理；再持SERIALIZABLE／UPDLOCK／HOLDLOCK，最後rollback。apply重新檢查相同資料及摘要，按捕獲的精確主鍵刪除request_results、notifications、reservation_terminals、reservations、products、stores、users；每列rowcount必須1，所有scope殘留必須0才commit。procedure產生的notification UUID不由harness指定，必須先滿足精確recipient／event_key／kind／vendor／terminal對應，再固定於preview摘要及主鍵清單。

所有使用者、店商品標記、訂單UUID／身份／snapshot、操作key／fingerprint均需符合manifest。查詢同時涵蓋**別人指向此批的引用**；任何非synthetic、額外活動、啟用trigger、cascade／不可信FK、變動摘要或SQL失敗均停止並rollback，不擴大刪除條件。session、favorite、review、EXP、spin、draw、coupon、ranking、deletion request、audit、erasure receipt任一相關資料存在即拒絕；不刪rate_limits或共用設定。

預期完整seed已提交或未提交，不支援猜測修補半批。若commit回覆遺失／timeout／清理已成功但回覆不明，停止後私下唯讀核對，不盲目重跑；已不存在的標記會fail closed。若reviewer擋住清理，回報此case精確UUID/key與counts，不換工具绕過。

## 無DDL通知失敗注入

```sh
PYTHONPATH=. python -m qa.schema011_notification_failure
PYTHONPATH=. python -m qa.schema011_notification_failure --execute --approved-quiet-window --manifest "$QA_PRIVATE_MANIFEST" --case "$QA_NOTIFICATION_CASE" --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER"
```

每次僅選同一manifest中的`notification-expiry`或`notification-loss`，在任何連線／寫入前保存0600 exclusive/fsync開始標記；占用本輪十批中的一批，失敗也不能重跑。保持run session guard至殘留檢查結束，同run不可平行，上一批未清理就拒絕。一個outer transaction建立3帳號／1店／1商品／1待領訂單及衝突通知；原expire_reservation或report_stock_loss必須因通知UNIQUE違反2601／2627失敗。同一T-SQL CATCH先保存ERROR_NUMBER、XACT_STATE及@@TRANCOUNT至local variables，再於同batch執行IF XACT_STATE()<>0 ROLLBACK，最後SELECT保存的診斷；避免doomed transaction離開batch引發3998。Python仍要求原錯誤為2601／2627、回滾前XACT_STATE=-1且@@TRANCOUNT>=1，其他錯誤不得判PASS。finally rollback後重新查所有scope；即使SQL／診斷斷言失敗也執行殘留核對，某表非零仍繼續核對其他表，任何錯誤都不能判PASS。既有owner才可插入衝突通知，不新增runtime INSERT權限。**此項只證明owner交易失敗回滾，不代替既有runtime41項權限驗收。關店通知使用去重，這種注入無效，所以仍未測，不加trigger。為遵守十批累計上限，關店↔預約兩種競態順序延後；關店與新預約同時操作時的通知與刪單一致性仍未實測，先前單連線41項不能替代。**

## 本地與部署證據分開

本地pytest驗manifest篡改、私有檔案、外部引用、request key／fingerprint替換、已關店資料、preview不寫入、摘要變動拒絕、精確主鍵刪除及中途失敗rollback。這些是Python安全測試，不能證明T-SQL compile、driver rowcount、真鎖競爭或Azure清理成功。執行者必須另外回報每case結果與各批清理remaining=0；失敗只回固定assertion／錯誤class，不公開driver例外、SQL參數或完整row。

## 安全審查修訂狀態

舊候選`b29968b`尚未Azure實跑；安全審查指出跨SQL batch交易狀態判讀及額度口徑問題。本修訂把全部8競態＋2回滾／失敗批次納入單一manifest，移除額外fresh-run通知入口，加入同batch錯誤診斷及finally殘留檢查。修訂以獨立commit交接復審；舊hash不可當新版本驗證，尚未獲得本輪真SQL結果。

後端runtime／migration／grant及部署ZIP未變。Android #19登入前焦點poll失敗，#20通過焦點／鍵盤後WebView連線關閉，根因尚未確認；#21與#22後續完整fixture流程通過，不代表先前根因已修復。超商整合及APK證據見[交付紀錄](ANDROID_CONVENIENCE_CHECKPOINT.md)。本輪SQL尚未執行。

## 固定復審來源（2026-10-03）

QA程式固定於 `dd82efdf0e7c1ec5a9ca76e2c44d77c2eed0069b`；本地後端170 passed（含QA安全測試），尚未Azure實跑。此版修正673c15e通知CATCH僅SELECT但未同batch rollback的復審blocker；其餘三檔不變。測試驗證保存診斷→rollback→回傳順序、非預期錯誤仍失敗、Python finally及全scope殘留檢查保留；這不是真SQL／driver驗證。不得使用舊版通知hash或十競態manifest。

| backend/qa 檔案 | SHA256 |
|---|---|
| schema011_fixture.py | `a74ce0d9d1cd01c4985a44c581d8a2b0096184248f25adfd5dc9815043d5eae4` |
| schema011_races.py | `d3c4e266f418b48a53ee96023ee8af1532ccddf3f797a9c1584563b6197041ef` |
| schema011_cleanup.py | `f5c7586454e362bed807250159c312b5a4106a6ed2b32ee1964b4afb89e33c9c` |
| schema011_notification_failure.py | `670bcb4066143474b00bf80cd47944e8d5878ab7eec96715bd5ec6e7f0a5996e` |
