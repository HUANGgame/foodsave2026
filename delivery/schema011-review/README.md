# Schema011 review-only bundles

未部署、未執行migration或GRANT。既有delivery根目錄7824868套件保持原狀；不得將新版runtime配舊005資料庫或舊UI。

Source commit: `4493ad5271ad514489023b85458120284323f0b6`。完整entries／bytes／SHA256見[verification.json](verification.json)。owner包附schema011回滾QA腳本（預設plan），不會在startup執行。

先審查[精確SQL scope](../../docs/SQL011_SECURITY_REVIEW.md)，父流程取得action-time批准後，owner依006→007→008→009→010→011順序；再單獨審核既有MI的指定grant。本文不是部署授權。

QA計數修補：notification closure以COUNT(id)，rollback各表以其已授權且非NULL的id/user_id計數，避免column-only SELECT下的COUNT(*)觸及DENY欄位。runtime包內容／hash未變，沒有grant/schema變更。

007編譯修補：DROP CONSTRAINT敘述先賦nvarchar(max)變數，再EXEC(@statement)。相同限定favorites constraint，無schema/權限scope變更。Azure前次migration失敗；本地結構測試不等於新版TSQL編譯通過。
