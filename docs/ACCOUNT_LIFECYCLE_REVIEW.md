# 帳號生命週期：本地審查候選（未部署／未真寄信）

本階段僅恢復註冊／驗信／登入／忘記重設／改密碼；其他功能維持暫停。不能把本地fixture結果或郵件HTTP接受狀態說成真寄達，更不能交付尚未能註冊的APK當作完成。

## 行為與API

| 路徑 | 行為 |
|---|---|
| GET /auth/options | 唯讀可用性；旗標或寄信配置未就緒則關閉 |
| POST /auth/register | 僅email；共用配額後寄驗證碼，固定202訊息，不查詢／洩露帳號是否存在 |
| POST /auth/verify-email | email＋碼＋本人選的新密碼；驗證後才建consumer；不回session |
| POST /auth/forgot-password | 已存在／不存在／停用帳號均同寄信與回應路徑 |
| POST /auth/reset-password | email＋碼＋新密碼；只更新既有active帳號，不建立／啟用帳號，撤銷全部session |
| POST /auth/change-password | bearer＋目前密碼＋新密碼；交易內重驗session／目前密碼，撤銷全部session |
| POST /auth/login | 保留既有登入；加email節流及user更新鎖，避免舊密碼驗證與reset交錯後留下session |

註冊先驗信再設密碼，避免攻擊者先用別人的email綁定已知密碼。公開API不可傳role，vendor/admin仍只能受控流程建立。現有帳號不被假標成已驗證，不強制失去登入；email_verified_at維持NULL，重設驗信後才設定。舊版App不支援這個email-first註冊契約，必須交付新App後再驗收。

## 安全措施與限制

- 使用Python標準庫hashlib.scrypt、secrets與hmac，不自製crypto。新密碼15–128字元、拒絕部分常見／重複弱密碼與email本身，不保存可逆密碼。scrypt-v2 N=131072/r=8/p=1，16-byte隨機salt；每process最多2個hash工作。現有N=16384雜湊仍能驗證；啟用schema012流程後首次成功登入會升級雜湊成本並撤銷其他舊session，密碼本身不變、信箱不會因此被標記已驗證；改密碼／重設／新帳號也使用新成本。
- 既有雜湊不是plaintext；較低成本保留至首次成功登入升級、改密碼或重設。不是全面外洩密碼字典檢查、MFA、passkey或零風險保證。
- 驗證码256-bit（43字元），15分鐘有效。資料庫只存purpose＋email＋碼的SHA256及email key，無raw token、無未驗證email／password。purpose與email綁定，重送替換前碼；成功同交易清除同信箱全部碼。過期一天以上的碼於新請求最多刪100筆；沒有新增排程。
- 同一信箱應用鎖＋user UPDLOCK/HOLDLOCK＋單一交易保護一次性消耗、密碼更新與session刪除。真SQL競爭／鎖／rollback尚未驗證。
- IP每15分鐘10次；寄信每email每15分鐘3次（註冊／重設共用）；全站5/min、10/hour、30/day、每UTC曆月1000。這是應用層fixed window，provider仍可能429；不提高Azure managed-domain配額，不自動重試、送到付費備援或用新來源繞過。
- 不信任任意X-Forwarded-For。部署端須確認既有反向代理IP信任；未設定可能全體共用proxy IP而誤限流，不能放寬到任意代理。
- raw碼只經TLS寄信及POST body；無query URL、網頁第三方追蹤或reset自動登入。App不持久儲存密碼／碼；新密碼表單送出後清空。驗證失敗body不echo輸入；郵件provider例外不含收件者／碼回傳。
- 新email輸入限ASCII格式並做長度／domain label驗證；未做DNS或真可達性推斷，收信驗證才證明控制權。SMTPUTF8國際化地址不在本候選驗收範圍。
- SQL runtime是共用服務身份；若runtime本身被攻陷，既有廣泛users INSERT／SELECT等權限仍是殘餘風險。本次不宣稱DB可驗證人類身分或修復所有既有授權邊界。

## 寄信adapter與Azure決策

介面為send_code(email,purpose,code)，業務不依賴供應商。test mail僅存在測試dependency override，無prod console或跳過驗證模式。SMTP adapter限465 TLS或587 STARTTLS且驗證憑證，僅明確核准配置才可用。

新增ACS adapter使用azure-communication-email 1.1.0與azure-identity 1.26.0的ManagedIdentityCredential，僅既有App Service system-assigned MI，不使用DefaultAzureCredential／CLI fallback、key或connection string。retry_total=0、短網路逾時、logging_enable=false、追蹤關閉；NoPolling只判初始接受Running／Succeeded，不創背景poller或聲稱送達。未確認結果回503，碼仍依原時間到期，不能把延遲郵件當有效。

使用者已准許Azure贈送額度，未准現金、PAYG升級或付款方式。部署端需先核對ACS可建立、額度適用與spending limit保持；credit不足停止。不能以app quota當作現金零花費保證。ACS臨時核准窗口FOODSAVE_MAIL_AUTHORIZED_UNTIL最長24小時，到期關閉新寄信；續期需再次確認credits，不自動延長。不給runtime讀billing或管理資源權限。

父流程已查得ACS Email退役與新客戶截止公告：2028-09-30退役、2026-10-23新客戶截止；需部署端確認適用，視為可替換的短期候選，不承諾永久服務。來源 https://learn.microsoft.com/en-us/azure/communication-services/whats-new 。

## 已集中批准的部署範圍（本環境尚未執行）

1. **資源／credits**：僅指定FoodSave資源群組中的Email Communication Services＋Communication Services＋Azure-managed寄件domain及連結；既有App/SQL/HTTPS不搬移。部署端給出精確資源名稱／區域／credits適用與停止條件後批准；不加付款方式或升級訂閱。
2. **Azure RBAC**：僅既有App Service MI，scope限定新ACS單一資源。父流程只讀核對的候選custom role為Actions `Microsoft.Communication/CommunicationServices/Read`與`Microsoft.Communication/CommunicationServices/Write`、DataActions空；Write可改該ACS資源，不能宣稱send-only。須把實際role定義／ID與scope列入批准，不給Contributor／Owner／subscription scope，不包含Delete／ListKeys、不建立新principal或persistent secret。本adapter不需要operation polling/read額外權限。
3. **SQL**：owner只在foodsave套用`backend/migrations/012_account_lifecycle.sql`（一新增欄位、一表、兩index、一procedure）。既有runtime追加`infra/sqlserver/runtime-grant-012.review.sql`：account_challenges SELECT/INSERT/DELETE與apply_account_password EXECUTE。不新增直接password_hash UPDATE、role變更、viewer存取、DDL、GRANT OPTION。原有users INSERT/SELECT与sessions權限沿用。WiFiDB不觸及。
4. **App設定／部署**：依掃描後固定source，部署runtime依賴及新API；先保持FOODSAVE_ACCOUNT_LIFECYCLE_ENABLED=false／FOODSAVE_REGISTRATION_ENABLED=false。設定非秘密provider=acs、endpoint、sender、mail-approved及最長24h授權截止。隱私政策完成旗標不能為通測而虛設；需批准實際政策與寄信資料流揭露。
5. **受控整合驗收**：批准收件信箱及少量consumer帳號／資料範圍（不是先前race授權）；使用者自行在App設密碼，不聊天交secret。驗真寄信→碼→建帳→登入→忘記重設→舊session失效→新密碼登入→改密碼；再做過期、重用、重送、限流、未知帳號及mail failure。保存hash/結果，不保存raw密碼／碼。清理資料另核對精確範圍。
6. **APK交付**：以上通過後才升版本、建新APK、manifest/sign/hash掃描、原生實測與私人Library交付。0.3.1不含本次帳號功能；此候選未建新APK、未deploy、未執行migration/grant或寄真信。

## 回復方案

優先關閉lifecycle／registration／mail-approved旗標停止新操作，保留已成功變更的密碼、users與舊session撤銷結果。已用scrypt-v2的帳號不可回復到只懂舊scrypt的完整舊後端；保留本次security.py相容驗證能力。

`backend/rollback/012_account_lifecycle.review.sql`僅審查候選：停寫後且無任何challenge／已驗證帳號／v2雜湊才允許owner移除新增schema及migration receipt。已發生帳號操作則拒絕destructive down migration，改走保留additive schema的功能回復；不把旧密碼或session復活。未執行任何rollback。

既有schema011 race／cleanup工具尚未針對012新表復審，不應直接套用為新帳號cleanup。新帳號的資料清除與郵件provider保留需加入實際隱私／erasure政策後才能正式開放。

## 官方參考

- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://docs.python.org/3/library/smtplib.html
- https://learn.microsoft.com/en-us/python/api/overview/azure/communication-email-readme?view=azure-python

## 本地檢查 checkpoint

後端全套222 passed（含獨立安全復核後修正）。前端unit17、browser33、production build／typecheck通過。19個本地變更檔的常見secret格式掃描無命中，無binary或私有設定；測試使用隨機合成password/code與假的SQL/mail，未寄真信、未在真SQL compile／驗並發。全流程HTTP fixture包含register→verify→login→forgot/reset→舊token失效→新密碼登入→change→再次撤銷；不是正式整合驗收。


## 獨立只讀安全復核與部署阻擋項

獨立reviewer檢查5aeb7d2候選，沒有發現直接HTTP帳號接管路徑，但不是零漏洞保證。

- 已修：無效驗證碼在昂貴scrypt之前拒絕；新密碼hash只在有效ticket／帳號或有效session／目前密碼之後執行。login／finish／change及三個刪除帳號驗密入口共用SQL配額20次/min（一次可含驗證與升級hash），各process仍最多2個hash工作。共享小配額仍可被耗盡造成拒絕服務。
- 已修：SMTP及ACS在初始化和送出前檢查最長24h核准期限；每封限單一收件者，SMTP序列化／ACS JSON UTF-8最多4096bytes。5/min、10/hour、30/day、1000/UTC曆月計數先於寄送，失敗也消耗配額。分／時／日是從首次請求起的fixed window，非rolling window；UTC月用獨立年月key。不宣稱USD1是硬性費用上限。
- 待部署驗證（阻擋啟用）：startup --no-proxy-headers可能把所有人算成同一proxy IP。部署worker須核對實際ingress及受信代理設定；不得直接信任任意X-Forwarded-For。
- 待真SQL驗證（阻擋啟用）：schema012 compile、精確runtime grants；同碼雙消耗、reset對change、login對reset、transaction rollback。222本地tests使用fake SQL，不能替代。
- 權限邊界：runtime新增challenge SELECT/INSERT/DELETE含全表能力，procedure只校驗active與expected hash、交易和新hash格式，不獨立驗證人類token/session。API在同一交易驗證；runtime本來就可讀users hashes、INSERT sessions/users。這是可信共用runtime，不是DB層每使用者隔離。本次沒有擴充已批准grant。
- 真寄達及使用者私下設定密碼／重設仍待驗；不得在聊天、日誌或artifact提供raw code／密碼。隱私／erasure政策與實際寄信資料流揭露也須通過啟用檢查。

使用者已批准本次掃描後auth source推送既有branch及指定部署範圍。具體資源與SQL操作交由Azure worker，不在本工作環境繞網路限制。修正不新增SQL／Azure權限。

二次獨立復核指出郵件adapter與API email字元規則不一致；已共用EmailRequest並加入apostrophe／驚嘆號／等號合法地址及header injection拒絕測試。

補充獨立復核：公開刪除狀態／刪除申請及登入後刪除入口原先漏接global password quota，已補上；七個HTTP密碼入口均驗證配額耗盡時429且不進入hash／驗密／服務操作。新增共享browser／Android帳號fixture涵蓋註冊、錯碼重設、成功重設、舊密碼拒絕、新密碼登入及改密碼登出；真Android結果另記，不以browser通過替代。

部署端實際ACS為含region的主機名；adapter已接受單層或region兩層的HTTPS communication.azure.com主機，拒絕非HTTPS、偽後綴與userinfo。此為設定格式測試，非真ACS寄信證據。
