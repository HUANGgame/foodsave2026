# Runtime 最小權限模板（準備完成，未執行）

`runtime-grants.review.sql` 只供既有owner於專用foodsave資料庫使用。替換所有已批准的runtime名稱及object ID後，再核對身分；不將真實雲端識別資料提交公開repo。模板預設因placeholder停止，需004已套用；遇既有角色／直接權限／身分不符即回滾，由owner審查，不自動擴權。

重要阻擋：SQL Server欄位層級權限不支援INSERT。因此未授deletion_requests INSERT，以免runtime在新列指定approved_for_erasure或其他owner欄位。只授id,user_id,state讀取，明確拒絕INSERT/UPDATE/DELETE與owner欄位讀取。現在刪除申請API會在INSERT回滾，不能宣稱刪除受理流程完成。

最小後續方案：owner建立僅暴露id,user_id的同owner view，runtime的單一INSERT改指該view，僅授view INSERT。底層表繼續拒絕寫入；default強制requested／未批准／NULL owner時間。也可改用固定參數procedure。兩者都需另行審查schema安全邊界、新migration及runtime重新部署，本輪未實作或套用。

UPDATE已縮至實際改寫欄位；DELETE僅session登出、取消收藏、管理員重配排行規則。沒有db_owner、DDL、schema全域權限、GRANT OPTION、永久刪除或其他資料庫存取授權。audit僅INSERT；獨立viewer未納入。部分目前SELECT *查詢需表級SELECT；登入／跨用戶角色仍由API強制，不是SQL row-level security。

腳本只檢查本身的direct權限及角色；owner仍須確認public／群組／既有登入沒有其他繼承權限，不能從「未新增其他DB權限」推論原本絕無其他DB存取。Entra解析失敗須停止，不得自動增加Directory Readers。sp_getapplock預設public principal，未新增廣泛EXECUTE授權。

本輪只完成程式讀寫盤點與靜態allowlist檢查；SQL語法執行、有效權限與業務API實測仍待owner完成。

官方依據：[GRANT object permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-object-permissions-transact-sql)、[CREATE USER](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql)。
