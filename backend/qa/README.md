# 真SQL驗收腳本：僅準備，尚未執行

`sql_acceptance.py`不使用mock，不含HTTP服務或新權限／清理功能；預設`--mode plan`完全不連DB。只以現有runtime MI與005 schema執行，不能改用owner權限假裝runtime測試通過。用App私有SSH的既有Python環境，設定PYTHONPATH指向已部署backend套件；不放進web startup、不建立排程。執行前先驗證下載commit及SHA256。

## 最小執行条件

1. 專用foodsave、001–005已套用，runtime受限授權有效，現有SQL／ODBC連線可用。不得新增角色、秘密或資料庫。
2. 營運者確認短暫安靜驗收時段：無真人流量、無平行QA、无週結算／全域維護／owner清除。腳本不更改公開註冊或服務設定來強迫這個條件。
3. 回滾段要求沒有任何現有可抽獎品；若有即整段拒絕，不停用或消耗它們。為防止檢查後插入競態，交易內HOLDLOCK讀取合格獎品範圍，可能短暫阻擋管理員獎品寫入，故須安靜時段。兩種模式使用不同run UUID。
4. 並發段必須先由父流程取得**提交暫存QA資料及後續owner精確清理的批准**。目前僅準備腳本，未取得執行／清理完成證據；不要把CLI批准旗標當成使用者授權。
5. 在shell外層設180秒timeout。失敗／斷線後先查manifest及QA UUID記錄，不盲目重跑同一run，不能以模糊LIKE條件永久刪除資料。

## 回滾段

`--mode rollback --run-id <NEW-UUID> --approved-quiet-window`

三個全新synthetic帳號（consumer兩個／vendor一個），**沒有admin**；一店、一商品、獎品與spin grant、測試預約均在同一條真SQL連線的外層交易內建立。Service方法直接執行真實SQL，共用此連線但不提交，finally rollback，另外查fixture使用者計數為0。發生錯誤也回滾，不呼叫owner erasure。

涵蓋本人取消same-key重播／new-key拒絕、跨帳號取消404、錯取貨碼400、核銷same-key不重增EXP／new-key拒絕、過期預約transition只還庫存一次、抽獎same-key只扣一次且只一筆draw/coupon。既有EXP配置只讀、不修改；停用時EXP為0也屬預期，僅驗證不重複。

最後驗證procedure單一INSERT可執行、額外approved_for_erasure參數被SQL拒絕8144、批准欄位SELECT／UPDATE與基表INSERT被拒絕229或230。沒有傳送有效永久刪除操作。因runtime不可讀owner欄位，本段不能直接證明資料內批准值；固定0／NULL仍需owner另行檢查程序定義，不扩大runtime讀權。

過期測試用新fixture預約的過去expires_at，不修改任何現有日期、不等待真實30分鐘，也不執行會掃全DB的expire_reservations維護工作。因此不能宣稱全域排程／週結算／真實牆鐘到期全部通過。

## 兩連線競爭段

`--mode concurrency --run-id <DIFFERENT-NEW-UUID> --approved-quiet-window --approved-committed-fixtures --manifest <PRIVATE-NEW-PATH.json>`

先以exclusive-create、mode0600寫出不含密碼／token的復原manifest，再提交只屬本run的三帳號、一店、一份庫存商品。兩個ThreadPool worker各開真正獨立SQL transaction／@@SPID，以Barrier同時發起原Service.reserve。要求兩個SPID不同、結果恰為201與409、庫存0且僅一筆已提交預約。SQL exception/deadlock不算預期409，也不自動重試掩蓋失敗。

**不能整體rollback-safe**：兩連線必須看見同一份已提交庫存；勝者也需提交才讓另一條觀察結果。其餘成功／失敗／逾時都可能留下此run資料；腳本沒有永久清理，也不把fixture帳號停用當作抹除。商品有10分鐘期限但不會自動清掉歷史資料。

所有ID由run UUID以uuid5固定導出；使用者email為保留example.invalid域，店家／商品名稱為foodsave-qa:<run-UUID-hex>。密碼只在記憶體產生並雜湊，不輸出或存入manifest；取貨碼與券碼也不記錄。輸出僅斷言名稱／數量、狀態、錯誤class，SQL參數／例外詳情不輸出。

## 清理交接（待單獨批准，未執行）

owner先依manifest exact UUID與fixture email/name雙重核對；掃描是否有非本run帳號的交易／收藏／評論引用QA商品／店家／獎品，如有即停止，不能連帶刪他人紀錄。獲批准後只刪本run參照鏈：request_results/audit_logs/exp_events、測試reservations等子列，再product/store/users；本模式不產生獎品／grant，不能刪prizes或其他run資料。保留刪除前後aggregate count證據，不輸出帳密或整列。脚本中沒有任何cleanup入口、DELETE users或擴权。

## 證據邊界

本次僅Python語法檢查、無DB plan輸出及靜態隔離檢查。**尚未執行真SQL驗收，不能宣稱上述斷言通過。** 即使之後通過，仍非HTTP/CORS/代理節流／跨裝置／完整管理流程／週排行／備份還原驗收。不要在公開CI連真Azure或把manifest上傳到GitHub。

部署端執行更新：2026-10-03 06:53 UTC，browser worker回報runtime MI／schema005、preflight users0／prizes0，rollback模式15斷言全部passed、exit0、committed_fixtures_remaining=false。此為部署端真SQL執行報告；並發模式未執行。

## Approved concurrency fixture cleanup (owner only)

The parent supplied explicit user approval to create the three synthetic accounts/product batch and remove only that batch after testing. `qa/owner_cleanup.py` is separate from deployment/startup/runtime and does not grant permissions. Use the existing authorized owner connection from `owner_migrate.py`; NEVER run with runtime MI or change its DELETE grants.

Minimum additional file is `qa/owner_cleanup.py`; dependencies are the existing owner ZIP's `owner_migrate.py`, `foodsave` package and installed requirements. From that backend directory, set `PYTHONPATH=.`. Keep the original private recovery manifest intact. First run (counts only, transaction rolled back):

```sh
PYTHONPATH=. python qa/owner_cleanup.py --server "$FOODSAVE_SQL_SERVER" --database foodsave --driver "$FOODSAVE_ODBC_DRIVER" --manifest "$QA_MANIFEST"
```

Review `run_id`, counts (3 users, 1 store, 1 product, 0 or 1 reservation and matching request result), and `preview_sha256`. The deployment operator, under the granted batch-specific approval, may then repeat that exact command with `--apply --approved-preview-sha256 "$REVIEWED_PREVIEW_SHA256"`. Apply revalidates the complete preview under serializable locks; changed digest, marker, foreign references, row counts or SQL error rolls back. Set an external execution timeout (180 seconds); do not silently rerun an uncertain commit. SQL state must be checked privately if connection loss makes commit outcome uncertain.

IDs must exactly match all UUIDv5 values derived from the manifest run UUID. Account emails/roles, store owner/name, product metadata, reservation customer/product/state/quantity/snapshot and the sole `reserve/qa-concurrent-stock` result must match. Any other account activity, enabled trigger or cascading/untrusted/disabled FK aborts. Only scoped request results, captured reservation IDs, product/store IDs and three account IDs are deleted. No DROP, global expiry job, other-table cleanup, grant or policy change. A second execution after successful cleanup intentionally fails closed on missing markers.

Local verification covers malformed manifests, substituted IDs, preview rollback, stale-preview rejection and rollback on validation failure (3 tests); it is not evidence that cleanup executed on Azure SQL. Actual preview/apply results must be reported by the deployment operator.

## Confirmed deployment-worker outcome (2026-10-03)

The parent confirmed real SQL concurrency mode completed with three assertions and exit0: two distinct @@SPIDs synchronized by Barrier; one harness status201 and one409; stock0 and exactly one committed reservation. These are direct Service calls, not actual HTTP requests. The authorized owner reviewed the preview digest and applied exactly the recovery manifest; commit exit0 removed 3 synthetic users and 1 each store/product/reservation/request_result. Post-check found zero batch rows in all five tables. Schema remained 22 tables/migrations001–005; runtime permission query returned the unchanged76 rows and role memberships0. This supplements the previous15 rollback assertions and is not a new local execution claim. Actual resource IDs, private manifest and account data are not published. The completed batch must not be recreated; future batches require scope confirmation.

## New pickup rollback-only SQL / in-process API acceptance

Minimal additional file: `qa/pickup_rollback.py` (standalone; no dependency on earlier QA scripts). Use compatible runtime code from7824868 or later, existing restricted runtime MI and existing private test environment with `httpx==0.28.1` available. Do not add test dependencies to the production startup/ZIP or automatically install them in the runtime. Default plan has no DB access:

```sh
PYTHONPATH=. python qa/pickup_rollback.py
# From backend, only inside the already approved private execution environment:
PYTHONPATH=. python qa/pickup_rollback.py --execute --approved-quiet-window --run-id "$FRESH_QA_RUN_UUID"
```

Apply an external180-second timeout. Three synthetic identities (consumer/vendor/other-vendor), one store/product, sessions, receipts and rate buckets exist only within one outer transaction; all exit paths request rollback, no commit/cleanup/owner/grant operations. Product bounds and past-expiry fixtures are scoped to fresh UUIDv5 IDs; no real rule or user updates. No manifest or credentials are written. Auth uses realSQL sessions and normal FastAPI bearer dependencies; only the service's connection is pinned to the single rollback transaction. Routes run through TestClient's **in-process ASGI transport**, not public network HTTP; this does not bypass blocked browser URLs and does not prove deployed TLS/CORS/App integration or concurrency. No new external listener.

Covers reserve replay/duplicate hold, opaque QR, preview without fulfillment/stock/EXP mutation, wrong store/consumer/format, manual fallback, review binding/token/expiry, one delivery and same-key recovery, EXP policy without rule changes, stock±1/replay/negative/upper bounds, expired code/release-once, manual guess limit, then zero residual checks for7 tables plus scoped rate buckets. Successful output gives exact assertion count/names; failed output only a fixed assertion name or exception class. Review failures privately, do not print SQL/credentials/codes. The local3 safety tests and syntax check are not realSQL execution proof. Actual camera scanning remains a physical-device acceptance item.
