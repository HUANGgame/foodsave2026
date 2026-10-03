# Android CI：fixture基線已單次通過

[首次run](https://github.com/HUANGgame/foodsave2026/actions/runs/37101823813)：commit `efe64547ba94874eebb24d322e21317445f7a77f`，2026-10-03 UTC，終態 **failure**，總時間10秒。

job `111142700802` 日誌明確顯示：`BLOCKED: runner lacks existing KVM read/write permissions; no sudo grant performed.`，exit 2。Checkout通過，KVM前置檢查未通過；**本次沒有建置、安裝、啟動APK，也沒有執行Android角色測試**。不能將已寫好的測試腳本算成已完成驗收。

Workflow限定公開repo、標準 `ubuntu-24.04`、30分鐘、同分支concurrency取消舊run。只有contents:read，checkout鎖定官方完整SHA、persist-credentials:false；沒有使用者secrets、OIDC、cache action、artifact upload或新雲端資源。GitHub runner的「Cache mode: write」是平台能力資訊，這份workflow沒有呼叫快取服務。無SDK自動接受條款。

預備腳本先使用官方SDK及Java21編譯debug APK，驗證簽章、記錄大小/hash，啟動Google API35 x86_64 emulator，ADB安裝／啟動，連真正Capacitor WebView的CDP。三角色測試使用intercepted synthetic API，消費者預約／取消、商家表單、管理員入口，另測force-stop/relaunch；不代表Azure SQL或完整管理功能驗收。release設定不變，不啟用release WebView debugging。package仍是測試用 `tw.foodsave.demo`。

## 後續已批准的最小權限變更

使用者其後已明確批准。在一次性GitHub runner、測試啟動前檢查 `setfacl` 已存在，再執行下列精確ACL調整：

```sh
sudo setfacl -m "u:$(id -un):rw" /dev/kvm
```

已於7501c2c加入此命令；第二次run通過ACL檢查後，在尋找emulator時失敗。它只授權當次runner帳號存取KVM裝置，避免world-writable；不更改repo、Azure、DB或持久主機的權限。若命令不存在則停止，不自行安裝套件或改用更廣權限。父流程已提供明確批准；不能用無限重試、larger runner或付費環境替代。

官方依據：[公開repo標準runner計費](https://docs.github.com/en/billing/concepts/product-billing/github-actions)、[KVM支援及權限說明](https://github.blog/changelog/2024-04-02-github-actions-hardware-accelerated-android-virtualization-now-available/)。此次checkout另有Node20被平台改以Node24執行的棄用警告，checkout本身成功，並非失敗原因。

第二次run [37102164978](https://github.com/HUANGgame/foodsave2026/actions/runs/37102164978) 終態failure、7秒，`emulator: command not found`。74861e4修正為先透過官方sdkmanager安裝emulator，仍不自動接受新條款；第三次run已結束，詳見下方。

## 實際Android進展與剩餘失敗

第三次 [37102284218](https://github.com/HUANGgame/foodsave2026/actions/runs/37102284218)：KVM可用、API36 debug APK編譯與v1/v2簽章驗證成功、API35 emulator安裝Success及Activity Status:ok；自訂CDP連線失敗，整體failure，UI未驗。

第四次 [37102663515](https://github.com/HUANGgame/foodsave2026/actions/runs/37102663515)，commit8aa99902502993efe07a578bac93d9a47e88c20b：改官方Playwright Android WebView接口，仍在等待webview事件30秒逾時。APK再次build/sign/install/Activity啟動成功，**UI三角色未執行，整體failure**。簽署APK大小5,161,470 bytes，SHA256 dad5696504459b4516e32f557e63628b09459a1553c1884a88869a309ee180f1；未上傳／保留CI產物，只有job logs/summary，不是可下載的正式APK。

尚未取得WebView／AndroidRuntime崩潰診斷，不能猜測實際UI已呈現或修改release debugging。下一步需有界收集純fixture啟動診斷，找出WebView未被發現原因，再決定適配；不無限重跑。未新增安全授權或接受新SDK條款。

## 第五次：實際APK fixture基線通過

[run37103516509](https://github.com/HUANGgame/foodsave2026/actions/runs/37103516509)，精確commit `3b87b0456ad64a8e5435487fe7910404731eb4d8`，job111147500595，終態 **success**。僅增加有限的登入前診斷；沒有改App設定、提高等待上限或啟用release除錯。

證據：API35 x86_64 Google emulator；App PID1943在前景，debug APK旗標DEBUGGABLE，WebView provider com.google.android.webview 124.0.6367.219 enabled，relro完成且package dirty=false；同PID devtools socket存在。啟動錯誤篩選無輸出。Playwright官方Android接口取得真正 `https://localhost` Capacitor頁面，品牌文字已呈現。

通過的實際Android操作（後端皆synthetic fixture）：

- 消費者登入、預約、切個人中心／我的預約、讀取取貨碼、取消與庫存回復契約。
- 零次數抽獎禁用；storage不含bearer token、未回退demo。
- 商家登入及商品表單送出，驗證價格／庫存payload。
- 管理員登入後有管理中心入口，無商家工作台入口；**不代表管理CRUD通過**。
- 原生force-stop與relaunch後回到登入，bearer session未保留；畫面無橫向溢出。

APK v1/v2簽章通過，package tw.foodsave.demo，min23/target36，大小 **5,161,466 bytes**，SHA256 `8203fd831640241dea620e21732955e26cfcfc8978077b3d4caa80651eef7b94`。依零儲存費用要求沒有artifact upload，runner檔案已隨job回收，**此hash不是可下載交付連結**。

先前兩次WebView偵測逾時在此輪未重現；健康啟動證據不能倒推先前失敗原因或聲稱已消除所有冷啟動競態。保留診斷及失敗紀錄，不盲目延長等待或反覆跑成功基線。真實裝置、原生定位同意／拒絕、原生返回鍵／鍵盤／外部導航、轉盤動畫FPS、真Azure API／SQL、跨裝置及完整管理流程仍未驗收。零付費／無額外權限與SDK自動授權的限制保持。

## Sixth run: native input/location/back and wheel checks passed

[run37104919923](https://github.com/HUANGgame/foodsave2026/actions/runs/37104919923), exact commit `f16a3a16f680f9c949475adab6c3a288f469721d`, job111151437543, finished **success**, 2026-10-03 07:06 UTC. Android API35 emulator installed and launched the real API36 debug APK; official Playwright connected to its Capacitor WebView. Native Back now navigates WebView history before falling through to Android's default behavior. No app permission or release debugging changes.

Actual additional PASS evidence: native soft keyboard accepts ADB input and Back hides it without leaving login; Android location permission dialog denied with Chinese feedback and product list retained; device location service disabled with feedback and no fabricated location; native Back returns reservations to profile; wheel double-tap submits exactly one draw, HOME/resume preserves the result, wheel lands at the expected 210 degrees; reduced-motion media is honored and saved draw history restores after navigation. Existing consumer reserve/cancel, vendor form, admin entry, zero-spin/token guards and force-stop/relaunch checks also pass. Backend responses remain synthetic intercepted fixtures. Reduced-motion is emulated media on the actual Android WebView; no physical-device FPS or live Azure API claim.

APK: package `tw.foodsave.demo`, version3 / 0.2.0-integration, **5,162,318 bytes**, SHA256 `71319da31d0e528da36d662efdeb415023f91583fad10d789b26a0d4c209117f`; v1/v2 signature verification passed. No artifact upload/cache; ephemeral CI APK is not a downloadable deliverable. Real GPS granted-position accuracy, external navigation, physical-device performance, full admin CRUD and Android-to-Azure/cross-device acceptance remain open.
