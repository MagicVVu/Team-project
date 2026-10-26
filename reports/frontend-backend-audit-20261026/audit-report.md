# 前端与正式后端对接审计

审计日期：2026-10-26（Asia/Shanghai）。通过 `ssh magicvvu` 检查正式运行容器，前端对象为当前工作区 Android 源码，Git HEAD 为 `f1f5dcbf0f2208400c0353ed275b0a220c1f6415`。未核验用户手机已安装 APK 是否与此源码一致。

结论：确认 **9 项前端未接入或对接不完整**。其中优先处理云端会话记忆、采购来源与版本控制、家庭共享操作摘要；共享流水的回执按钮还存在明确的权限接口选择问题。商品规划、自动补货和审核风险规则另有 AI/后端未完成事项，不能仅通过增加前端按钮解决。

## 核验依据与限制

- 正式后端镜像 `magicvvu/backend:p9-20261026`，健康接口返回 `0.9.0 / V1-P9`；正式 AI 镜像 `magicvvu/agent:p82-05fa3203a7cb`，维护版本 `V1-P8.2`、引擎 `deepseek`。后端、AI、数据库三容器均 healthy。
- 本次重新运行正式容器 `python -m app.p9_preflight`，16/16 检查通过，明确返回 `business_data_written=false`、`model_called=false`。
- 从正式容器的 `app.openapi()` 导出 52 个路径。服务关闭了公开 OpenAPI，`/openapi.json` 返回 404 是配置行为，不能据此判断业务接口缺失。
- 与本地逐字节 SHA-256 比对，7 个关键后端文件全部一致：products、shopping、inventory、draft_execution、assistant_reads、session_memory 路由及 draft_execution 服务。因此下列本地后端源码引用对应实际运行源码。
- 能力声明取自正式容器中只读能力函数；未冒用任何用户令牌。未登录 HTTP 能力请求返回 401，认证保护正常。
- 未创建账号或家庭，未修改业务数据、服务配置、网络规则，未发送聊天或执行操作，未调用付费模型。此次为运行状态、正式契约、源码及权限逻辑审计；不等同于手机页面与真实账号的完整联合验收。
- 证据：[运行核验](runtime-evidence.json)、[正式 OpenAPI](production-openapi.json)、[关键源码摘要](production-source-hashes.json)。采集脚本 [collect_runtime.py](collect_runtime.py) 通过 stdin 在正式容器运行，未保存到服务器。

## 已确认的前端缺口

以下 `H=/api/v1/households/{household_id}`；P1 表示优先修复，P2 表示后续补齐。这里的优先级是本次审计建议。

| 编号 | 优先级 | 功能 | 正式后端已有能力 | 当前前端与用户影响 |
| --- | --- | --- | --- | --- |
| F01 | P1 | 云端会话记忆、历史与中断恢复 | `GET /api/v1/agent/conversation`、`POST .../conversation/reset`、`POST .../conversation-turns`、`GET .../conversation-turns/{request_id}`；最近30天历史及会话修订 | 仍走旧 `conversation-messages`，历史只在 SharedPreferences；未消费新会话 ID、修订、历史游标、恢复阶段，换设备不能从前端恢复这套服务端记忆 |
| F02 | P1 | 修改旧采购来源与采购版本保护 | `PATCH H/shopping-list/items/{item_id}` 支持来源保留/设置/清空三义、64位 version、operation_id 与永久回执 | 只有新建采购时可选来源；旧采购编辑显示“当前服务不能修改”。DTO 丢弃服务器 version，普通编辑与阈值补货更新均未携带 expected_version，陈旧编辑不能利用 P9 的冲突保护 |
| F03 | P1 | 家庭成员共享操作摘要 | `GET H/operations/{operation_id}/summary` 允许同家庭成员查看脱敏摘要 | 消费流水按钮调用仅操作者可读的 `GET /api/v1/operations/{operation_id}`；查看其他成员操作时按服务端条件必然 404，未使用共享摘要 |
| F04 | P2 | 商品身份创建及批次关联/解除 | `POST H/products`、`PUT H/inventory-items/{item_id}/product`；planning-facts 返回身份来源 | 没有商品创建、显式关联/解除入口或对应调用；StockItem 仅维护批次。无法通过手机建立 P9 商品身份。完整商品选择与聚合展示还受下文服务端边界限制 |
| F05 | P2 | 完整库存事件账本 | `GET H/inventory-events?batch_id=&limit=&offset=`，覆盖新增、移动、消费、开封、丢弃、采购、调整、归档、更正等持久事件 | 当前仅消费流水 + 最近30条 history_json；不能查看完整跨动作时间线及事件关联。新接口分页用 events/next_offset，不能直接套 items/total 解析器 |
| F06 | P2 | 引用原事件的库存更正 | `POST H/inventory-items/{item_id}/corrections`，需 related_event_id、reason、quantity、operation_id、expected_version | 当前“盘点修正”调用 adjustments。它已保持非消费语义，但缺少选择原事件、填写更正原因和展示更正关联的能力 |
| F07 | P2 | 操作成功后的 AI 只读反馈 | `POST /api/v1/operations/{operation_id}/feedback`，返回 available/partial/unavailable/not_applicable | 成功后只保存回执并刷新库存/清单，没有反馈调用或反馈状态展示。原报告“没有公开 feedback 契约”的描述已过时 |
| F08 | P2 | 服务端 AI 库存兼容性检查 | `GET H/inventory-ai-compatibility`，分页返回问题批次、字段、版本及手动修正建议 | 仅本地 `compatible()` 检查名称长度与单位；未接服务端扫描，无法提供家庭库存问题清单，也不能覆盖服务端全部校验 |
| F09 | P2 | 已删除/丢弃/归档批次查看 | 库存列表支持 `status=all/DISCARDED/REVERSED`，单批次 GET 也保留历史访问 | 刷新不传 status，只拿默认 ACTIVE/FINISHED；没有归档列表。删除或丢弃后，前端难以从列表重新定位批次与历史。这是读取入口缺失，不代表后端提供恢复或撤销功能 |

### F01：新会话协议尚未承接

证据：前端 [AgentClient.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AgentClient.kt:12) 仍调用旧入口；[AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt:24) 使用本地偏好存消息，36行只识别旧 conversation_protocol，126行恢复已知本地任务。正式新接口见 [session_memory.py](../../backend/server/app/routers/session_memory.py:12)。

建议顺序：GET当前会话 → 按 requires_reset 初始化 → 持久保存 conversation_id/revision → 发送 turns → 断网先按 request_id GET恢复。需要同时承接分页、当前活动任务和历史状态区分、processing/prepared/result_unknown/completed、明确开始新会话。不能只把旧请求 URL 替换成新 URL。

### F02：采购编辑仍停留在旧契约

证据：[CloudPanels.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/CloudPanels.kt:175) 只在创建时提供来源选择，179行仍宣称服务器不支持修改；[CloudStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt:248) 只在 creating 时写来源。[CloudApi.kt](../../frontend/app/src/main/java/com/example/teamapp/data/CloudApi.kt:22) 的 CloudShoppingItem 没有 version，133行解析也丢弃该字段。

后端 [shopping.py](../../backend/server/app/routers/shopping.py:113) 已实现来源变更、版本冲突和回执重放。前端要保留来源字段省略、UUID、显式null的区别，保留服务器 version，确认后持久化稳定 operation_id 和原请求体。版本冲突后重新核对；不能替换版本自动覆盖。普通数量编辑和 [plan()](../../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt:241) 更新已有采购也应接入版本保护。旧请求仍合法，因此当前并非全部采购保存必然报错，而是缺少新增能力和并发保护。

### F03：共享消费流水使用了个人回执接口

证据：[ConsumptionEventsPanel.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/ConsumptionEventsPanel.kt:70) 对所有事件直接调用 [CloudStore.operationReceipt](../../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt:184)。后端 [operation_for()](../../backend/server/app/services/draft_execution.py:142) 要求 DraftOperation.user_id 等于当前用户；[shared_summary()](../../backend/server/app/routers/assistant_reads.py:43) 则提供家庭级脱敏读取。

场景：成员A消费 → 成员B打开同家庭消费流水 → B点击A的原回执 → 当前代码得到404。此结论来自与正式容器一致的权限条件，未通过新增真实消费复现。建议家庭流水使用共享摘要；个人原始回执仅用于本人执行恢复，不扩大其授权。

### F04—F06：商品身份、完整账本、关联更正

正式实现见 [products.py](../../backend/server/app/routers/products.py:17)、[inventory.py](../../backend/server/app/routers/inventory.py:214)。前端 [toStock()](../../frontend/app/src/main/java/com/example/teamapp/data/CloudApi.kt:125) 只解析原库存字段；[消费流水](../../frontend/app/src/main/java/com/example/teamapp/ui/ConsumptionEventsPanel.kt:38) 只读取 consumption-events；[CloudStore.adjust()](../../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt:235) 调用 adjustments，未调用 corrections。

建议先做只读完整账本及批次历史，再添加带事件选择和原因的更正。消费、盘点、调整、更正保持不同语义；不得把已有调整追认成消费。P9账本只保证持久化覆盖范围内的事件，不包含所有旧CRUD补录，也不证明现实每天记录完整。

商品身份需要成员逐项明确确认，不按同名自动归组。当前公开契约没有商品列表/搜索 GET，也没有商品聚合公开 GET；后端聚合位于内部规划 provenance，不能让手机访问内部服务或把按名称求和当作正式商品聚合。完整商品管理页还需补齐读取契约。

### F07—F09：反馈、兼容扫描与归档读取

反馈接口见 [assistant_reads.py](../../backend/server/app/routers/assistant_reads.py:63)；前端 [refreshReceipt()](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt:407) 只刷新家庭数据。可以接入反馈状态，但反馈不可用时必须继续显示业务已成功，不能重新提交。PLAN_ADD 当前返回 not_applicable，不能展示为采购专用反馈已完成。

兼容扫描接口见 [assistant_reads.py](../../backend/server/app/routers/assistant_reads.py:22)，对照前端 [InventoryContract.kt](../../frontend/app/src/main/java/com/example/teamapp/data/InventoryContract.kt:24)；应按分页扫描并保留 page_only 含义，不能用一页无问题判断整个家庭兼容。

归档列表参数见 [inventory.py](../../backend/server/app/routers/inventory.py:67)，前端 [refreshData()](../../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt:113) 未传 status。可增加单独历史入口，避免把终态批次放回活动库存统计或开放不支持的恢复操作。

## 仍需 AI 或后端配合的事项

1. **P9商品级规划与新重验basis**：后端已给出内部 provenance 扩展，但正式AI的 `p2.tools.RemoteInventoryReader._read()` 只返回 response.json()["data"]，新provenance不会进入其规划 Reader。正式AI仍P8.2；商品聚合已在后端存在不代表模型已经使用。交接见 [P9契约](../../docs/versions/V1-P9/backend-ai-p9-contract.md)。
2. **自动补货提交**：后端 `automatic_planning_commit=false`、`manual_plan_only=true`。已有 `POST /api/v1/drafts/{draft_id}/planning-revalidation` 只读诊断，前端未接 stale/blocked/mismatches 展示；AI新basis仍待适配，完整自动提交未放行。前端 [AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt:391) 主动阻止计算型建议执行，符合当前能力边界，应保留。
3. **审核风险规则**：正式AI返回 active_human_rule_count=0，不能把家庭标签补齐、阈值提醒或未知结果解释为已审核安全。
4. **图片云识别/照片跨设备同步、云ASR/TTS、系统推送/WebSocket**：正式公开契约未提供相应链路。当前照片已实现本地ML Kit OCR及可用时抠图，并非完全没有识别；语音采用系统识别后的文本。这些属于服务端能力/产品范围缺口。
5. **采购专用AI反馈**：已有通用反馈公开入口；PLAN_ADD由于没有库存变更，当前明确 not_applicable。采购专用反馈仍待共同扩展，不能笼统写成“feedback接口不存在”。

## 网络与联合验收

本机使用前端内置测试CA访问 `https://8.134.172.165:8000/api/v1/health`，TCP连接在10秒内超时。随后将同一公开CA通过stdin传给服务器curl，使用 `--resolve 8.134.172.165:8000:127.0.0.1` 访问现有8000 TLS入口，启用证书与IP主机名校验后返回P9健康200。服务器本地TLS正常，当前本机到公网端口的可达性未确认。根因尚未定位，不能断言是安全组、防火墙或前端证书问题；本次未调整网络规则。

建议执行顺序：修复F03与F02 → 承接F01 → 补齐F05/F07/F08/F09 → 基于账本实现F06并协商F04读取契约。自动补货与商品级AI规划另行联合适配。

后续使用专用家庭和两个成员账号验收：共享流水摘要、同时编辑同一采购项、来源设置/清空及旧请求恢复、换设备会话读取、消息中断GET恢复、丢弃后历史查询、带原因更正且不增加消费量、反馈失败仍保留成功回执。本次没有执行这些业务写入。

工作区只新增本审计目录，未修改应用实现，未提交或推送。
