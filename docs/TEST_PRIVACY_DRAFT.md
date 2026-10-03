# FoodSave 公開測試版隱私與刪除說明（待定案，不代表已啟用）

營運者為HUANG，聯絡信箱413637629@o365.tku.edu.tw。本服務目前為測試版，仍可能發生服務中斷。此草稿不構成法律合規保證；待下列實際設定與責任確認後才同步到App及公開政策，不把privacy-complete提前設true。

## 帳號、驗證與寄信

註冊使用email，密碼只儲存加鹽scrypt雜湊，不保存可還原密碼。登入session用於驗證身分；App僅於記憶體持有登入憑證。重設及改密碼成功會撤銷原有session。請自行在App設定密碼，不透過聊天提供密碼或驗證碼。

驗證郵件透過Microsoft Azure Communication Services發送，供應商會處理收件地址、郵件內容及傳送所需資訊。已關閉郵件互動追蹤；這不代表供應商不保留傳送／安全紀錄。Azure worker已確認寄信資源資料位置為AsiaPacific、managed domain互動追蹤關閉；平台內部投遞／服務紀錄保存期未由目前設定揭露，仍屬未知，不能說供應商不留紀錄。Microsoft資料處理說明：https://learn.microsoft.com/en-us/azure/communication-services/concepts/privacy ，隱私權聲明：https://privacy.microsoft.com/en-us/privacystatement 。

一次性碼15分鐘內有效，資料庫只保存碼與email衍生的雜湊及期限。重送使舊碼失效。失效與物理清除不同：新請求會有限量補清舊過期資料，owner人工工具也能每次最多清100筆過期challenge；目前沒有自動清除排程，因此不承諾第15分鐘立即刪除。

為限制暴力嘗試與寄信成本，系統保存email／帳號／共用入口等衍生限流識別與計數。這些雜湊不是無法關聯的匿名資料。仍有效的安全計數不因刪帳而重設；限流窗口結束後，營運者按刪除申請人工補清該email的過期限流識別。全站成本計數不含單一申請人的專屬身份，不藉刪帳清零。一次性寄信測試防重計數屬單獨已核准測試控制，不以刪帳重新取得寄送名額；其後處置需在該測試結束後另核對，不假稱已全部匿名化。

## 既有功能與資料流

預約、收藏、評論、獎勵及操作紀錄用於既有功能；測試版不因此增加新資料用途。商家刪帳／過期預約仍須完成既有顧客通知與訂單處理，不能直接刪庫跳過通知。定位、相機、全家公開查詢、地圖／照片外部來源的資料流沿用目前App已列說明，不新增追蹤或廣告用途。

## 刪除流程：立即停用，30天內處理

App或公開帳號頁可提出刪除；確認身分並受理後立即停用帳號、撤銷登入。受理不等於所有副本已清除。HUANG須追蹤請求，以既有owner權限人工處理，最遲30天內完成可識別個資清除及必要後續；目前未宣稱自動清除已部署。

依使用者已要求全部刪除，本測試版不另創業務保留理由；建議owner政策business_retention_days=0，無待處理訂單及必要通知完成後，依既有兩階段工具完成清PII及業務資料刪除。不能只執行第一階段就宣稱整體完成。清除收據需定案有限保存期限；它只證明應用SQL範圍，不證明雲端備份／日誌／外部來源已清除。

schema012增量已加入：刪除該email的challenge、清驗信時間、清已過期email限流識別；其他使用者資料、全站配額、尚未到期防濫用計數不受影響。若仍有有效email計數，營運者須在窗口後按同一刪除申請補清，才完成該部分處理，不能把第一階段回覆當完整刪除證明。

## 定案前須確認的最小項目

1. HUANG承接人工追蹤／至少定期檢查及30天上限；確認grace_days（建議0）、business_retention_days=0與有限receipt_days。這是明確營運參數，不用虛構測試期保留需求。
2. Azure worker只讀確認：SQL短期備份保存7天、差異備份間隔12小時，weekly/monthly/yearly LTR均PT0S，immutabilityDisabled。營運資料刪除不會立即從既存備份移除；應依備份生命週期到期，不能把7天寫成刪帳後立刻完成或全供應商紀錄保存期。App Service application file/blob logging Off、HTTP file/blob false、detailed errors/failed tracing false，HTTP file retention days為null，不能解讀為0天。App／ACS Azure Monitor diagnostic settings為空，表示未配置匯出目的地，不表示無平台內部紀錄；EmailServices診斷查詢ResourceTypeNotSupported也不是無紀錄證據。本次不改任何備份／日誌設定。
3. 備份復原後，先重新套用已受理刪除／停用結果再提供服務；實際備份到期及日誌處理責任須列明。
4. owner012增量在合成資料執行rollback QA並零殘留，確認人工刪除與補清模式。不得藉驗收執行真人資料刪除、改grant或新建排程。
5. 定案後才更新App文案、公開政策及privacy-complete；公開註冊開啟與使用者本人驗信／登入／重設另行驗收。私人APK測試不以商店申報完成為前提。
