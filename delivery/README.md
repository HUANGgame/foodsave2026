# 部署交接包（尚未正式驗收）

- `foodsave-f1-code.zip`：F1 Linux Code Python3.12後端／管理頁，啟動命令 `sh startup.sh`。
- `foodsave-owner-migrations.zip`：既有Entra owner專用migration／預設停用清除工具（含001–005；部署端已確認套用），**不可部署進runtime**。
- `checksums.json`：固定檔案大小、SHA-256與ZIP內容清單。

包內沒有憑證、.env、實際雲端資源設定或App測試包。部署端已確認runtime部署及schema001–005，SQL回滾／並發與QA清理通過；此ZIP仍不代表App端到端或實機全部驗收。實際帳戶／主機／權限由擁有者安全配置；零付費限制，禁止自动升級或建立付費服務。詳見 `docs/F1_DEPLOYMENT.md`。本輪僅文件更新，兩份ZIP與校驗值未改；QA工具獨立交付、不加入runtime。CI沒有保留可下載APK；下一個真API測試包與私有交付方式仍須依[最小驗收方案](../docs/LIVE_APP_ACCEPTANCE.md)確認。
