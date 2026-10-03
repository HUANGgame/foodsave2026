# 安全補強階段：證據與剩餘缺口

這是程式與mock驗證，**不是正式環境全部驗收通過**。

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

## 全範圍目前證據

| 範圍 | 已有證據 | 真正验收狀態 |
|---|---|---|
| UI／四分頁／照片／地圖 | 靜態建置、browser合同與demo回歸紀錄 | GPS拒絕／逾時／不可用及返回商品有browser mock；Android未驗 |
| 登入／角色／session | 單元與API mock拒絕測試、前端session隔離 | 真DB登入、跨裝置、代理節流未驗 |
| 商品／預約／取消／核銷 | 前後端合同、快照單元、程式交易鎖 | SQL最後庫存並發、取消核銷競爭、重啟一致性未驗 |
| 收藏／評論／EXP | 原demo邏輯與API程式／部分mock | 真DB唯一事件、彙總、營運EXP值未驗／待決策 |
| 週排行 | 台北週界單元、可重入結算程式 | 真DB結算重跑、有效期／同分規則批准待辦 |
| 轉盤／獎品 | mock重試一次扣除、關閉恢復、減少動畫與落點檢查 | 真SQL次數／獎品交易、真獎品履約、Android FPS未驗 |
| 刪除帳號 | 受理／停用／查詢／返還程式與mock | owner分階段SQL清除工具已開發、預設停用；真SQL、政策與外部清除未驗 |
| 隱私與公開註冊 | 草案頁／配置接口／未配置拒絕註冊 | 真營運資料、公開政策及Data safety未完成 |
| 管理／DB查看 | 本地HTTP與browser mock、白名單／角色程式 | Azure部署未驗、viewer未批准；可先由owner用SQL Portal |
| Azure SQL／migration | SQL檔及owner工具已寫、未連真DB | 執行環境網路准入／owner路徑受阻；migration和GRANT未執行 |
| F1主機部署 | 受控ZIP、校驗碼、根目錄requirements／startup | 主機建立不等於程式部署；部署通路仍由負責人確認 |
| APK／AAB | API36編譯、debug簽章／unsigned、manifest／ZIP／bundletool | 產物為.test合同配置；未實機安裝，不是發布版 |
| ER／手冊 | 與現有migration／程式對照 | 尚未以真環境從頭操作驗證 |

結論：可以交接可審查程式與部署材料，不能聲稱其他項目全部驗收或production ready。未新增費用或權限，未觸碰其他資料庫。前階段未改schema，本次004僅寫入migration檔，尚未套用。

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
