# 食在可惜 FoodSave

Next.js＋Capacitor Android 與 FastAPI／Azure SQL 的惜食服務開發版本。**尚未完成正式環境與 Android 裝置驗收，不能當作 production-ready 版本。**

## 已實作

- 明確分離本機demo與live API模式，live失敗不回退假資料。
- 消費者／商家／管理角色、預約庫存、核銷、收藏評論、EXP與後端決定結果的轉盤。
- 管理頁、冪等交易程式、週結算、帳號刪除申請與登入撤銷。
- Android compile/target36、unsigned release AAB設定；未附舊APK或測試包。

刪除申請目前代表停用及待處理，**不代表完成資料抹除**。SQL並發、migration、權限與Android安裝／流暢度仍需實際環境驗證。測試商家、測試資料及mock不是營運資料。

## 本機開發

```bash
npm ci
npm test
npm run dev
```

預設demo；live模式設定 `NEXT_PUBLIC_APP_MODE=live` 與實際 `NEXT_PUBLIC_API_BASE_URL=https://...`。登入token只留記憶體，重載需登入；本機只保存未確認操作識別碼與內容雜湊。

後端安裝／測試：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

不要將任何密碼、token、.env或簽署金鑰加入版本庫。註冊預設關閉，須先完成營運者、隱私聯絡與保存政策配置。

## 部署材料與文件

- [固定部署ZIP與校驗資料](delivery/README.md)：程式包和owner migration包分開，無秘密或實際帳戶設定。
- [F1部署手冊](docs/F1_DEPLOYMENT.md)、[後端說明](backend/README.md)。只允許經核准的硬性零付費方案，不自動升級或開付費服務。
- [操作手冊](docs/OPERATIONS_DRAFT.md)、[架構與ER](docs/ARCHITECTURE.md)、[正式驗收矩陣](docs/ACCEPTANCE_MATRIX.md)。

目前驗證分為單元／API mock、瀏覽器mock合同與建置檢查；不等於真SQL或Android測試。部署前由擁有者配置專用DB與最小權限。GitHub分支保存開發成果，main不自動合併。
