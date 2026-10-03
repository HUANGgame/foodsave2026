# FoodSave 後端核心（0.2.0-core，尚未整合驗收）

此輪新增真正的 Azure SQL／SQL Server 程式路徑，**尚未連上資料庫實測**。App已有live API client與獨立demo入口，已通過mock合同，尚未連真SQL驗收。既有Library APK仍為demo。不要部署到既有WiFi資料庫；僅限新建FoodSave專用DB。

## 執行需求

- Python 3.12、FastAPI 0.141.1、Uvicorn 0.52.1、SQLAlchemy 2.0.43、pyodbc 5.2.0。
- Microsoft ODBC Driver 18、unixODBC及有效TLS信任鏈；建議Linux x86_64、Debian12容器。
- Dockerfile安裝ODBC前要求明確 `FOODSAVE_ACCEPT_ODBC_EULA=Y`，**本輪未接受該條款、未建置容器**。擁有者確認條款後才可執行。Microsoft安裝文件：https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
- 專用Azure SQL DB，runtime帳號僅限本schema需要的DML；migration用獨立DDL帳號。DB viewer是API中固定白名單，不是公開SQL執行器。檢視使用獨立FOODSAVE_VIEWER_ODBC_CONNECTION，未配置就503，不回退到runtime帳號。`infra/sqlserver/viewer-role.sql`為欄位級SELECT角色提案，實際建立持久權限須擁有者批准；尚未配置或DB實測。

## 可重現啟動（連線由環境安全注入）

在 `backend/` 下執行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# 先以受控migration帳號注入FOODSAVE_ODBC_CONNECTION，勿在shell history明寫密碼。
.venv/bin/python -m foodsave.migrate
# 初始化管理員／商家，密碼從互動式隱藏輸入讀取，不提供預設帳密。
.venv/bin/python -m foodsave.cli create-user --role admin
.venv/bin/python -m foodsave.cli create-user --role vendor
# 換成專用runtime帳號；HTTPS由主機入口終止。
.venv/bin/uvicorn foodsave.api:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Migration在同一交易內執行，版本表記錄001/002/003；啟動web不自動改schema。`/health/live`不連DB；`/health/ready`檢查最新migration。Azure休眠恢復40613只有readiness做最多一次1秒後重試；寫入遇資料庫錯誤回503與Retry-After，不自動重跑副作用。連線池5+5、連線逾時10秒、pool_recycle300秒，沒有keepalive背景查詢。生產readiness若密集查DB可能影響休眠，部署時應改用不持續喚醒DB的策略並驗證；不得以健康檢查刻意維持DB常醒。

管理頁 `/admin`：登入後可看白名單資料、建立店家／獎品／手動次數，以及EXP設定。Session只保存在頁面記憶體，重新載入需重登入；伺服器存token雜湊，12小時到期，登出撤銷。表格以textContent顯示；不顯示密碼hash／session／取貨或券碼；伺服器每次檢查admin角色。沒有外部公開連結，未部署。

## 已實作API

- `POST /auth/register|login|logout`、`GET /me`；公開註冊固定consumer；vendor/admin僅受控CLI建立。
- `GET /products`；`POST /reservations`、`POST /reservations/{id}/cancel`、`GET /reservations`。
- 商家 `POST /vendor/products`、`PUT /vendor/products/{id}`、`GET /vendor/reservations`、`POST /vendor/reservations/{id}/complete`。商品編輯需原revision；下單快照不追改。
- `PUT /favorites/{store_id}`、`POST /reservations/{id}/review`。已領取本人限一次評論；EXP來源唯一。
- `POST /draws`、`GET /draws`：後端權重抽獎，次數／獎品／結果／券同一交易；歷史可恢復結果。消費者不拿到weight；沒有種入假獎品、假券或品牌合作。
- 管理員 `POST /admin/stores|prizes|spin-grants`、`PUT /admin/exp-rules|ranking-rules`、`GET /admin/data/{table}?page=1`。

所有業務寫入需16–80字元 `Idempotency-Key`。客戶端對每個使用者意圖產生一次UUID；送出前保存key，503／逾時沿用原key重試，成功才清除。相同key不同內容409。資料庫以使用者更新鎖序列化重試，與交易同時記錄回覆。不得以新key自動重試抽獎。App已實作持久pending key／內容hash；未保存token或password。轉盤重開可讀回歷史，需真環境及Android驗收。

密碼用隨機salt+scrypt；登入／註冊有DB共享限速。預設不信任轉送IP，Azure入口部署前須限定可信代理並驗證真實client IP；目前同一代理後用戶可能共用限速。不以任意X-Forwarded-For繞過限制。

## 排程

```bash
python -m foodsave.cli expire
python -m foodsave.cli settle-week
```

expire每次最多100筆，逐筆交易並與核銷競爭。建議每分鐘一次並監控積壓；現階段排程未啟動。週結算以DB UTC時間轉Asia/Taipei，處理剛結束的一週；同分依user_id穩定排序，預設第1名3抽、2–10名2抽、11–50名1抽。以sp_getapplock與唯一來源防重發；建議UTC星期日16:05執行，重跑安全。grant有效至下一個台北週界；這項有效期／同分排序是實作暫定值，營運批准前不得宣稱正式規則。最大10000名，規模擴大前需壓測與分批設計。漏掉一整週需補結算功能，目前僅上一週。

## 測試分類與剩餘工作

```bash
python -m pytest -q
```

單元與FastAPI TestClient使用mock，不使用SQLite，也不證明SQL鎖／交易語法可用。真SQL驗收尚缺：migration套用／重跑、跨帳號／跨店、最後一份並發、核銷取消競爭、抽獎重試與券恢復、週結算重跑、服務重啟一致性。

本輪不是正式完整後端：仍缺真環境App串接驗收、native流暢度、後端附近查詢／完整分頁、帳號恢復／最終資料抹除、券兌換與實體獎品履約、圖片上傳、完整管理編輯與DB唯讀帳號的配置驗收、監控備份還原。沒有正式獎品或EXP值，EXP預設停用。正式可用前必須補齊並驗收。

追加API：GET /prizes、/favorites、/stores/{id}/reviews、/vendor/catalog，以及POST /account/deletion-requests（202受理／停用，不是假稱完成抹除）。公開註冊預設關閉，營運與隱私資料批准後才設定FOODSAVE_REGISTRATION_ENABLED=true。

安全補強：新增公開 `/account` 刪除／查詢頁、POST /account/deletion-request（需DELETE確認）、POST /account/deletion-status（皆需本人帳密）、GET /privacy。runtime新增deletion_requests的SELECT需求；schema不變。公開註冊還要求FOODSAVE_OPERATOR_NAME／FOODSAVE_PRIVACY_CONTACT／FOODSAVE_RETENTION_SUMMARY均已設定。最終資料抹除仍未實作。
