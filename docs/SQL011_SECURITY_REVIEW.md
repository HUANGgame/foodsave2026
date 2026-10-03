# Schema011 action-time SQL安全審查（未執行）

目標：既有、已驗證Application ID SID的runtime managed identity，僅專用DB `foodsave`。公開腳本使用placeholder；實際MI名稱／Application ID只在私有部署交接核對。不得以顯示名稱猜SID，不新建principal。父流程須先取得本次action-time確認，再由既有owner执行。

## 精確新增權限

| 對象 | 權限 |
|---|---|
| dbo.stores | UPDATE(service_mode) |
| dbo.expire_reservation | EXECUTE |
| dbo.close_vendor_business | EXECUTE |
| dbo.report_stock_loss | EXECUTE |
| dbo.mark_notification_read | EXECUTE |
| dbo.notifications | SELECT(id,user_id,event_key,kind,body,created_at,read_at,expires_at) |
| dbo.reservation_terminals | SELECT(reservation_id,user_id,vendor_id,reason,previous_state,released_quantity,created_at) |

審查檔：`infra/sqlserver/runtime-grant-011.review.sql`。已在006審查的service_mode單欄包含於整份011，勿把兩份當兩次不同scope。favorites沿用原表既有SELECT/INSERT/DELETE，007只遷移store_id→vendor_id、PK/FK，不加grant。其他原權限維持，不使用db_owner/db_datawriter、角色新增、整表stores UPDATE、GRANT OPTION、DDL、users DELETE、直接business DELETE或新表直接DML。

## 程序可改／刪的固定範圍與強制條件

四程序均要求呼叫者已在active transaction（@@TRANCOUNT及XACT_STATE）、SET XACT_ABORT ON，不自行COMMIT，無動態SQL／EXECUTE AS。前三者以store transaction applock及product/order鎖序列化。

| 程序 | 條件、scope與副作用 |
|---|---|
| expire_reservation(reservation_id) | 指定一單，DB UTC已到期且waiting/legacy expired才執行；completed/cancelled及未到期拒絕。寫通知／terminal，waiting返quantity，legacy expired返0；scrub該order四種operation收據；只刪該order reviews/reservation。可作有界maintenance，不限caller customer |
| close_vendor_business(vendor_id) | 該user為vendor、inactive且已有requested刪帳申請；最多其唯一store。顧客與followers UNION去重通知，所有該店order終態release0，scrub相關收據；刪該店reviews/reservations、追蹤該vendor的favorites、products及store。無user DELETE，不自動PII完成 |
| report_stock_loss(vendor_id,product_id,expected_revision,expected_pending,actual_available) | 必須active vendor且擁有指定product的store；revision、waiting筆數完全一致，非NULL合法範圍。該product所有waiting單寫release0通知／terminal並刪reviews/orders；庫存覆為actual值、revision+1。不改其他product、無EXP/懲罰 |
| mark_notification_read(user_id,notification_id) | UPDATE只WHERE兩ID吻合，read_at COALESCE；沒有DELETE。重試不更換首次已讀時間 |

## Ownership chain及actor冒用界線

所有固定模組及資料表同dbo owner，靠SQL Server ownership chain允許上述有限業務DELETE；runtime沒有直接DELETE也**仍能透過程序觸發這些刪除**。grant稿檢查有效owner及無execute-as，異常停止；實際SQL QA要核對程序可執行但直接刪除無權限。

API的bearer session決定actor，StockLoss嚴格schema拒絕user_id/vendor_id/actor_id注入，產品ownership及terminal/inbox亦檢查。**共用MI不是每位app使用者的SQL身分**：能任意執行SQL的受害runtime可提供任意actor UUID，並可能濫用既有user/session/刪除申請權限。程序無法證明人類已輸入密碼；密碼驗證是API責任。這是現架構明確殘餘風險，不能說ownership chain解決了actor spoof或提供DB row-level tenant隔離。

## Migration／執行順序

既有001–005保留，owner依檔名字典序在同一migration transaction執行：
1. 006_store_service_mode.sql
2. 007_notifications_and_terminal_ledger.sql
3. 008_expire_reservation.sql
4. 009_close_vendor_business.sql
5. 010_report_stock_loss.sql
6. 011_mark_notification_read.sql

006多店／007無owner收藏preflight失敗須停，不能自動刪／改真資料。007含owner-only固定動態DDL，用於新增欄位後分開編譯及已知表constraint變更；runtime四程序無動態SQL。新API readiness要求011；新UI不得配舊005 API。收藏欄位變更不向後相容，切換須quiet window協調同版API/UI；此文件不授權部署或回滾DDL。

## 證據分層與負向測試

本地單元／SQL結構檢查：client actor欄位拒絕、其他user terminal/read拒絕、原key不重建order、loss pending/revision不符409、缺貨不返庫／EXP、expired用DB time／legacy不返第二次、XACT_ABORT及caller txn、不EXECUTE AS、不擴直接DELETE。這些不是SQL解析／鎖行為實測。

schema011回滾腳本新增wrong vendor404、changed pending409、未到期不expiry、completed不刪、late cancel/expiry不返庫、同key不重建、active vendor不能close、通知不可跨帳號已讀、closure follower去重、rollback零殘留。預設plan；待migration+grant另行批准後以既有受限MI執行。沒有觸碰真人資料，未執行。

仍待真SQL驗證：通知INSERT失敗時全交易rollback、相反競態順序／雙連線、程序編譯及ownership-chain執行效果。不得用本地fake交易測試宣稱這些已通過。
