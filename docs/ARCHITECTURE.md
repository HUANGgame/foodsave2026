# 系統與資料表關係（目前程式）

來源：migration001–011。本圖是新版source設計：部署端先前確認001–005，006–011尚未套用或真SQL驗證。精確權限與ownership-chain邊界見SQL011_SECURITY_REVIEW.md。

```mermaid
flowchart TD
 App[Next App + Capacitor Android] -->|HTTPS bearer memory session| API[FastAPI]
 Admin[管理頁 /admin] -->|HTTPS admin session| API
 API --> Auth[密碼 / sessions / 角色]
 API --> Tx[庫存 / 預約 / 核銷 / 評論]
 API --> Draw[冪等抽獎 / EXP]
 API --> Writer[(Azure SQL runtime identity)]
 API -->|固定欄位 SELECT| Viewer[(Azure SQL viewer identity)]
 Job[expire / settle-week CLI] --> Writer
 Migrator[手動 migration identity] --> Writer
 App --> Map[OSM底圖 / Google Maps步行導航]
 App --> Photo[已授權HTTPS圖片來源]
```

正式模式API失敗不切回demo。登入token只在記憶體；裝置只保存未完成操作識別碼與內容雜湊。後端token存hash，會話12小時；刪除申請立即停用帳號／撤銷session，但資料抹除仍待營運流程。新版schema011及新增權限尚未套用。

```mermaid
erDiagram
  users ||--o{ sessions : "user_id"
  users |o--o| stores : "owner_id"
  stores ||--o{ products : "store_id"
  users ||--o{ reservations : "user_id"
  products ||--o{ reservations : "product_id"
  users ||--o{ request_results : "user_id"
  users ||--o{ exp_events : "user_id"
  users ||--o{ favorites : "user_id"
  users ||--o{ favorites : "vendor_id"
  users ||--o{ notifications : "user_id"
  users ||--o{ reservation_terminals : "user_id"
  reservations ||--o{ reviews : "reservation_id"
  users ||--o{ reviews : "user_id"
  users ||--o{ spin_grants : "user_id"
  users ||--o{ draws : "user_id"
  spin_grants ||--o{ draws : "grant_id"
  prizes ||--o{ draws : "prize_id"
  draws ||--o{ coupons : "draw_id"
  users ||--o{ coupons : "user_id"
  users ||--o{ audit_logs : "actor_id"
  weekly_settlements ||--o{ weekly_rankings : "week_key"
  users ||--o{ weekly_rankings : "user_id"
  users ||--o{ deletion_requests : "user_id"
  users {
    varchar id
    nvarchar email
    varchar password_hash
    varchar role
    bit active
    datetime2 created_at
  }
  sessions {
    char token_hash
    varchar user_id
    datetime2 expires_at
    datetime2 created_at
  }
  rate_limits {
    char bucket
    datetime2 window_start
    int attempts
  }
  stores {
    varchar service_mode
    varchar id
    varchar owner_id
    nvarchar name
    decimal latitude
    decimal longitude
  }
  products {
    varchar id
    varchar store_id
    nvarchar name
    nvarchar photo_url
    int original_price_minor
    int sale_price_minor
    int available_quantity
    datetime2 pickup_deadline
    bit active
    int revision
  }
  reservations {
    varchar id
    varchar user_id
    varchar product_id
    varchar state
    int quantity
    nvarchar snapshot
    char pickup_code_hash
    datetime2 created_at
    datetime2 expires_at
    datetime2 completed_at
  }
  request_results {
    varchar user_id
    varchar operation
    varchar request_key
    char fingerprint
    nvarchar response
    datetime2 created_at
  }
  exp_rules {
    varchar event
    int amount
    bit enabled
  }
  exp_events {
    varchar id
    varchar user_id
    varchar event_key
    int amount
    datetime2 occurred_at
  }
  favorites {
    varchar user_id
    varchar vendor_id
  }
  notifications {
    varchar id
    varchar user_id
    varchar event_key
    varchar kind
    nvarchar body
    varchar related_vendor_id
    datetime2 created_at
    datetime2 read_at
    datetime2 expires_at
  }
  reservation_terminals {
    varchar reservation_id
    varchar user_id
    varchar vendor_id
    varchar reason
    varchar previous_state
    int released_quantity
    datetime2 created_at
    datetime2 expires_at
  }
  reviews {
    varchar reservation_id
    varchar user_id
    int rating
    nvarchar body
    datetime2 created_at
  }
  spin_grants {
    varchar id
    varchar user_id
    varchar source_key
    int remaining
    datetime2 expires_at
    datetime2 created_at
  }
  prizes {
    varchar id
    nvarchar name
    varchar kind
    int weight
    int remaining
    bit enabled
    datetime2 expires_at
    nvarchar terms
    int discount_percent
  }
  draws {
    varchar id
    varchar user_id
    varchar grant_id
    varchar prize_id
    nvarchar prize_snapshot
    datetime2 created_at
  }
  coupons {
    varchar id
    varchar draw_id
    varchar user_id
    varchar code
    varchar state
    datetime2 expires_at
  }
  audit_logs {
    varchar id
    varchar actor_id
    varchar action
    varchar target_id
    datetime2 created_at
  }
  ranking_rules {
    int start_rank
    int end_rank
    int spins
  }
  weekly_settlements {
    char week_key
    datetime2 starts_at
    datetime2 ends_at
    datetime2 completed_at
  }
  weekly_rankings {
    char week_key
    varchar user_id
    int rank
    bigint exp
    int spins
  }
  deletion_requests {
    varchar id
    varchar user_id
    varchar state
    datetime2 requested_at
    datetime2 completed_at
    bit approved_for_erasure
    datetime2 pii_cleared_at
    datetime2 purge_after
    varchar policy_version
  }
  erasure_receipts {
    varchar request_id
    varchar policy_version
    datetime2 completed_at
    datetime2 expires_at
  }
```

另有migration runner建立的schema_migrations(version, applied_at)。request_results保存冪等操作結果；預約取貨碼只向本人API回傳，DB viewer不公開它。ranking_rules與exp_rules為配置表，以程式套用，不捏造不存在的FK。rate_limits為匿名雜湊bucket，不儲存原始IP。

004新增owner清除狀態及無user FK的限時回執。owner工具預設停用；清除前公開狀態可用原密碼，清除密碼後由owner依回執協助。真SQL清除與外部备份流程未驗證，詳見ERASURE_RUNBOOK。

005：API既有交易內呼叫dbo.submit_deletion_request(request_id,user_id)，程序固定未批准及空清除欄位。runtime僅此procedure EXECUTE，不能直接寫申請表或讀owner欄位；不自動執行erasure。

006保證非NULL owner至多一store。007 terminal.reservation_id刻意無order FK，vendor_id及notification.related_vendor_id也無vendor FK；可先移除業務資料，再依owner policy清除識別。008–011固定procedure透過同dbo ownership chain操作，runtime不取得直接業務DELETE。
