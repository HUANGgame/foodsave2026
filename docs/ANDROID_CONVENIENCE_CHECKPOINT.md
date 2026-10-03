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

## 0.3.1地區選擇版

App來源 `1b679959d96d47dba0bab490ee45f99cf168450b`。手選公開中心包含臺北信義、新北板橋、桃園、臺中西區、臺南中西、高雄苓雅；回傳範圍由來源決定，未驗證全台覆蓋。附近查詢先揭露座標傳給全家，明確同意後才請求系統定位權限；拒絕、取消或服務失敗可手選。附近位置與結果只留本頁記憶體；手選快取分區，舊查詢回應不覆蓋新區域。

私人APK `foodsave-0.3.1-area-debug.apk`，5,328,142 bytes，versionCode 5，versionName `0.3.1-area-test`，套件／簽章不變。SHA256 `8e79faed16ad2cd93d57699841ee03819154e4b0a71ad7b3268bd047d60159e0`。本地unit17、browser29、production build與APK build／manifest／v1-v2簽章／ZIP完整性通過。敏感格式與檔名掃描未發現私鑰、常見token／金鑰、敏感設定檔或合成測試標記；含既有核准API位址與公開營運聯絡信箱，不等於完全沒有個資或完整安全認證。

此確切私人APK尚未安裝實測。本地adb無裝置，既有FoodSaveTest啟動失敗：x86_64需要硬體加速，無/dev/kvm且vmx/svm不可用。browser29不能算Android29。新增CI案例驗證原生WebView切區快取及附近同意取消／系統拒絕，須以該run終態與PASS紀錄為準；來源HTTP仍攔截為合成資料，不能替代真來源／真機驗收。
