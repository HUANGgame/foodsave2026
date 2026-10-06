# 第二批：店址确认与一公里完整分页（旧基线重建）

父提交：`004e40fdfe11d71e51564f10fa812b7c63cd2dd2`。本批只修改后端、测试及文档，保留第一批 admin/session、同帐号能力与自领保护。没有重试 Library/Azure 通道、执行 migration、修改数据库权限或部署；仍未取得／比对缺失 ZIP，也没有改动网站、APK、全家收藏、7-11 或其他暂停功能。

## 店址 API 与公开边界

- 新店仍用既有 `POST /vendor/store` 接收客户端提供的 GPS 草稿坐标；后端本身不会取得手机 GPS。新增店家的 `location_confirmed=false`、`location_revision=1`。草稿不出现在公开商品／店家与附近查询，也不能被预约，即使服务模式已设为 reservation。
- `GET /vendor/stores/{id}/location` 仅店主可读，返回现有坐标、位置版本、是否已确认、未结算订单数量及 can_move 提示；读取不会发布或保存草稿。can_move 只是当次读取结果，保存时会重新检查。
- `PUT /vendor/stores/{id}/location` 要求既有 session、Idempotency-Key，以及 latitude、longitude、expected_revision 和 `confirm="SAVE_LOCATION"`。没有确认字串、过期版本或跨店请求会被拒绝。GPS 移动／拖曳过程中只应修改客户端草稿，明确保存才调用此 API；前端 UI 尚未接线。
- 保存以 `owner_id + location_revision` 比对并更新，版本加 1；回传数据库实际保存、按 decimal(9,6) 精度舍入的坐标，并转换为 JSON 数值。新店首次保存才公开；已有店址在后续草稿编辑期间仍保持上次已保存的位置。
- 相同 key 和 payload 重试只回传原结果，不再移动或增加版本；不同 payload 重用 key 回覆 409。较旧成功 key 在更新之后重试，返回原版本结果而不会恢复旧位置，客户端应重新 GET 当前值。缓存回传前仍检查当前 owner。

## 预约／移动交易策略

mutate 先锁当前 user row，再取得 `foodsave:store-mode:<store_id>` 的 Exclusive、Transaction-owned applock。移动、预约、取消、完成及既有过期／缺货程序使用同一店家锁。移动在锁内读取店主与版本、检查订单，然后进行带 owner/revision 条件的 UPDATE，写入审计与幂等结果；错误须回滚。

任何仍存在的 `waiting` 或 `expired` 订单都会阻挡保存位置，包括时钟已过期但尚未结算的 waiting，以及旧版已标记 expired 但尚未终结的记录。移动不自动结算、取消、补库存或清除订单；先用既有明确结算流程处理。

预约也在相同店家锁内读取已确认的座标与位置版本，并写入 `reservations.snapshot` 的 latitude、longitude、location_revision。先预约再移动会阻挡；先移动再预约会取得新保存的位置。移动不会改写已有订单快照。测试只验证服务控制流程与两种串行顺序，**并未证明 SQL Server 中真实并发锁行为**。

## 数据库筛选与分页契约

新增已登入查询：

- `GET /nearby/stores?latitude=...&longitude=...&limit=50&cursor=...`
- `GET /nearby/products?latitude=...&longitude=...&limit=50&cursor=...&store_id=...`（store_id 可省略）

返回 `{items, next_cursor, radius_m:1000, page_size}`；limit 范围 1–100，默认 50。坐标必填且有限值，固定一公里，不接受客户端扩大 radius。只纳入已确认店址、有效 consumer/vendor 店主；商品另保留有效／未过领取期限条件。无商品的有效店家仍会出现。

SQL CTE 先对全部合资格店家计算球面大圆距离并过滤 `distance_m<=1000`，再查商品／店家、应用 cursor 和 TOP(limit+1)。距离定义为平均地球半径 6371008.8 米的 haversine 球面距离，非道路距离；计算夹限防止浮点误差造成 SQRT/ASIN 越界，并涵盖日界线与极区。

以唯一、不可变 id 作为 keyset 排序（**不是按距离排序**）；next_cursor 基于最后一笔已返回 id，不使用 offset，等距离也不重复或跳过。cursor 验证版本、UUID、查询中心、资源类型及店家过滤范围，所有值作为 SQL bind 参数。cursor 是位置描述，不是权限凭证。客户端必须持续取到 next_cursor 为 null，才能宣称完整附近结果。

分页是逐页实时读取，不是跨请求数据库快照；翻页期间新店或位置变化可能要下一轮刷新才出现。中心改变或前景 30 秒刷新时，客户端应从第一页重新收齐；本批尚未改动客户端刷新实现。

旧 `/stores`、`/products` 与 `/vendor/catalog` 保留原数组／物件契约，移除 200 笔截断；公开旧列表也排除草稿与无效店主。**旧 API 仍是完整清单，不带一公里分页且可能产生较大响应**；后续网站／APK 必须接新 nearby API 才能享有有界查询响应。商家目录也返回坐标与位置版本，商品不再截断；其分页 UI 留待后续。其他历史记录／审计列表的既有上限未改动。

## 新 migration 与发布限制

新增 `014_store_location.sql`，仅增加 location_revision、location_confirmed 和约束／默认值；不改变 owner、role、session 或权限。按已验证旧基线，原有店址已公开，故现存资料初始化为 confirmed=1，之后新增店家默认 0；不重写坐标。真正执行前仍须核对正式 schema，不能对未核对来源的其他版本套用该假设。

migration 要求调用端已经开启有效交易；提供给既有 owner-run migration runner，不在启动时执行。新开店与 health/ready 要求 014 marker；marker 仅代表 runner 记录，不能代替 SQL、权限、锁或业务验收。

旧权限模板只有 stores.service_mode 的 UPDATE 权限，未提供 latitude、longitude、location_confirmed、location_revision 的更新权限。本批**没有修改 grant 文件或实际权限**，新保存操作在旧权限下可能被拒绝；任何将来的最小权限调整须独立审查授权。没有把检查失败改成提升权限或绕过限制。

T-SQL DDL/查询编译、Azure SQL 并发、索引／执行计划、实际 runtime 权限与 SQL 回复方案都尚未验证，因此不能部署。若以后已产生未公开草稿，直接回退到不认识 confirmed 的旧后端可能公开草稿；不可把 Git bundle 还原当成可直接执行的正式回退方案。

## 本次测试与备份

完整命令：`PYTHONPATH=.:backend /workspace/foodsave-rebuild/venv/bin/python -m pytest -c backend/pytest.ini backend/tests -q`。

最终结果：**359 passed，1 warning，13.99 秒**，记录 `/workspace/foodsave-rebuild/batch2-tests-final.log`；`git diff --check` 通过。警告为既有 Starlette/httpx TestClient 弃用提示。

新增 27 项位置服务/API控制流程案例、30 项附近查询案例及一个 migration 文字检查参数案例。涵盖 draft、显式确认、owner/revision/CAS、重试、回滚、waiting/expired、顺序与快照、Decimal 数值契约、readiness、400 笔远店之后的 331 间近店、单店 305 件商品、最后页、等距离、删除前页项、日界线、极区、约一公里两侧、无效坐标／cursor／半径覆写。

附近查询在本地 SQLite 执行实际 CTE/WHERE/JOIN/ORDER，仅将 T-SQL TOP 语法转换为 LIMIT，并补数学／时间／JSON 函数。这是查询语义比对，**不是 T-SQL 编译、Azure SQL integration、真实 SQL 竞态或效能验证**。位置测试为内存服务/API doubles；没有实际 GPS、端到端网页、APK 或真机验收。

修改前 `/workspace/foodsave-rebuild/backups/batch2-before.bundle` SHA256：`691fab2d6ee43f3456f6b4b4e1aede7476d1bb2353f75155aab930d71d215e64`。bundle verify、独立还原 `/workspace/foodsave-rebuild/batch2-restore` 的 fsck 及 256 档逐一 SHA256 比对均通过，清单为 `backups/batch2-before-files.json`。每次覆写另先产生并核对 `backups/edits` 副本，提交前由独立检查员审查。

这些备份与测试日志只在本次工作环境，备份包含第一批 Git 程式与文档，不包含最新正式部署、正式 SQL、APK 或未匯出成果。源码缺失、正式通道受阻、权限与真实 SQL 验收、网站／APK 整合仍为后续事项。
