# 單次 ACS 收信檢查（CLI，非公開 API）

目的只有既有 MI → ACS 接受 → 使用者實際收到普通測試通知。沒有密碼、驗證碼、連結、challenge、帳號或信箱驗證狀態寫入；不等於註冊／重設完成。

## 核准與限制

收件者必須是本次父流程批准的唯一學校信箱；probe本身只追蹤其正規化SHA256，不新增收件地址到source／APK。工具包沿用的api.py原本已含公開隱私聯絡信箱（同一地址）；它不是新秘密，不能宣稱整包不存在該地址。`FOODSAVE_MAIL_PROBE_TO`由Azure worker在server process環境提供，非任意地址參數。當前固定digest已在本地對批准地址核對一致。

僅ACS／既有system-assigned MI；維持既有endpoint、Portal canonical sender、mail-approved、最長24h期限、無retry／tracking、4096bytes限制。兩個account flags必須明確false。工具不修改App設定、schema或授權、不啟server、不部署API。

DB_NAME必須foodsave；只在既有rate_limits增加／更新限流bucket：先`auth:mail:probe:once:v1`每批准email限一次（100年窗口，無reset或自訂key），再呼叫API原有account_quota共享email3/15min、global5/min10/hour30/day1000/UTC月。worker沒有客戶IP，使用固定local-approved-mail-probe來源bucket，不宣稱驗證proxy。所有計數先commit，沒有補回quota或自動重試。

任何quota、SQL或provider失敗都不重寄；初次未確定是否送出也消耗唯一名額。要再次嘗試須另行檢視並核准，不得刪bucket、換key或切provider。

## Azure worker執行（尚未執行）

1. 核對固定ZIP SHA256，解壓至獨立暫存目錄，不覆寫運作中的API。使用現有已安裝依賴的Python；不安裝新服務或取新secret。
2. 保留現有SQL MI／ACS設定。只對這次process提供 `FOODSAVE_MAIL_PROBE_APPROVED=true`、`FOODSAVE_MAIL_PROBE_TO=<唯一核准學校信箱>`；`FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED=false`、`FOODSAVE_REGISTRATION_ENABLED=false`。期限必須仍有效且credits可用。不要把整份env或連線資訊輸出。
3. 工作目錄設為解壓根目錄，`PYTHONPATH=.`；使用既有Python執行 `-m qa.mail_delivery_probe --send-once`。worker施加60秒單次command timeout並確保程序退出、連線釋放；逾時不重試。
4. exit0／ACS_ACCEPTED_ONLY只代表初次provider接受，delivery_confirmed及account_verified仍false。exit1代表未確認，不能推斷沒送；不回傳provider exception或operation payload。沒有--send-once只印說明並exit2，不寄信。
5. 由使用者自行查看核准信箱（含垃圾信），只回報「已收到FoodSave測試通知」。未收到就保持待確認，不把ACS Running/Succeeded當寄達。不要求轉寄內容、密碼或任何碼。
6. 結束移除這次process的probe環境設定，保持公共flagsfalse；不自動延長期限或刪除rate資料。

## 本地證據

後端全套232 passed，包含固定收件限制、public flags／provider拒絕、一次性防重、既有global caps、例外redaction、錯DB拒絕與耗盡quota停止傳送。獨立只讀review未发现阻擋問題。全部fake SQL／mail，沒有Azure、真正寄信或真人帳號操作。ZIP用明確allowlist建立，包含api的傳遞依賴；不包含startup、migration、測試帳密或APK。

## 後續私人驗收

本通知不產生驗信碼。註冊／重設仍需另行批准封閉pilot的server端完整email限制與期限，讓使用者在私人APK自行收碼與設密碼；不能由工作者代填或在聊天索取。真SQL競爭驗收與公開proxy policy仍分開處理。本工具不繞過任何公開deny。
