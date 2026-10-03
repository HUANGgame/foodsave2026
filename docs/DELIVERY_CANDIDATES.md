# 五項交付候選狀態（不是完成／上架宣告）

| 交付項 | 現有候選與證據 | 最小剩餘條件 |
|---|---|---|
| App APK／AAB | 7824868 API36 debugAPK在API35 emulator安裝／啟動／fixture成功；CI不保留檔案，不能下載 | 核准真API配置與私有交付位置後重建APK、驗嵌入URL／簽章／hash及真API流程；正式packageID／簽署由擁有者確認，AAB未正式交付 |
| 管理網站 | runtime ZIP含/admin及帳號入口，新ZIP已固定hash交付部署端 | 部署端回報新版health／privacy與完整管理操作；实际URL僅私下交付，不發佈資源識別 |
| 受保護DB查看 | owner唯讀檢查通路已有部署端SQL證據 | App viewer身份與權限未批准／完整驗收，不以公開SQL或owner權限代替；沒有已交付viewer連結 |
| ER／架構 | [ARCHITECTURE.md](ARCHITECTURE.md)及migrations001–005 | 新取貨沿用request_results JSON，無schema006；新SQL驗收後補實證，不聲稱已驗所有關聯 |
| 操作／隱私手冊 | [OPERATIONS_DRAFT.md](OPERATIONS_DRAFT.md)、[PICKUP_INCREMENT.md](PICKUP_INCREMENT.md)、[LIVE_APP_ACCEPTANCE.md](LIVE_APP_ACCEPTANCE.md) | HUANG／指定客服／30天方向已填；必要业务记录原因與期限、备份与外部副本清除實行方式待定；註冊保持關閉 |

新版部署候選是7824868的delivery ZIP，校驗值見checksums.json。只準備候選，不自行部署、簽署正式版、商店上架或永久刪除真人資料。私有檔案交付尚需可用位置；本輪沒有新Library file ID，也不把舊demo或fixture包當finished。

商家首頁已有快速上架／掃碼取貨／今日訂單，商品沿用、庫存±1。**完整新店首次設定未做**：仍由管理員建立／指派店家，商家才能上第一個商品；沒有讓一般商家自行建立店家或擴大DB權限。若批准加入新店兩步引導，應先確定店家建立與權限邊界，再實作，不把現有商品表單稱為完成店家onboarding。
