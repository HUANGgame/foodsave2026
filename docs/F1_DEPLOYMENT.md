# F1 Linux Code 部署交接（尚未部署）

唯一目前候選：使用者核准的Azure App Service F1 Linux Code／Python3.12／EastAsia，portal估價0美元。**永遠不付費**：不升級、不用學生credit抵付、不建立ContainerApps／付費Jobs／Registry。原ContainerApps template已作廢，不得執行。新SQL僅限專用`foodsave`，free offer過量必須pause，禁止付費overage。部署負責人負責核實及建立，這個工作區未provision。

## 可交給部署步驟的檔案

- `artifacts/foodsave-f1-code.zip`：requirements.txt與startup.sh在ZIP根目錄，僅包含API／admin／必要模組。沒有migration、Dockerfile、App測試輸出、.env、秘密或.test API設定。
- `artifacts/foodsave-owner-migrations.zip`：獨立migration 001–005與owner_migrate.py、CLI；不放進App Service。hash／檔案清單見`artifacts/f1-package-verification.json`。
- 重建：`python3 scripts/package-f1.py`。未上傳Library或交付使用者測試包。

## App Service設定提案

Python3.12 Code模式、F1、Insights/Defender關閉。啟動命令 **`sh startup.sh`**。ZIP部署需平台Oryx安裝requirements，設定`SCM_DO_BUILD_DURING_DEPLOYMENT=true`；不使用自訂Docker／Registry，不啟用CD basic auth。實際部署請部署負責人透過已核准的Entra途徑完成，這裡沒有取得publishing password。

啟動單worker、port8000、concurrency16；沒有背景排程或啟動DB查詢。SQLAlchemy使用NullPool且關閉pyodbc pooling，釋放閒置連線，不為了避免SQL休眠而持續ping。

ODBC不可假定：先在App Service私有SSH執行 `python -m foodsave.diagnose`，它只列Python與已安裝driver，不印環境或token、不連DB。確認17或18實際存在後才設定`FOODSAVE_ODBC_DRIVER`。缺driver則停止，需確認官方Code image適配／安裝與EULA；startup不偷偷apt安裝或接受條款。

確認system-assigned managed identity與foodsave專用DML授權後，安全設定：

- `FOODSAVE_SQL_SERVER`：部署負責人已核實的Azure SQL hostname。
- `FOODSAVE_SQL_DATABASE=foodsave`：程式拒絕其他DB名稱。
- `FOODSAVE_ODBC_DRIVER`：實際診斷列出的`ODBC Driver 18 for SQL Server`或17。
- `FOODSAVE_REGISTRATION_ENABLED=false`：營運隱私資料未齊前保持關閉。
- `FOODSAVE_ALLOWED_ORIGINS`：僅實際App／網站origin。Android是`https://localhost`；管理頁同origin不需CORS。

在此路徑不要設定舊的`FOODSAVE_ODBC_CONNECTION`覆寫值。ODBC使用`Authentication=ActiveDirectoryMsi;Encrypt=yes;TrustServerCertificate=no`，實際MI連線仍須部署後驗證。runtime不得為db_owner，沒有CREATE/ALTER/DROP權限。授權需求為實際業務表SELECT/INSERT/UPDATE/DELETE、schema_migrations僅SELECT，及transaction-owned sp_getapplock可用性驗證。**本輪沒有執行GRANT**。

DB viewer仍要求獨立`FOODSAVE_VIEWER_ODBC_CONNECTION`與欄位SELECT角色，未配置回503、不回退runtime。新的viewer身份／權限不在現有runtimeRW授權之內，需部署負責人另確認；不可為了顯示連結而公開SQL或使用owner身份。

## 擁有者migration

在已有Azure CLI登入、Python3.12及核准ODBC driver的私人環境解壓owner包，安裝requirements後執行：

```bash
python owner_migrate.py --server YOUR_VERIFIED_SERVER.database.windows.net --database foodsave --driver 'ODBC Driver 18 for SQL Server'
```

工具只使用既有登入取得SQL短期access token，直接放記憶體連線，不寫入檔案或輸出。既有Entra owner需已具foodsave DDL權限；不新增權限、不登入替代帳號、不提升runtime。只操作指定新DB，migration重跑按version表略過。部署包不帶此工具。SQL與token實際連線未驗收。

## F1例行整理與限制

管理頁「整理逾期與上週排名」呼叫`POST /admin/maintenance`：需admin、共享限速，最多處理100筆逾期；週結算用SQL交易／應用鎖／唯一週別防重發。回應遺失可重試，已結算不再發獎。没有付費排程，沒有聲稱休眠期間會自動執行。上一週以外的漏結算目前不自動追補，需後續受控處理。

部署負責人提供的F1限制：60 CPU分鐘/日、3 CPU分鐘/5分鐘、1GB RAM、1GB storage、165MB outgoing/日；超額可403硬停、會休眠、無SLA，不能承諾一直可用。上限需以實際portal為準，不為避免停機升級付費。大量排行結算／圖片流量可能超過免費額度，需在真環境量測並停止超額工作；不擴功能。

## 部署後必要驗收

先`/health/live`（不碰DB），私有driver診斷，owner migrations，再`/health/ready`（新版檢查005）。不以頻繁SQL readiness探針維持DB清醒。驗runtime不能DDL、viewer不能寫／讀敏感欄位；最後庫存並發、抽獎重試、週結算重跑、App跨帳號、Android啟動仍待實測。未有actualhost時不改APK網址，也不交付fixture APK。

## 已收到的F1資源（部署負責人核實，尚未部署程式）

WebApp `YOUR_APP`，RG `YOUR_RESOURCE_GROUP`，F1 Python3.12 Linux。實際HTTPS網址：
`https://YOUR_APP.azurewebsites.net`

非秘密設定已記錄於 `infra/f1-public-config.json`，尚未寫入Azure。App前端僅待後端驗證後以此URL重建，沒有再打包.test APK。SQL建立仍待使用者條款確認。未有安全部署通路前不傳access token、publishing profile或基本帳密；ZIP只在本機，未上傳Library。

本輪檢查：26項後端單元／mock通過；部署ZIP解壓後API載入、/health/live與/admin基本HTTP檢查通過。這不是Azure/ODBC/SQL驗收。

## External Git子目錄部署：僅分析，尚未套用

Repository根目錄是Next.js，Python的requirements在backend；不能只改startup就假定Oryx會正確偵測Python。Kudu官方歷史文件提供`.deployment`的`project=子目錄`，但其文件例子針對Node/PHP/ASP.NET，不足以證明目前F1 Linux Python3.12/Oryx路徑已驗證：https://github.com/projectkudu/kudu/wiki/Customizing-deployments

此外backend目錄含owner_migrate.py與migrations，與已過濾的runtime ZIP不同。若部署負責人確認External Git路徑可用，應明確確認建置根目錄、部署輸出內容及startup工作目錄；保留owner工具隔離。這輪不盲目新增.deployment、不觸發部署。ZIP扁平根目錄的`sh startup.sh`不能未驗證就套用整個repo根目錄。

005交接：owner先套用005，再依已批准的runtime身分審查infra/sqlserver/runtime-grant-005.review.sql，最後部署新的runtime ZIP。新增唯一dbo.submit_deletion_request EXECUTE；禁止基表INSERT及owner欄位存取，不可授schema廣泛EXECUTE。舊084 runtime與此API呼叫不同，必須更新；未在本工作區套用任何grant。
