# Azure SQL 相容測試環境

**狀態：設定檔已備妥，尚未啟動或通過 DB 測試。** 2026-10-03 此環境拉取 Microsoft SQL Server 映像時回覆 Forbidden。不得把 Compose 語法檢查視為資料庫驗證。

正式資料庫已選 Azure SQL；此配置僅供本地 SQL Server Developer 相容測試，與既有 WiFi 資料庫完全分離。API、migration、角色與交易核心尚待實作。沒有可登入的管理網頁或 DB 查看連結。

## 本地啟動（映像可下載後）

從 repository 根目錄執行，需 Docker Compose、x86_64 及足夠記憶體。只建立本地暫時密碼，不建立正式帳號或簽署金鑰：

```bash
FOODSAVE_ENV_FILE=$(python3 infra/sqlserver/make-test-env.py)
docker compose --env-file "$FOODSAVE_ENV_FILE" -f infra/sqlserver/compose.yaml up -d --wait
docker compose --env-file "$FOODSAVE_ENV_FILE" -f infra/sqlserver/compose.yaml ps
```

DB僅綁定 `127.0.0.1:14339`；不對外公開。SA僅用於隔離測試初始化，未來API需独立最小權限帳號。沒有掛載宿主資料夾或持久卷；stop/start保留此容器資料，down刪除容器即丟棄測試資料。這不是備份方案。

暫停保留測試資料：

```bash
docker compose --env-file "$FOODSAVE_ENV_FILE" -f infra/sqlserver/compose.yaml stop
```

完成測試後，只清除此專案的暫存容器與臨時密碼（會刪除此容器測試資料）：

```bash
docker compose --env-file "$FOODSAVE_ENV_FILE" -f infra/sqlserver/compose.yaml down
rm -- "$FOODSAVE_ENV_FILE"
```

勿把 `.env` 內容、`docker inspect` 的環境值或展開後的 Compose 設定貼進聊天／報告。憑證檔只能由擁有者讀寫。

## 正式 Azure 邊界

使用者透過安全通道配置專用 Azure SQL database；不在聊天傳密碼、不連用既有 WiFi DB。預計使用 SQLAlchemy + pyodbc／Microsoft ODBC Driver 18。正式連線需加密並驗證憑證，不能套用本地 healthcheck 的 `-C` 信任本機測試憑證設定。

本地 SQL Server 通過不能代替 Azure 環境驗收：仍須實測 migration、有限權限帳號、並發交易、服務重啟一致性與備份還原。SQL Server 映像標籤目前尚未鎖定digest，首次成功下載並驗證後再固定已測digest。
