# 最新使用者規則、已測基礎與下一階段（未部署）

以2026-10-03最新指示為準；本文件覆蓋過去「切換中仍保留待領」及「過期只改狀態」方案。不得混用過時說法。

## 本次可審查的基礎

全店唯一service_mode enum：information／reservation。新店information；既有店家migration回填reservation以維持之前行為。資訊模式不可預約，後端也拒絕竄改請求。reservation→information有任何waiting即409且不改模式、不建立暫停或pending-switch狀態；清零後可切。information→reservation可直接切。reserve及set_store_mode用同一store transaction-owned applock，避免檢查與新預約競態。歷史完成訂單目前不阻擋切換。

商家可直接選全店模式，pendingCount及管理／確認逾期入口可見；資訊模式沒有掃碼主入口，顧客卡只有價格／數量／期限／更新資訊，沒有預約或出示碼。外部7-ELEVEN／全家一律唯讀；缺数量為unknown，sourceUpdatedAt與checkedAt區分。外部provider實際接入不在這份commit。

migration006草案：stores.service_mode一欄、CHECK／default；既有多店owner則停止，不自動刪除或重新指派，再以filtered UNIQUE(owner_id)落實一商家帳號一店。既有owner=NULL店家不強行配帳號。owner執行前須審查。runtime唯一新權限提案：`GRANT UPDATE (service_mode) ON OBJECT::dbo.stores TO [既有已驗身分]`，腳本含專用DB／migration／Entra ApplicationID SID檢查；**未執行**。不增加整表UPDATE、DDL或任何runtime DELETE。

更新時間從既有request_results的product.save／stock-adjust created_at取得，未知維持NULL，超過30分鐘顯示可能過時，不偽造即時庫存。既有交易EXP／商品成交快照仍保留。

## 六條新規則逐項驗收狀態

| 使用者規則 | 目前程式／測試證據 | 新規則剩餘狀態 |
|---|---|---|
| 1 商家刪帳：刪店／商品／訂單，先通知受影響顧客 | 修補會在同交易鎖店、取消所有該店waiting、返庫一次、記vendor_closed，停用商家／商品；測試通過 | **未完成新規則**：尚未建立in-app通知，也未實體刪店／商品／訂單。不可把取消當刪除 |
| 2 逾期／失敗不可顯示交付成功 | 修正confirmexpired後refresh503覆蓋訊息；browser回歸通過，未核銷／未發EXP有後端測試 | 本地PASS；新版真API與Android仍需對應版本驗證 |
| 3 逾期：一次返庫＋通知後刪order，重試不失冪等 | 有界lazy expiry每次最多25，history限定本人、feed有界整理，reserve整理該product；顯式店家整理最多100；共用storeguard及product/order重查 | **未完成新規則**：現在仍state=expired，尚無通知／實體DELETE／獨立終態ledger |
| 4 一手機多帳號，一次一個active session；一vendor一store | api token僅memory、generation隔離晚回覆、pending keys含userID；一般登入／登出與role後端驗證已有測試。migration006增加一店限制提案 | 顯式切換帳號入口與offline登出修補待做；不新增多密碼儲存。沒有自助store首次入駐流程 |
| 5 伺服器最新版／更新庫存且不偷蓋未存輸入 | revision409保護；禁止截止縮短到waiting最晚期限之前；inline±1原子。目前登入／返回前景／人工刷新，不是websocket或秒級同步 | edit revision重新載入／丟棄確認、新批次複製為新product、合理可見頁輪詢待做；不把已有刷新稱全面即時 |
| 6 收藏＝vendor account；無商品也顯示，vendor刪帳通知並移除 | 現在仍storeID收藏、卡片由products推導 | **未完成**：需favorite關聯遷移、獨立store資料與通知交易；無商品不可再消失 |

前106後端、11前端單元通過；本輪browser17場景中16初次通過，1項原生option的matcher不適用，改驗HTML disabled property後該場景通過。靜態build／TypeScript通過。全部是本地或fixture證據，migration006／新模式真SQL未驗。既有已通過18 SQL及Android run37107966613仍屬其固定舊版本。

## 下一階段：收斂成兩個必要批次

**A：通知＋刪除原子性（先schema/安全審查，再實作）。** Owner migration007建立in-app notifications（受件user、唯一event key、類型／最低必要文案、建立／已讀／期限）與reservation terminal ledger（不FK到即將刪除的order、保留最小事件／冪等結果，不存取貨碼／電話／密碼）。favorite改為vendor帳號關聯並驗證遷移，不默默丟棄舊資料。商家關閉先收集顧客／追蹤者，原子寫通知與終態，再依FK順序刪reviews／reservations／favorites／products／store；立即停用登入，帳號PII仍依已批准30天流程處理，不能將business rows刪除宣稱所有個資已清除。逾期先返庫一次、寫通知／終態，再實體DELETE order。晚到請求及已刪order的原key須讀ledger，不能重扣庫存或回傳假waiting。離線通知於下次登入/fetch顯示，不承諾付費push/SMS或即時必達。

最小安全提案採同dbo ownership-chain的固定程序（無動態SQL、無EXECUTE AS、限交易內執行）：`dbo.close_vendor_business`、`dbo.expire_reservation`、`dbo.mark_notification_read`。提議runtime僅新增這3個程序EXECUTE及notifications明列公開回覆欄位SELECT、terminal ledger必要欄位SELECT；不要直接授予users／stores／products／orders整表DELETE。程序須以已驗證帳號ID／單一訂單ID為界、檢查owner與狀態，禁止無scope清除。favorite沿用原表DML權限但遷移欄位／FK由owner審查。**程序及007尚未編寫／授權／執行，必須先交完整SQL與精確欄位清單給父流程審查；本提案不是已授權grant。**

通知／ledger保存採可配置有限期限，應與已批准30天PII清除及owner清除工具一併驗證；不得默認永久保存或在真人資料上測試。測試至少含通知失敗整筆rollback、兩次expiry只返庫／通知一次、先完成後expiry不刪誤單、vendor closure與reserve競爭、followers通知去重、row已刪同key恢復、owner清除涵蓋新增資料。

**B：帳號／收藏／revision最小UI閉環。** 明確切換帳號＝退出本機active session再登入，不是刪帳；斷網也清本機token並明示遠端撤銷待確認，未完成意圖仍按account隔離。一帳號一店後只顯示其店鋪；不做多分店owner授權。收藏從vendor/store資料獨立取得，0商品有卡片及取消收藏。可見畫面使用有限間隔輪詢與foreground刷新，背景停止；409保留輸入、提供顯式載入最新版，舊單不被批次重上架污染。以實際請求／版本測試，不宣稱推播即時同步。

這已新增通知與FK刪除／冪等模型，不是小字串修改；需要追加一個獨立資料層實作與一個UI／驗收階段。無帳戶token百分比計量能力，不承諾精確百分比或完成時間。已過的舊基線不無限重跑，只驗受影響場景與必要回歸。source branch僅可審查，**delivery ZIP仍固定7824868，不部署這個未核准migration版本**。

## 唯讀帳號／授權盤點

登入／登出目前在個人中心，沒有帳號快切清單，不保存多組密碼。logout目前遠端失敗時本機token尚未清除，需B階段修正。vendor_catalog/products/order查詢都以目前登入ownerID限縮；舊設計可同owner多店，006的unique constraint提案將阻止新複數店，但既有重複必須先審查，不能自行刪店。一般consumer不能靠前端切role成vendor；首次merchant入駐仍需受控帳號／店家指派，未擴tenant權限。

## 外部來源另列，勿搶占關鍵刪除驗收

父流程報告全家官方匿名MapProductInfo取得有效樣本，尚非本workspace接入：後續clean-room adapter採公开区域手選、30分鐘cache，401／403／429停止並backoff；未opt-in不傳本人定位。價格／單品期限／照片缺少就null，不用分類合計冒充單品數。7-ELEVEN仍blocked，不借金鑰／cookie／驗證繞過；兩者永遠資訊模式，不能在FoodSave保留或核銷。此接入待A/B關鍵流程收斂後獨立階段執行。

## 最新庫存權威規則（納入A，不新增不必要產品流程）

店家確認的伺服器數量為準，consumer快取不能鎖庫或覆寫。available_quantity代表**尚未保留的可售量**；它為0不代表既有held商品無法交付，因此普通±1／可售量歸零不得自動取消已保留單。reserve仍須在同一storeguard／product交易鎖內重查mode及可售量；UI過時則拒絕／重新讀伺服器，不用舊數字補庫存。

只有店家明確表示「實際缺貨，無法履約」並確認受影響筆數，才進入reason=vendor_out_of_stock的取消／刪除交易。原子寫terminal ledger及唯一通知，通知文案採使用者確認方向：「很抱歉，店家確認此商品已售完，這次預約無法提供。請勿再前往取貨。」保留店家確認的actual available（售完則0），**release_quantity=0**，不得呼叫普通用戶取消的返庫路徑。無EXP／no-show處罰；同key重試／晚到cancel／expiry讀終態而不再次補庫。

因此A階段增加固定scope程序提案`dbo.report_stock_loss`（額外EXECUTE，無runtime直接DELETE；仍待完整SQL審查）。與前三個程序一共4個EXECUTE提案，不因本文件自行grant。鎖競態驗收：reserve先贏則納入後續確定無法履約的通知，缺貨先贏則reserve拒絕；customer cancel或expiry先返庫後店家更正，以店家最終確認值收斂；缺貨先處理後任何重試不得返庫。實際取消真人預約未授權執行，僅開發及synthetic交易驗證。

現版本已具備reserve原子可售量檢查，且可售量0不取消held單；**缺貨專用事件、通知及reason-specific release模型尚未完成**，不能把普通cancel返庫邏輯冒充此需求。
