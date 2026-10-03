# 超商資訊測試 APK：2026-10-03

App來源commit：`60e97726836a8719eb7dfb9a76bd7264fdeb2679`。

保留自營消費者與店家模式；新增免登入全家資訊頁、門市／商品清單、可選地圖、30分鐘快取與未知／過期資料提示。全家查詢目前僅固定臺北信義公開測試區域，不傳使用者GPS。7-ELEVEN僅官方網頁與OPENPOINT商店入口，未整合庫存；外部超商無預約或領取按鈕。

私人交付APK：`foodsave-0.3.0-convenience-debug.apk`，5,326,223 bytes。

- SHA256：`ec5eb94962f8544601d17e24fceb869ca2997be1fb358c0e39121991d22e66fb`
- applicationId：`tw.foodsave.demo`；versionCode 4；versionName `0.3.0-convenience-test`。
- minSDK 23，targetSDK 36；既有debug簽章v1／v2通過，未建立release secrets。
- live設定使用既有核准API；ZIP完整性通過，無CI測試endpoint、合成測試標記或私鑰檔。APK未放入公開repository／CI artifacts。

本地unit 16、browser fixture 24通過，production build／typecheck與離線Gradle assembleDebug成功。

[Android CI #22](https://github.com/HUANGgame/foodsave2026/actions/runs/37120874348)成功：CI專用APK在模擬器安裝、Activity啟動、原生鍵盤、消費者／店家流程、相機拒絕與手動領取、定位拒絕、HOME／Back、轉盤及重啟測試通過；免登入全家卡片、未知數量、快取與7-ELEVEN入口通過。全家測試攔截原生HTTP bridge並回合成資料，未請求真來源。

上述CI APK與私人交付APK設定及位元組不同。私人交付的確切APK未於本環境實機／模擬器安裝，未實測真全家HTTP或Azure public API；本環境來源連線被proxy 403阻擋，沒有繞過。真資料與真機驗收仍待使用者進行。自營功能依賴既有後端及帳號，外部來源可用性不保證。
