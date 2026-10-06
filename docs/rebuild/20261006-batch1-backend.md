# 第一批：舊基線同帳號商家與自領防護

這是從已驗證 Git 基線 `610deaeda64ac62110dd3fbeeaa919d74152dbd0` 重建的後端程式，不是取回原環境未匯出成果，也未與三份缺失 Library ZIP 做內容比對。此批父提交為 `42a6f48b1541a1708ae91f25ca365b284c992166`。未重試 Library／Azure 受阻路徑，未部署、執行 migration 或修改資料庫權限。

## 實際修改與契約

- `POST /vendor/store`：接受 name、latitude、longitude 與 Idempotency-Key，owner_id 一律取已驗證 session 的 user ID；禁止 role、owner_id 或額外欄位注入。沿用資訊模式預設。重試原 key 回傳原結果；不同 key 再建店回覆 409。
- 保留 `users.role`、永久 ID、admin 權限與 session。authenticate 依 stores.owner_id 回傳 `is_vendor`；consumer 店主可以使用商家操作，舊 vendor 可執行顧客預約／取消／評論／抽獎。商家資料與寫入仍有 owner_id 範圍檢查，admin 專用路由未放寬。
- 自行開店沿用 mutate 的 user-row UPDLOCK/HOLDLOCK；管理員開店也先鎖 owner row 並檢查已有店家。既有 migration006 的 `ux_stores_single_owner` 唯一 filtered index 保持不變。這是設計與程式控制流程，不是已驗證 SQL 競態結果。
- 預約檢查店主；手輸／QR preview、直接完成、preview-confirm 核銷都拒絕自領。原成功快取回傳前重新檢查訂單顧客／店主，避免舊 cache 繞過自領及跨店限制；取消與 terminal 回覆依此次操作身分判斷，不再依互斥角色推定。
- 核銷成功相同 key 重試不重發 EXP；不同 key 或改走直接完成路由遇到已完成訂單會拒絕。亦禁止舊自領訂單取得評論獎勵與收藏自家店取得獎勵。這是 FoodSave 原生收藏，沒有修改全家收藏或其他暫停功能。
- 店家查詢／原生收藏目標、排行榜與管理員發放對象接受 consumer 或 vendor，避免新 consumer 店主不可見或舊 vendor 無法使用顧客獎勵。管理員本身未加入顧客／商家權限。
- `request_deletion` 對 consumer 店主也執行既有受限關店程序，避免刪帳留下營業資料；保留原本經密碼驗證的刪帳行為。開店本身不清 session。

## 新 migration 的界線

新增 `backend/migrations/013_store_capabilities.sql`，由本基線的 009／010 產生；兩個 ALTER PROCEDURE 的唯一業務差異是既有 `u.role='vendor'` 改為 `u.role IN ('consumer','vendor')`，原 owner_id、active、刪帳請求、交易、鎖、通知及清理條件保留。另先檢查既有唯一店主索引存在且啟用。

它不是缺失 ZIP 內的舊 013，沒有清 session、重綁 owner、批次更新 users、GRANT／REVOKE 或索引修正。舊 001–012 完全未改動。本次沒有執行任何 SQL；尚未證明新 SQL 可在 AzureSQL 編譯／執行，亦未驗證 runtime 實際權限。

自行開店在交易內要求 `013_store_capabilities.sql` migration 記錄，缺少則回覆 503。**此記錄只代表 migration runner 記錄，不代表整合測試已通過。**既有 health/ready 也不是本功能完整驗收訊號。

在 validation 庫完成真實 SQL、併發、權限與恢復驗證前不可視為可部署。未來部署也須先比對正式程序及 schema，處理可能存在的其他 013；不能只看編號便略過差異。若新 consumer 店家已產生，回退到舊後端／舊程序會失去對它們的完整支援，因此不能把程式 bundle 還原當成資料庫回退方案。

## 本次測試

使用隔離 venv 安裝 repository `backend/requirements-test.txt`，沒有變更依賴檔。完整命令：

```sh
PYTHONPATH=.:backend /workspace/foodsave-rebuild/venv/bin/python -m pytest -c backend/pytest.ini backend/tests -q
```

- 修改前：265 passed，1 warning。
- 本批最終：301 passed，1 warning，14.24 秒。紀錄：`/workspace/foodsave-rebuild/batch1-tests-final.log`。
- 新增 35 項 stateful service/API mock 與 SQL 文字契約案例：同 ID 開店與重試、session/admin 保留、跨店、缺 migration、欄位注入、自領手輸／QR、舊 cache、核銷與評論重播、失敗回滾、操作身分 terminal 等。其餘既有測試調整互斥角色假設與必要的 owner 欄位；刪帳測試新增 consumer 店主案例。
- `git diff --check` 通過。警告為 Starlette 對 httpx TestClient 的棄用提示；未更動依賴處理它。
- 全部結果屬本地單元／API／控制流程 double 及文字檢查，**不是 SQL migration、真實資料庫整合或併發測試**，也不是網頁端到端、APK build 或真機測試。

## 修改前備份與審查範圍

`/workspace/foodsave-rebuild/backups/batch1-before.bundle` SHA256：
`2220fa0cc8aa3695f8eb6f6b879caa3b2739046947d5eaa88bf9d23cfdf3a4be`

已通過 bundle verify，獨立還原至 `/workspace/foodsave-rebuild/batch1-restore` 並通過 fsck；253 檔逐檔符合 `backups/batch1-before-files.json`。每次覆寫另先複製到 `backups/edits/<批次>/` 並比对 SHA256。只讀檢查員核對備份及程式覆蓋風險後才可提交。

備份範圍是舊 Git 基線加第一階段文件，不包含正式 SQL、正式部署設定、最新 APK 或未匯出成果。備份與執行 log 目前僅保存在本次環境。

## 後續未完成

店址移動與訂單鎖定、附近一公里穩定分頁及 200 筆截斷修正、0.4.10 前端還原比對、我要上架 UI、Android APK／簽章／真機驗證、Drive 上傳與正式部署仍未完成。沒有因本批後端測試通過而宣稱正式商家功能已啟用。
