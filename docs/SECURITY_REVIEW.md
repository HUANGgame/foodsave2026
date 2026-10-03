# 安全補強階段：證據與剩餘缺口

目前已有本地mock、真SQL及Android fixture分區證據，**不是正式環境全部驗收通過**。下方「最新證據」為目前狀態，其餘階段紀錄保留歷史時點。

前一階段：33個後端單元／API mock、10個前端單元、6個App browser合同通過；新增公開帳號頁的browser mock也通過。涵蓋刪除重試／查詢、確認勾選、密碼欄清除、跨用戶取消拒絕、角色限制、登入世代隔離與抽獎重試。未執行真SQL資料變更。

## 已修正

- 刪除回覆遺失：可在後端`/account`以原帳號密碼查詢或重送，受理後不依賴已撤銷的session，不發新token。
- 刪除待領取訂單：同一交易內按商品／預約順序鎖定、重查waiting後取消並返還；與核銷競爭的真正效果待SQL驗證。
- 重複刪除返回同一申請，不重複返還庫存。
- 公開註冊除開關外，也要求後端營運者／聯絡／保存說明已配置。
- 晚到的旧登入回覆不能清掉新登入token；session變更後不送出尚未發出的舊意圖。

## 本次部署差異

新ZIP包含`/account`網頁、刪除申請與狀態API、`/privacy`公開配置接口及以上後端修正。現有001/002/003 SQL migration未改，**不需要新增schema版本**。runtime需要對`deletion_requests`增加SELECT（原建議僅INSERT）；仍限定同一專用DB及既有runtime身份，由部署負責人確認／套用，不由此工作區執行GRANT。

新增非秘密環境變數：`FOODSAVE_OPERATOR_NAME`、`FOODSAVE_PRIVACY_CONTACT`、`FOODSAVE_RETENTION_SUMMARY`。未填時`/privacy`標draft、公開註冊保持關閉。不得用測試內容假裝正式政策。

## 最新證據（2026-10-03，優先於下方歷史紀錄）

真Azure結果來源為部署端執行報告，由父流程確認；此workspace未直接連線執行，並非本地mock推論。公開文件不列實際資源／身分ID或批次個資。

| 範圍 | 已確認證據 | 剩餘缺口 |
|---|---|---|
| Azure部署／schema／權限 | runtime部署；22 tables，migrations001–005；受限MI可用 | 重啟／還原演練尚未驗 |
| 真SQL回滾驗收 | 15斷言passed、exit0；跨帳號拒絕、取消／核銷／到期重播、抽獎冪等、procedure權限邊界；fixture rollback | HTTP及App端整合仍未驗；取消與核銷競爭另待驗 |
| 真SQL最後一份並發 | 兩個不同@@SPID、Barrier同步；一個201、一個409、stock0、恰1 reservation；3斷言passed、exit0 | 是Service直接呼叫；201/409為harness結果，不是實際HTTP回應 |
| 該批owner清理 | 審閱preview digest後apply同manifest、commit exit0；刪3 synthetic users、1 store、1 product、1 reservation、1 request result | 僅QA清理，不代表營運帳號刪除政策已核准／執行 |
| 清理後檢查 | 上述5 tables該批殘留均0；schema22 tables／001–005不變；runtime權限查詢76 rows、role memberships0不變 | 筆數不代表逐項授權內容的獨立新審查；未授runtime DELETE |
| Android真APK＋fixture API | run37104919923 success；安裝／啟動、三角色入口與流程、鍵盤／Back、GPS拒絕／服務關閉、轉盤連點／恢復／落點／減少動畫、force-stop重登入 | 真Azure API、GPS允許／外部導航、實機FPS及完整admin CRUD未驗 |
| APK交付 | CI v1/v2簽章、manifest與hash已驗 | CI無artifact保留；尚無本輪可下載的真API APK／正式簽署版 |
| 隱私／營運／完整功能 | 註冊仍關閉；政策草案與owner刪除工具；65後端本地測試通過 | 真營運者／保存政策／獎品／EXP／排行／外部副本處理待確認；不可標production ready |

本輪並發與清理已完成，無需為補文件重建帳號或再次執行QA。runtime及owner部署ZIP不變；後續QA批次、公開註冊和權限變更仍需各自確認範圍。

## 刪除工具階段增量

新增 owner-only `erasure.py` / `owner_erase.py`、004 migration（店家 owner_id 可空、申請審查／清除時間、有限期回執），詳見 [ERASURE_RUNBOOK.md](ERASURE_RUNBOOK.md)。runtime ZIP內容不變，003 readiness與既有最小權限不变；部署084版本不需為這個owner工具重部署。新owner ZIP會含004，勿在未審查時假設已套用。沒有呼叫Azure刪除。

本輪新增交易替身測試：預設關閉、逐案審查、dry-run零寫入、有限期限、政策版本、等待訂單阻擋、兩階段、FK順序、重試與失敗回滾。GPS拒絕／不可用／逾時提示及評論返回有browser mock。完整個資抹除仍需外部副本和自由文字人工審查；不得把程式測試標成正式驗收。

驗證結果：48後端單元／交易替身、10前端單元、9App browser mock通過，Next静態建置成功；pytest有1項Starlette/httpx棄用警告。未重建APK，既有APK不含本輪GPS變更。

Android CI追加：標準ubuntu-24.04首次run 37101823813失敗（KVM預設讀寫權限不足），未sudo擴權、未SDK授權、未build/install/launch。最小一次性ACL提案待使用者確認，詳見ANDROID_CI.md；未增加Azure/DB權限或變更部署包。

真Azure SQL驗收發現002的inline CHECK跨欄位造成8141；已改為表級 `ck_ranking_rules_range CHECK(end_rank>=start_rank)`。檢查001–004其餘CHECK未發現同類inline跨欄位問題，新增静態結構回歸（包含舊錯誤必須被偵測）。這不是SQL編譯測試；owner須確認前次交易rollback並重跑migration，不能因001曾印Applied就認定已提交。runtime ZIP未變。

005已批准的申請程序隔離：API只傳兩個UUID；程序強制未批准且owner時間空值。runtime新增單一procedure EXECUTE、基表INSERT仍拒絕。62後端測試通過（API拒絕惡意owner欄位、既有重試／交易mock、程序／grant靜態檢查）；真SQL权限与迁移未驗。Android第4run整體failure：build/sign/install/Activity成功，WebView偵測逾時，三角色UI未執行；詳見ANDROID_CI。

Android fixture進展：run37103516509 success，真APK安裝啟動、WebView中消費者預約取消／商家表單／管理員入口及原生force-stop/relaunch通過。WebView provider、foreground activity及debug socket均有日誌證據，release設定未變。這是實際Android＋mock API，不是Azure／完整功能驗收；GPS、外部導航、完整admin、真SQL並發與冷啟動穩定性仍有限制。CI無artifact upload，沒有可下載CI APK。

真SQL新證據（來源：部署端browser worker的runtime MI執行報告，2026-10-03 06:53 UTC；不是本地mock）：在schema005、preflight users=0／eligible prizes=0下，sql_acceptance rollback模式15項斷言passed、exit0、committed_fixtures_remaining=false。包含跨帳號取消拒絕、取消／核銷／到期重播、同key抽獎不重扣、procedure成功／額外owner參數拒絕、基表INSERT與owner欄位讀写拒絕、fixture rollback。兩連線並發模式尚未執行／待暫存資料與精確清理批准；不可把本輪回滾交易成功擴稱持久化／並發／HTTP／跨裝置全通過。

Android追加驗證（2026-10-03 07:06 UTC）：run37104919923 / f16a3a16 success；真APK模擬器通過鍵盤、原生Back、拒絕定位／關閉定位服務、轉盤防連點／背景恢復／精確停獎／減少動畫，既有角色fixture也通過。無權限、release除錯或憑證變更，無付費runner／cache／artifact upload；不代表真API或實機FPS。

並發batch清理已收到父流程附帶的使用者明確授權。新增owner-only `backend/qa/owner_cleanup.py`，預設preview、限定manifest衍生ID與QA標記，需先審閱preview digest再apply，serializable transaction及外部引用／筆數檢查。沒有執行真SQL清理或授予runtime DELETE；部署端負責實際操作與回報。

取貨增量最新：7824868 Android run37107966613 success，原生相機拒絕及手動preview/confirm/同key retry有實際APK證據，並非真鏡頭掃碼。新私有pickup_rollback.py採3 synthetic identities、單一外層rollback、真SQL／in-process FastAPI依賴認證；尚未在Azure執行。新增3項harness安全檢查通過。新介面無migration006／grant；原18項真SQL證據仍屬之前版本。隱私operator/support/30天方向已批准，policy-complete=false及registration=false，未聲稱自動刪除已部署。
