# Auth012：Android evidence 與代理政策候選

## Android #25 已完成

- Run https://github.com/HUANGgame/foodsave2026/actions/runs/37136221461 ，job111241176575：success。
- Tested source a1330a0a5ac491b11de5f69f8a5b2e60b33c3b61；後續94f9d0e只變更server endpoint validation，沒有改Android UI／fixture。
- CI fixture APK5329080 bytes，SHA256 f8639a22bf271cf78527e52551027e204801c91c3b32e010f722840bc64e84a3。package tw.foodsave.demo，versionCode5/versionName0.3.1-area-test；v1/v2 signatures verified。
- 16:20:39Z installed/native launch；16:20:52Z email-first register/no auto-login PASS；16:21:02Z invalid reset rejection/successful reset/new login/old password refusal PASS；16:21:07Z current-password change/local logout/no persisted secrets PASS；16:22:55Z force-stop/relaunch/no retained bearer PASS。
- 既有預約、商家、取貨、權限拒絕、區域切換等同輪PASS。合成API與native HTTP bridge攔截，不是真SQL／ACS、真Family來源或實體手機證據。此CI APK沒有公開artifact，也不是最終私人交付APK。

## 官方依據與目前決策

Azure Linux Python文件描述預設Gunicorn前有Nginx，但本專案用custom Uvicorn startup，不能據此推斷本App的直接peer或其IP。官方文件沒有給此App可直接照抄的可信proxy IP。來源：[Python Linux configuration](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)。

App Service的public inbound/outbound IP有各自用途、共享與變動情況；AppService service tag也不是識別某個可信proxy的安全控制。不能把這些地址直接填入Uvicorn trusted peers。來源：[Inbound/outbound IP](https://learn.microsoft.com/en-us/azure/app-service/overview-inbound-outbound-ips)。

Microsoft代理指引以known proxy/network限制header信任，Linux非IIS沒有同等自動設定；ASP.NET範例旗標不是Python設定。來源：[Proxy/load balancer](https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/proxy-load-balancer?view=aspnetcore-10.0)。

目前保持startup `--no-proxy-headers`、registration=false。IP配額使用socket peer，會有共享代理誤限流風險，但沒有直接信任任意XFF。尚未修改startup／網路／Azure設定。

## 待具體證據後送批准的最小差異

1. Azure worker透過既有受控診斷確認直接socket peer、proxy鏈、每一跳ownership，以及外部不能直達Uvicorn8000的邊界。檢查實際執行命令／proxy配置；觀察一次IP或僅見私有IP不足以授信。確認重啟／worker變動時地址行為。
2. 若得到可證明只由受信proxy使用的精確地址集合P1…Pn，候選只把 `--no-proxy-headers` 改成 `--proxy-headers --forwarded-allow-ips='P1,...,Pn'`，保留workers1／concurrency16等全部設定。列表必須是核實後具體值；不得把這個placeholder當可執行批准。無*、0.0.0.0/0、::/0、整段RFC1918或盲信AzureCloud。無新RBAC／資源／網路規則。改動前把實際清單與來源證據交父流程確認。
3. Uvicorn0.52.1只在socket peer受信時讀XFF，從右往左找第一個不受信hop；各個可信hop必須確實附加真實上游來源或清洗header。不能自行取左邊第一個，也不能僅靠header存在、Host、X-ARR-LOG-ID當授信憑據。來源：[pinned Uvicorn code](https://github.com/Kludex/uvicorn/blob/0.52.1/uvicorn/middleware/proxy_headers.py)。
4. 若無法證明有限可信集合與chain sanitation，就保持現狀／registration off；不得為通測信任*。若需要Front Door等邊界，須另列成本、資源和精確network差異核准，不在本次自行建立。官方Front Door限制範例同時用AzureFrontDoor.Backend來源與特定X-Azure-FDID，單看header不夠。來源：[App Service access restrictions](https://learn.microsoft.com/en-us/azure/app-service/app-service-ip-restrictions)。

## 驗收方式（Azure端尚未做）

- 保持registration off、無密碼／token／真寄信。若既有安全診斷不足，先提出短期受保護觀測方案給批准，不能新增公開echoheaders endpoint。不要收集Authorization、Cookie、body或全量header／生產IP清單到公開log。
- 兩個已知不同出口來源A/B，發送相同安全探測；記錄來源類別A/B及derived-IP一致／不同布林結果。重複A必須同一bucket；B應不同。NAT共用出口本來就共用bucket，不誤當bug。
- A分別不带XFF、帶偽造左端、逗號鏈、重複header、帶port、IPv6（若可用）、不合法值。有效derived client必須仍是實際A，或明確拒絕／安全fallback；不得隨假header改變bucket。TCP未授信peer的XFF必須忽略。
- 確認相同IP改變來源port不會分裂配額；測試允許鏈的每個proxy；部署worker重啟後重新確認，未知peer不得被自動加入trusted列表。不要靠大量真登入或真郵件打quota；用隔離合成throttle namespace／受控診斷，需要額外測試寫入先列範圍。
- 本地只驗過installed Uvicorn0.52.1的4個合成cases：untrusted peer忽略header、trusted multi-hop排除偽左端、duplicate headers、IPv4:port正規化。全部PASS；不是Azure ingress驗證。

目前缺少的是Azure實際peer／chain與不可繞過邊界證據，因此沒有可安全批准的具體IP清單。共享SQL password/mail/email配額繼續保留，代理調整不得削弱。
