# 安全補強階段：證據與剩餘缺口

這是程式與mock驗證，**不是正式環境全部驗收通過**。

本階段：33個後端單元／API mock、10個前端單元、6個App browser合同通過；新增公開帳號頁的browser mock也通過。涵蓋刪除重試／查詢、確認勾選、密碼欄清除、跨用戶取消拒絕、角色限制、登入世代隔離與抽獎重試。未執行真SQL資料變更。

## 已修正

- 刪除回覆遺失：可在後端`/account`以原帳號密碼查詢或重送，受理後不依賴已撤銷的session，不發新token。
- 刪除待領取訂單：同一交易內按商品／預約順序鎖定、重查waiting後取消並返還；與核銷競爭的真正效果待SQL驗證。
- 重複刪除返回同一申請，不重複返還庫存。
- 公開註冊除開關外，也要求後端營運者／聯絡／保存說明已配置。
- 晚到的旧登入回覆不能清掉新登入token；session變更後不送出尚未發出的舊意圖。

## 本次部署差異

新ZIP包含`/account`網頁、刪除申請與狀態API、`/privacy`公開配置接口及以上後端修正。現有001/002/003 SQL migration未改，**不需要新增schema版本**。runtime需要對`deletion_requests`增加SELECT（原建議僅INSERT）；仍限定同一專用DB及既有runtime身份，由部署負責人確認／套用，不由此工作區執行GRANT。

新增非秘密環境變數：`FOODSAVE_OPERATOR_NAME`、`FOODSAVE_PRIVACY_CONTACT`、`FOODSAVE_RETENTION_SUMMARY`。未填時`/privacy`標draft、公開註冊保持關閉。不得用測試內容假裝正式政策。

## 全範圍目前證據

| 範圍 | 已有證據 | 真正验收狀態 |
|---|---|---|
| UI／四分頁／照片／地圖 | 靜態建置、browser合同與demo回歸紀錄 | GPS允許／拒絕與地圖互動未完成Android驗收 |
| 登入／角色／session | 單元與API mock拒絕測試、前端session隔離 | 真DB登入、跨裝置、代理節流未驗 |
| 商品／預約／取消／核銷 | 前後端合同、快照單元、程式交易鎖 | SQL最後庫存並發、取消核銷競爭、重啟一致性未驗 |
| 收藏／評論／EXP | 原demo邏輯與API程式／部分mock | 真DB唯一事件、彙總、營運EXP值未驗／待決策 |
| 週排行 | 台北週界單元、可重入結算程式 | 真DB結算重跑、有效期／同分規則批准待辦 |
| 轉盤／獎品 | mock重試一次扣除、關閉恢復、減少動畫與落點檢查 | 真SQL次數／獎品交易、真獎品履約、Android FPS未驗 |
| 刪除帳號 | 受理／停用／查詢／返還程式與mock | 最終抹除／保留例外／備份清除流程尚未實作；政策待批准 |
| 隱私與公開註冊 | 草案頁／配置接口／未配置拒絕註冊 | 真營運資料、公開政策及Data safety未完成 |
| 管理／DB查看 | 本地HTTP與browser mock、白名單／角色程式 | Azure部署未驗、viewer未批准；可先由owner用SQL Portal |
| Azure SQL／migration | SQL檔及owner工具已寫、未連真DB | 執行環境網路准入／owner路徑受阻；migration和GRANT未執行 |
| F1主機部署 | 受控ZIP、校驗碼、根目錄requirements／startup | 主機建立不等於程式部署；部署通路仍由負責人確認 |
| APK／AAB | API36編譯、debug簽章／unsigned、manifest／ZIP／bundletool | 產物為.test合同配置；未實機安裝，不是發布版 |
| ER／手冊 | 與現有migration／程式對照 | 尚未以真環境從頭操作驗證 |

結論：可以交接可審查程式與部署材料，不能聲稱其他項目全部驗收或production ready。未新增費用、權限或資料庫schema，未觸碰其他資料庫。
