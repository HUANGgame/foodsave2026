## 最新終態：Android fixture #18 SUCCESS（2026-10-03 10:05 UTC）

[Run37114944635](https://github.com/HUANGgame/foodsave2026/actions/runs/37114944635)，job111179832455，精確測試commit `78c9c1073f3296c9904789b4b5e24a776e2ba0d8`。Next build／Gradle build、APK v1/v2簽章、minSdk23／targetSdk36、API35 emulator安裝／Activity啟動及全部fixture斷言通過。

APK：`app-debug.apk`，5,314,759 bytes；SHA256 `e264623666a159e3862d34af0c692786aef4a1803a85cece342369b7fb1253b8`。package `tw.foodsave.demo`、versionCode3、versionName `0.2.0-integration`。維持no artifact upload，所以這份CI APK沒有可下載保留副本，不能聲稱已交付真人可用APK。

七類新場景全部PASS：information無reserve；pending option disabled及fixture409模式不變；offline單帳號切換不混orders/notices；vendor-account零商品收藏與取消；通知顯示／已讀；explicit stock-loss confirmation及quantity0；expired confirm不顯示交付成功。另含keyboard真實tap/adb文字／Back、reserve/cancel、vendor表單、camera denied→manual preview→同keylost-reply重試、admin link、定位拒絕／停用、原生Back、wheel double-tap/HOME-resume/210°、reduced motion、memory-only token、force-stop重開登入。

根因閉環：10:05:11 native focus再次顯示Google LocationOffWarningActivity，Awake；精確匹配後Back取消警告，10:05:12恢復FoodSave焦點，10:05:13原生Back真正返回profile。10:05:19 rAF=20、running animations=0、三次nav bounds一致；10:05:21原本一般locator.click通過（沒有force／DOM dispatch）。證據支持此次Back阻擋是fixture切換定位後的系統Activity，不需改產品返回邏輯。初始native email bounds亦實際觸控成功，保留IME與輸入斷言；不把#17自動化viewport失敗改寫為未發生。

仍未測：Android與真API端到端／HTTP TLS CORS、實機流暢度、原生相機授權後實鏡掃碼、SQL通知失敗注入及schema011雙連線競爭。SQL41 PASS是部署端獨立證據；Android中mode409與库存等是mock，不替代SQL驗證。以下保留歷次失敗與診斷過程，過去「待結果」以本節終態為準。

---

# Schema011 Android fixture（不代表真API驗收）

執行環境維持public standard Ubuntu、API35 emulator、target36 debug APK；無cache／artifact upload、無Azure或真人資料。既有temporary KVM精確user ACL不變，未新增manifest/privacy權限。測試mock僅存在CI process，APK assets仍連設定的HTTPS API，不內嵌mock服務。

## 失敗與診斷紀錄

- [#10](https://github.com/HUANGgame/foodsave2026/actions/runs/37111832866)，0b438fe：build/sign/install/Activity及reserve/cancel通過；native permission hierarchy返回null root，dump無檔，讀檔中止。修補在原四次嘗試內捕捉暫時無檔、清除舊snapshot重取；未將無dialog當成功。
- [#11](https://github.com/HUANGgame/foodsave2026/actions/runs/37112145081)，d0b3d4a08e28442eb6d85bcce4ea95e76f942dfc：定位拒絕／停用、Back、wheel HOME/resume及210°均通過；隨後profile link actionability等待stable逾時。這不能直接歸咎CSS動畫或宣稱產品正常；新七類場景未跑到。
- [#12](https://github.com/HUANGgame/foodsave2026/actions/runs/37112591082)，e042bf2：增加native topResumedActivity離開／返回檢查、三次nav bounds、DOM visibility/focus、rAF次數及running animations診斷；profile改由uiautomator取得真實觸控範圍、adb tap，仍驗heading＋URL，無forced click／dispatchEvent。結果待日誌確認。

## 新增fixture contract

store mode及pending count、分離consumer/consumer2 identity與orders/inbox、vendor帳號favorite＋獨立零商品store、notification read、stock-loss revision/pending/actual及explicit confirm、pickup expired terminal response。mode409為mock後端拒絕，只驗UI不改模式，不能代替SQL鎖競態。缺貨quantity、刪除及通知為mock狀態，不是真SQL寫入證據。

不論CI結果，仍未涵蓋真API/TLS/CORS、實機流暢度、原生相機授權後實際鏡頭掃碼、SQL通知失敗回滾及雙連線競態。無artifact上傳設定表示CI APK不會留成可下載成品。

[#13](https://github.com/HUANGgame/foodsave2026/actions/runs/37113010716)，953eb62：新增七類場景全有Android PASS（info無預約、zero-product vendor favorite、通知read、offline account隔離、pending option/409、explicit loss、expired不success）；camera denial/manual same-key重試亦通過。生命週期另列失敗：導航URL及heading已確認reservations，KEYCODE_BACK後5秒仍是reservations。尚不能宣稱Back已修。#14新增IME是否先消耗Back及debug-only原生history index/size診斷；不記帳密、URL或個資。

## 根因確認與修正待驗

- #14：keyboardShown=false、historyLength17；上一個history entry確為profile，但Back後index仍16/reservations。不是「尚未進入預約頁」或可見IME造成。
- #15新增診斷誤用`dumpsys window windows`，該API35映像沒有焦點摘要；空輸出不能證明無focus。改用完整window dump。
- [#16](https://github.com/HUANGgame/foodsave2026/actions/runs/37114212532)取得原生證據：`mWakefulness=Awake`，`mCurrentFocus`／`mFocusedApp`為Google Play services的`LocationOffWarningActivity`。切換定位服務的fixture留下系統警告；CDP仍能操作背景DOM，原生Back實際送給警告Activity，不能當FoodSave返回失效。
- 57c51dd只在精確匹配該已知GMS警告時送一次Back取消，等待FoodSave MainActivity重新取得原生焦點；未知Activity仍失敗，不接受Google定位同意，不改權限。保留原Back/URL/heading斷言及HOME/resume/rAF確認，profile恢復正常locator.click（無force、無dispatchEvent）。臨時MainActivity診斷已還原，產品返回邏輯與953eb62一致，沒有任意增加timeout。
- [#17](https://github.com/HUANGgame/foodsave2026/actions/runs/37114645613)驗證上述修正，結果待終態日誌。

## 即時checkpoint（#18執行中）

#16已證实Google LocationOffWarningActivity取得native focus，裝置Awake；修正不是產品動畫或返回邏輯變更。#13–#16新增七類場景均PASS。#17在最早的電子郵件欄位Playwright click報outside viewport，未到定位修正。78c9c10改由native hierarchy的可見非password EditText座標觸控，再驗真正IME、adb輸入落在email欄及Back隱藏；保留後續全部斷言。

目前run [#18](https://github.com/HUANGgame/foodsave2026/actions/runs/37114944635)，測試commit78c9c10，尚未取得終態。不能把七類局部PASS當成整輪Android驗收通過。
