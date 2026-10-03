# 部署交接包（尚未正式驗收）

- `foodsave-f1-code.zip`：F1 Linux Code Python3.12後端／管理頁，啟動命令 `sh startup.sh`。
- `foodsave-owner-migrations.zip`：既有Entra owner專用migration／預設停用清除工具（含待審查004），**不可部署進runtime**。
- `checksums.json`：固定檔案大小、SHA-256與ZIP內容清單。

包內沒有憑證、.env、實際雲端資源設定或App測試包。只是可審查部署材料，不代表服務上線、SQL驗收或Android實機通過。實際帳戶／主機／權限由擁有者安全配置；零付費限制，禁止自动升級或建立付費服務。詳見 `docs/F1_DEPLOYMENT.md`。
