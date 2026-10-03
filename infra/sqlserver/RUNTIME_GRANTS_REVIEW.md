# Runtime 最小權限模板（準備完成，未執行）

`runtime-grants.review.sql` 只供既有owner於專用foodsave資料庫使用。替換所有已批准的runtime名稱、Object ID與Application ID後，再核對身分；不將真實雲端識別資料提交公開repo。模板預設因placeholder停止，需005已套用；遇既有角色／直接權限／身分不符即回滾，由owner審查，不自動擴權。

SQL Server欄位層級權限不支援INSERT，因此仍拒絕runtime對deletion_requests底層表INSERT/UPDATE/DELETE與owner欄位讀取；僅授id,user_id,state讀取。

使用者其後明確批准專用申請程序。005新增 `dbo.submit_deletion_request`，只接受request_id及user_id兩個UUID參數，要求既有交易；固定state=requested、approved_for_erasure=0，其餘批准／清除欄位NULL。沒有動態SQL或EXECUTE AS；透過相同dbo ownership chain進行單一INSERT，不授runtime基表寫權。API單點改為EXEC，原先帳密驗證、用戶鎖、重送返回同一ID、取消預約、停用與撤銷session保持在同一交易。

第一次授權用完整模板；若先前最小權限已套用，用 `runtime-grant-005.review.sql` 審查新增唯一EXECUTE權限與維持的DENY。順序為owner套用005 → 確認程序同dbo ownership chain → 明確批准的runtime grant → 新runtime ZIP部署 → readiness與有效權限／申請流程實測。不要再對底層表授INSERT。

**本輪只建立程式與部署材料，未執行migration／GRANT／實際刪除。** 惡意批准欄位API測試會422；靜態測試核對程序參數／固定值與grant範圍。SQL runtime無法SELECT批准欄位、不能直接INSERT或UPDATE，以及ownership chain可正常EXEC，都仍須部署端使用隔離fixture交易實測，不能由mock推定通過。

UPDATE已縮至實際改寫欄位；DELETE僅session登出、取消收藏、管理員重配排行規則。沒有db_owner、DDL、schema全域權限、GRANT OPTION、永久刪除或其他資料庫存取授權。audit僅INSERT；獨立viewer未納入。部分目前SELECT *查詢需表級SELECT；登入／跨用戶角色仍由API強制，不是SQL row-level security。

腳本只檢查本身的direct權限及角色；owner仍須確認public／群組／既有登入沒有其他繼承權限，不能從「未新增其他DB權限」推論原本絕無其他DB存取。Entra解析失敗須停止，不得自動增加Directory Readers。sp_getapplock預設public principal，未新增廣泛EXECUTE授權。

本輪只完成程式讀寫盤點與靜態allowlist檢查；SQL語法執行、有效權限與業務API實測仍待owner完成。

官方依據：[GRANT object permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-object-permissions-transact-sql)、[CREATE USER](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql)。

身分校驗修正：建立時FROM EXTERNAL PROVIDER WITH OBJECT_ID使用managed identity的Object ID精確解析；service principal在sys.database_principals的SID則對應Application ID。因此原本把SID與Object ID比較會誤擋並rollback。現在核對名稱、type E、EXTERNAL authentication及Application ID轉binary(16)，未移除guard。owner必須先以只讀Entra查詢確認Object ID與Application ID屬於同一已批准身份。public模板以三個不同placeholder表示，不能混用或猜測SID。

官方依據：[Microsoft Azure SQL：WITH OBJECT_ID與service principal SID](https://techcommunity.microsoft.com/blog/azuresqlblog/create-sql-logins-and-users-for-nonunique-microsoft-entra-principals-with-object/4106363)。

最小只讀核對查詢见runtime-identity-check.readonly.sql：只取name/type/authentication、SID bytes/hex/GUID與預期Application ID轉換值，不讀業務資料。rollback後無principal列屬預期，不能從不存在的SID推論端序問題。[CREATE USER官方範例K](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql)亦明確以service principal client/Application ID建立SID。
