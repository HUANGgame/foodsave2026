# 正式版驗收矩陣（尚未執行）

此表與現有demo測試分開。正式PASS必須有：版本／環境、帳號角色、操作步驟、UI證據、API結果、DB不變量與測試時間。逐列保留未完成範圍；下方最新證據記錄局部通過，不沿用demo測試冒充端到端正式驗收。

| ID | 執行角色 | 操作與預期 | 現在狀態 |
|---|---|---|---|
| U01 | 用戶 | 註冊／登入／登出／session失效；未登入寫入遭拒 | TODO |
| U02 | 用戶 | GPS允許與拒絕；1km查詢、綠色商品數、空結果與斷網可恢復 | TODO |
| U03 | 用戶 | 點店上拉、照片與評分數；點評論再返回保留店家與地圖 | TODO |
| U04 | 用戶 | 預約成功顯示取貨碼、截止與成交快照；重複點擊／重試不重建 | TODO |
| U05 | 用戶 | 取消／逾時只還庫存一次；不能取消已完成訂單 | TODO |
| U06 | 用戶 | 完成後本人可評論一次；別人／未完成／重放都拒絕 | TODO |
| U07 | 用戶 | 收藏／偏好跨裝置同步；EXP唯一事件；重新登入後一致 | TODO |
| V01 | 商家 | 登入獨立帳號、上架含照片／位置／截止的商品，另一客戶端看見 | TODO |
| V02 | 商家 | 編輯庫存／價格；已下單快照不變；不合法欄位拒絕 | TODO |
| V03 | 商家 | 錯誤碼／過期碼拒絕、正確核銷一次；其他商家不能核銷 | TODO |
| V04 | 商家 | 查待領取／已完成／未取貨，與消費者及DB一致 | TODO |
| P01 | 產品負責人 | consumer/vendor/admin分權，跨用戶／跨店ID操作403或404 | TODO |
| P02 | 產品負責人 | 至少兩個並發客戶端搶最後一份：最多一筆成功，庫存非負 | 真SQL Service並發PASS；HTTP／App雙客戶端未驗 |
| P03 | 產品負責人 | 取消與核銷競爭僅一個終態；EXP／還庫存不重發 | TODO |
| P04 | 產品負責人 | 週排名3/2/1可調；結算重跑不重發；台北週界正確 | TODO |
| P05 | 產品負責人 | 後端抽獎：零庫存不可中、次数與券同交易、重試不再扣 | TODO |
| P06 | 產品負責人 | 動畫停在後端指定結果；無前台機率；關閉／重開不改結果 | TODO |
| P06b | 產品負責人 | 連點只送同一抽獎意圖；零次數拒絕；逾時／斷網以同冪等鍵重試並讀回結果，重開不遺失券 | TODO |
| P06c | 三角色 | Android轉盤按壓／自然減速／準確停獎／青蛙收獎；切背景與返回恢復；記錄實測順暢度及使用回饋，不捏造FPS | 部分PASS：Android fixture；真API／跨裝置或實機體驗未驗 |
| P07 | 產品負責人 | 管理網頁及DB查看需登入；唯讀、遮罩、分頁；無公開DB或秘密 | TODO |
| P08 | 產品負責人 | 服務／DB重啟、備份還原後資料與交易狀態一致 | TODO |
| P09 | 產品負責人 | 真實照片／原創青蛙／清爽可愛；成功後才短促收葉子，無循環閃爍或操作阻塞；大字／44px、焦點、減少動畫 | TODO |
| P10 | 產品負責人 | 帳號刪除、隱私資料盤點、API錯誤不洩漏秘密 | TODO |
| A01 | 三角色 | APK安裝啟動、原生返回、鍵盤、定位權限、外部步行導航 | 部分PASS：真APK fixture；真GPS／導航未驗 |
| A02 | 三角色 | Android程序停止／重啟，重新認證與跨裝置狀態一致 | 部分PASS：Android fixture；真API／跨裝置或實機體驗未驗 |
| R01 | 發布驗證 | API36、manifest／權限／debug flag／秘密掃描、unsigned AAB和簽署交接 | TODO |
| R02 | 產品負責人 | 五項交付連結／文件／圖與真實schema一致；無假券或虛構合作宣稱 | TODO |

只有Android裝置上的操作才計入A項；Chromium與API測試提供補充證據。代理扮演三角色不等於三位真人或Google Play封閉測試資格。每次修復只重跑受影響場景與必要回歸，不無限制重跑。

追加核心輪次：21個後端單元／API mock與管理頁browser mock檢查已通過；它們不滿足本表要求的真SQL／跨客戶端／Android证据，所以不把此表改標正式PASS。

API串接輪次：23後端單元／mock、6 App browser合同通過；轉盤確實先收後端結果、含減少動畫與重試／關閉恢復。API36編譯成功。這些仍不滿足真SQL及Android裝置PASS要求。

完整分區證據與受阻清單見 [SECURITY_REVIEW.md](SECURITY_REVIEW.md)。本階段33後端、10前端單元、6App mock合同及帳號頁browser mock通過；所有真SQL／Android要求仍不能標PASS。

刪除工具／GPS階段：48個後端單元／交易替身、10前端單元、9個App browser mock通過；前端靜態建置成功。004僅檔案，owner清除預設停用。真SQL與Android項目仍未PASS。

Android CI基線：已建立公開標準runner有界workflow並執行一次，run 37101823813終態failure。KVM預設權限不足，建置／安裝／啟動前即停止；A01/A02仍BLOCKED。具體證據與待批准最小ACL見 [ANDROID_CI.md](ANDROID_CI.md)。沒有改Azure部署包。

005階段：62後端單元／mock／靜態測試通過，實際權限須部署端驗證。Android run37102663515有安裝／Activity啟動證據，但WebView逾時且角色UI未跑；A01/A02完整驗收仍未PASS。

Android追加證據：run37103516509在commit3b87b045實際完成APK安裝／啟動／WebView UI fixture及force-stop/relaunch並success。消費者預約取消、商家表單、管理員入口、零次數抽獎守衛、記憶體token檢查通過。A01/A02只是部分項目取得證據，原生定位／返回／键盘／導航、真API／跨裝置、完整三角色功能仍未PASS；詳見ANDROID_CI。先前WebView逾時未重現，未宣稱根因已消除。

真SQL rollback驗收：部署端於2026-10-03 06:53 UTC回報15 assertions passed、exit0，執行身分為受限runtime MI、schema005、fixture最後rollback且committed_fixtures_remaining=false。來源是部署端執行報告，不是mock。P01/P03/P05/P10相關局部資料庫路徑已有真SQL證據；P02雙連線搶庫存、持久資料一致性、HTTP及Android真API整合仍待辦。

Android補測：run37104919923 / f16a3a16，2026-10-03 07:06 UTC success。實際API35 emulator鍵盤輸入／Back收鍵盤、GPS拒絕／系統定位關閉回饋、原生Back回個人頁、轉盤連點一次請求／HOME恢復／210度停獎／減少動畫及歷史恢復通過；保留原三角色fixture與程序重啟驗證。A01/P06/P06b/P06c/P09部分證據增加，但GPS允許真定位、實機FPS、外部導航、真API跨裝置及完整正式驗收仍未PASS。詳見ANDROID_CI。

最新真SQL並發／清理證據（2026-10-03，部署端執行、父流程確認）：不同@@SPID的兩個connection經Barrier同步，harness結果201與409，stock0且1 reservation，3 assertions passed／exit0。P02的Service／SQL不變量通過；沒有實際HTTP雙請求或Android串真API證據。owner審阅preview digest後精確apply manifest，commit exit0；移除3 synthetic users及各1 store/product/reservation/request_result，5 tables該批residual均0。schema22 tables／001–005、runtime permissions查詢76 rows／role memberships0不變。前15項rollback及Android extended fixture PASS保留；不新增QA批次、帳號或公開註冊。

取貨增量Android：run37107966613 / 7824868，2026-10-03 07:59 UTC success。原生相機拒絕→手動碼核對→一次明確確認→回覆遺失同key重試通過；掃碼解碼只在browser合成影像測試通過，真鏡頭未驗。新QR真SQL／API rollback腳本已提供但尚未執行；不能沿用舊18 SQL斷言當新流程通過。merchant新店首次設定（自主建立／指派店家）尚未實作，現有流程仍需管理員指派店家。
