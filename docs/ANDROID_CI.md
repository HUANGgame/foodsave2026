# Android CI 基線（尚未通過）

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
