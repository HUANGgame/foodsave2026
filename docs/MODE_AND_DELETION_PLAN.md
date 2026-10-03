## 部署端確認：schema011 真SQL與回滾QA（2026-10-03）

父流程回報：owner已完成006–011實際T-SQL compile/commit；限定runtime權限盤點76→96，role memberships仍0；runtime部署成功，private readiness=ready，registration=false、privacy=draft。實際資源及deployment識別碼只留私有交接，不公開。

使用受限MI執行e60a362版本terminal_rollback.py，41 assertions全部PASS，synthetic資料rollback後zero residual。涵蓋到期一次結算／實體刪單、缺貨release0／晚到重試、vendor closure通知去重／範圍檢查等。這是部署端提供的真SQL證據，不是本workspace再次執行；不能視為HTTP/TLS/CORS或Android連真API通過。

尚未測：通知INSERT失敗注入的SQL rollback、schema011相向雙連線競爭、public/deployed HTTP及Android實連線、實機相機。新Android fixture證據另見ANDROID_SCHEMA011_CHECKPOINT.md。先前migration007 SQL102已修復並經部署端此次compile確認；不得把舊失敗紀錄改成從未發生。

---

# 兩階段部署前實作 checkpoint（歷史；最新結果見上方）

以最新使用者規則為準。A資料層及B介面已寫入本次source；新SQL尚未套用／驗證。既有delivery根目錄7824868套件仍保留，新版只置於schema011-review子目錄待審查。不能將舊schema005的SQL成功證據套用到本版。

## 已實作

- 店家唯一information/reservation模式：新店information、舊店回填reservation；waiting>0切information回409且不改狀態。reserve、mode及庫存操作共用transaction-owned store applock。006唯一owner索引；既有多店owner即停止migration，不自動刪店。
- 007通知及獨立reservation_terminals；收藏以vendor帳號為鍵。無對應owner的舊收藏使migration停止，不默默刪資料。
- 008逾期先記終態／通知、返庫一次，再刪reviews/orders。已completed不刪；舊expired不重返庫。request_results保留key，scrub舊取貨能力及快照；原reserve/preview重試410，晚到cancel讀終態不返庫。
- 009商家刪帳：同交易先驗密碼、提交刪除申請、停用登入／撤銷session，程序去重通知訂單顧客及收藏者，再刪相關reviews/orders/favorites/products/store。users實體刪除不在runtime權限內。
- 010實際缺貨：先核對owner、revision及waiting筆數，寫道歉通知／release=0終態，再刪該product waiting orders。可售量直接採店家確認值；無EXP／處罰。普通可售量0或±1不取消已保留商品。
- 011通知已讀只改該user＋notification組合。通知目前in-app，下次連線取得，沒有push/SMS承諾。
- UI顯式切換帳號、離線也清本機token且說明遠端撤銷未確認；不保存多密碼。獨立stores清單保留零商品收藏；通知可讀。商品revision409保留輸入，顯式丟棄／載入最新版；複製新批次用POST新product。可見頁30秒輪詢／foreground更新；vendor掃碼時暫停其catalog輪詢。
- 核銷expired/removed/失敗不顯示交付成功，缺貨與關店各有終態訊息。

## 權限與保存邊界

完整精確scope見[SQL011安全審查](SQL011_SECURITY_REVIEW.md)。只編寫SQL，不代表批准GRANT；不得擴DDL、role membership或直接業務表DELETE。API登入actor與共用MI信任邊界必须向批准者說明。

通知及terminal提出30天expiry，owner工具每輪各清最多100筆；這是待批准設計，尚未部署排程，不保證期限一到即物理清除。owner清PII涵蓋本人通知／terminal，清除其他通知的店家識別與文字；grace不得超過已批准30天。business retention及備份／外部圖片政策仍需定案，註冊／privacy-complete仍關閉。舊冪等key保留最小終態，清terminal後不能因此重建order。

## 驗證與剩餘

本地後端132項、前端單元12項通過；20個browser fixture場景及最新build結果見本輪安全checkpoint。測試不等於SQL程序實際執行。`backend/qa/terminal_rollback.py`新增schema011專用、預設plan、四個synthetic帳號、單一outer transaction必rollback；尚未執行真SQL。

未完成的驗收：通知INSERT失敗的真SQL原子回滾、雙連線競態、schema006–011實際編譯／權限、部署API/Android連線及實機相機。stores/products目前上限200，尚不是完整地理查詢／分頁；大型收藏列表可能需後續分頁。不新增外部超商adapter：全家官方樣本仍只是研究，7-ELEVEN仍blocked；兩者永遠資訊模式，不能預約核銷。
