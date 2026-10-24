# AI、后端与 Android 前端功能对齐报告

日期：2026-10-24。对象：当前 `dev` 工作区、Android `1.2.0-test / versionCode 4`、正式服务器 P8 AI 与新版后端。

## 1. 结论与建议顺序

前端已经具备 P8 聊天、任务持久化、草稿修改/取消、确认与回执恢复的基础实现。当前主要工作不是重建聊天窗口，而是补齐真实业务数据入口、结构化结果展示和库存页面的业务语义。

建议新增或扩展六个业务模块：

1. **物品资料与盘点中心**：补货偏好、真实盘点、逐日记录完整性、标签/储存资料，四个分区共用一套规划事实 API。
2. **AI 结果卡片与关注概览**：消费统计、耗尽预测、风险解释、补货建议、资料不足时的补录入口。
3. **消费流水**：真实消费事件、批次与原操作回执关联。
4. **批次操作中心**：库存详情中的正式消耗、开封、部分/全部丢弃，以及指定批次问答。
5. **家庭管理**：退出、移除成员、管理员任免、转让、解散。
6. **采购来源与建议复核**：待购关联真实库存批次，区分最低库存差值和本次 AI 计算建议。

在这些页面之前，必须先修正三个底层问题：**手动“消耗”目前只是普通调整；单位/分类不完全符合 AI 契约；库存模型丢失开封和生命周期状态。** 否则新增预测页面仍会持续缺数据或报数据不兼容。

推荐开发顺序：业务语义与 DTO → 资料/盘点入口 → AI 结构化结果 → 库存批次操作与消费流水 → 家庭及采购扩展 → 真机闭环验收。

## 2. 审计依据与范围

本次检索 Android 主源码 **41 个 Kotlin 文件、6250 行**，重点追踪页面 → Store → Client → 后端路由，以及 AI 的消费、预测、补货、风险、概览、续接实现。检索索引见 [frontend-ai-alignment-20261024.json](frontend-ai-alignment-20261024.json)。结论基于调用链，不以某个关键词是否出现作为唯一判断。

服务器本轮只读复核：

| 项目 | 实际状态 |
|---|---|
| 后端 | `magicvvu/backend:p8-771374b-20261024` |
| AI | `magicvvu/agent:p8-0175b52f054c`，DeepSeek，`chat_policy_version=p8-chat-1` |
| 数据库 | `20261023_0010` |
| 六类执行动作 | ADD、MOVE、CONSUME、PLAN_ADD、OPEN、DISCARD 均开启 |
| 会话/草稿控制 | `backend-conversation-1`、`chat_controls=true`、`execution_preview=true` |
| 可信引用 | 已开启 |
| 规划资料 | `backend-planning-facts-1`，GET/PATCH 已部署 |
| 自动计算补货直接提交 | `automatic_planning_commit=false` |
| 已审核风险规则 | 0 条 |
| 音频上传到 AI | 不支持；当前 AI 接收文本 |

本次未修改业务代码、未安装 APK、未执行设备 UI 测试、未调用付费模型、未写入正式业务数据。“有实现”不等于已经完成本次线上手机联合验收。旧 P7/P8 文档中的“尚未部署”应以本轮运行状态及 [正式部署记录](backend-ai-alignment/deployment-20261024.md) 更新。

## 3. 前端已经具备的功能：应保留并联验

| 功能 | 当前实现 | 本次判定 |
|---|---|---|
| 登录、注册、退出、账号缓存 | CloudApi、CloudStore、CloudCredentials，Keystore 保存令牌 | 已有 |
| 创建/加入/切换家庭、重命名、邀请码、成员查看 | CloudFamilyPanel + CloudStore | 基础管理已有，角色操作缺失 |
| 云端库存 CRUD、数量调整、阈值、购物与购买入库 | CloudStore + InventoryStore | 已有；普通调整与消费语义需要分离 |
| 中文/英文 UI、浅色/深色、四栏导航 | i18n、LightDesign/DarkDesign、MagicApp | 已有；新模块应共用这些基础设施 |
| 能力发现及 15 秒缓存 | CloudApi.verifiedCapabilities、TargetCheckCache | 已有；新资料/预览能力字段尚未使用 |
| 新会话入口 | AgentClient.conversation、AssistantStore.dispatchMessage/sendConversation | 已调用 `conversation-messages`，无需重建 |
| 多轮补字段、批次候选 | 当前 task/revision 绑定，候选按钮和补字段调用 | 已有；需覆盖多字段与历史修订联验 |
| 自动对话引用 | 服务端 conversation binding，前端保存活动任务并展示引用提示 | 已有基础；没有独立“从库存详情指定这批”的适配 |
| 草稿自然修改/取消 | control()、chat_controls 分支、校验后 preview | 已有 |
| 开封/丢弃的聊天确认 | editable 字段、日期、discard_mode、确认弹窗 | 已有；不是库存详情的独立操作入口 |
| 正式提交和回执 | commit、execution、operation，校验身份/修订/操作 ID | 已有 |
| 断线/关闭窗口后的恢复 | AssistantStore 持久出站正文、请求/操作 ID，GET 核实 | 已有；继续扩展新资料写入的恢复 |
| 采购差值推荐 | 按 `minimum - quantity` 生成手动计划 | 已有；不是基于消费历史的 AI 规划 |
| 相机/选图/语音录入 | AddFlow，系统中文语音转文本，parseVoice 后填表 | 已有；不是聊天语音输入或图片 AI 识别 |

主要证据：

- [AgentClient.kt](../frontend/app/src/main/java/com/example/teamapp/data/AgentClient.kt)：12–22 行已有会话、控制、预览、任务、确认与回执方法。
- [AssistantStore.kt](../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt)：146 行发送、217 行会话控制、267 行草稿校验、293 行任务接收、429 行确认、456 行取消。
- [CloudAssistant.kt](../frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt)：22 行聊天窗口，101 行任务卡，包含候选、编辑、确认、回执和恢复入口。

### 关于执行预览：需要完善，不能标为完全缺失

`AgentClient.preview()` 已声明独立 `/execution-preview` 调用，但主流程尚未调用它。当前确认前通过 `chat-control` 的“校验草稿”获得预览，后端复用同一业务校验，这条路径已经存在。

应补能力分支：有 `chat_controls` 时复用当前流程；只有 `execution_preview` 时调用独立 preview；结果需与当前 task/draft 修订及 edits 绑定。表单变化后继续清除旧预览。无需在同一次确认中重复调用两个等价预览接口。

### AI 新增能力逐项映射

| AI 能力 | 后端承接 | 前端现状/补齐方向 |
|---|---|---|
| 缺字段中文提示、候选序号、一次补多个字段、问候/帮助后继续任务 | conversation-messages 与内部 reply-resolution | 主流程已有，补联合验收及更清晰的当前对象提示 |
| 换话题/清引用、可信对象追问位置等 | 会话绑定、引用期限与服务端权限检查 | 自动引用已有；详情指定批次入口缺失 |
| 新增、移动、消耗、明确数量采购、开封、部分/全部丢弃 | 草稿、preview/control、commit、操作回执 | 聊天确认已有；详情操作语义与持久状态待完善 |
| “已经用完”按当前批次剩余量生成消费草稿 | CONSUME 的正式事务，终态 FINISHED | 可通过聊天承接；详情可加“全部用完”，仍须核对真实批次与余量 |
| 按位置查询物品、查看待定位物品 | 消息网关转发 QUERY_LOCATION_ITEMS | 当前可显示回复；可增加位置分组/明确批次卡片 |
| 记录消费统计（查询窗口 1–28 天） | 规划快照 + 正式事件账本 | 无结构化统计卡/流水接入 |
| 耗尽日期/剩余天数预测 | 完整记录日、消费事件、盘点证明 | 无资料入口与结构化预测卡 |
| 最低库存/记录历史补货建议 | 偏好、待购完整性、版本与快照 | 仅有本地阈值差值推荐，缺 AI 建议依据展示 |
| 风险问答与缺失资料指导 | 标签/储存/开封事实、已审核规则 | 有文字回复，缺风险证据卡和补资料跳转 |
| 关注概览，风险/规划独立可用状态、截断提示 | 消息网关支持 QUERY_OVERVIEW | 当前首页仍为阈值/登记日期提醒，缺 AI 分区概览 |
| 提交后反馈，区分已提交与资料刷新失败 | 已有内部回执读取；缺公开 feedback 适配 | 后端先补公开契约，再加反馈卡 |

AI 第一次理解最多一次模型提取，受支持的结构化续接/字面解析无需再次付费；前端不应通过另发新任务来“补字段”或自动重试未知结果。此为协议和源码行为，本次未做付费调用复测。

## 4. 应优先修复的具体问题

### F01 / P0：库存详情的“消耗”不会进入消费统计

调用链：

`MagicApp.QuantityAction("消耗库存") → InventoryStore.changeQuantitySynced(item, -amount) → CloudStore.adjust() → POST inventory-items/{id}/adjustments`。

这是普通数量调整，只产生库存 history，不产生正式 `BusinessEvent(event_type=Consumed)`。AI 消费统计读取正式事件账本；不能把普通扣减推测成消费，也不能把丢弃混入消费。

证据：[MagicApp.kt](../frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt) 246–270 行、[InventoryStore.kt](../frontend/app/src/main/java/com/example/teamapp/data/InventoryStore.kt) 146 行、[CloudStore.kt](../frontend/app/src/main/java/com/example/teamapp/data/CloudStore.kt) 180 行；对比后端 [draft_execution.py](../backend/server/app/services/draft_execution.py) 300 行起的正式事务。

前端要求：将“消耗”“盘点修正”“增加库存”拆开。消耗使用 CONSUME 草稿与正式确认，盘点修正保留调整入口，丢弃使用 DISCARD。不能继续共用一条 adjustments 请求再仅改变提示文案。

后端边界：当前没有独立的 `POST inventory-items/{id}/consume/open/discard` 公共接口。短期可复用查询/候选 → 可信批次引用 → 草稿 → 校验 → commit。若要纯表单、无需 AI 理解的库存操作，需后端补**结构化草稿创建契约**或等价业务入口，复用现有事务和回执；具体路径应由后端正式定义，不能在前端猜一个 URL。

### F02 / P0：单位、分类和名称范围需要统一

1. `CloudShoppingEditor` 新建采购默认单位为“件”；语音简单解析也允许杯、斤、罐等值。后端普通库存/采购可保存部分此类字符串，但 AI 单位白名单不包含“件”等单位。购买入库后会形成 AI 无法读取的批次；完整库存查询可能因此整体返回数据冲突。
2. 录入表单保存“食品 / 日用品 / 其他”，AI 规划类别只识别 `food / household / medicine / unknown`，旧中文值目前会降为 unknown。界面语言切换不能改变协议值。
3. 普通库存名称上限是 200 字，AI 名称上限 80 字；不能让用户保存后才发现该物品无法使用 AI，也不能偷偷截断旧名称。

证据：[CloudPanels.kt](../frontend/app/src/main/java/com/example/teamapp/ui/CloudPanels.kt) 164 行；[AddFlow.kt](../frontend/app/src/main/java/com/example/teamapp/ui/AddFlow.kt) 163–165 行；[ai_inventory.py](../backend/server/app/services/ai_inventory.py) 12–40 行；[planning_context.py](../backend/server/app/services/planning_context.py) 108 行。

前端要求：共享单位字典和别名归一化，展示中文但发送 canonical 值。当前支持：盒、瓶、包、袋、个、卷、片、吨、台、ml、L、g、kg 及已有毫升/升/克/千克/公斤别名。未知容器不能猜容量。旧不兼容记录应展示核对入口，不能自动改写。

分类采用显示标签与协议枚举分离；对旧库存做兼容显示，并通过用户核对的风险资料填写 canonical 类别。药品保持独立类别，不能当普通日用品生成补货建议。

### F03 / P0：库存 DTO 丢失开封/终态，数量仍以 Double 贯穿

后端 `StockResponse` 已返回 `opened_at` 和 `status`，但 `StockItem` 没有这些字段，`JSONObject.toStock()` 未接收它们。因此聊天能开封，普通详情却不能可靠显示“何时开封”和“批次是否结束”。最近 30 条文字 history 不能代替结构化事实。

应新增 `openedAt`、`lifecycleStatus`、必要的资料摘要，并在详情、列表状态与可用操作中使用。新资料/统计 DTO 使用 Decimal 字符串或 BigDecimal，不要把业务计算继续放在 Double；现有普通表单也应前置校验库存六位、采购三位精度。

证据：[Inventory.kt](../frontend/app/src/main/java/com/example/teamapp/data/Inventory.kt) 7 行；[CloudApi.kt](../frontend/app/src/main/java/com/example/teamapp/data/CloudApi.kt) 124–135 行；后端 [shopping_schemas.py](../backend/server/app/shopping_schemas.py) 的 StockResponse。

## 5. 模块一：物品资料与盘点中心（P0，完全缺少新接口接入）

建议放在“库存详情 → 资料与盘点”，四个分区共用一个 `PlanningFactsRepository/Store`，按服务器、用户、家庭、库存批次隔离缓存。前端目前没有 `planning-facts` 路径、DTO 或页面。

该模块属于已登录家庭云端数据；游客模式继续保留本机边界，不能假装资料已同步到服务器。

公共接口：

`GET/PATCH /api/v1/households/{household_id}/inventory-items/{item_id}/planning-facts`

### 5.1 补货偏好

| 字段 | UI / 校验 |
|---|---|
| minimum_stock | 非负 Decimal，可未知；与旧 minimum_quantity 的来源关系明确显示 |
| coverage_days | 希望覆盖天数，1–365，可未设置 |
| lead_days | 提前期，0–365，可未设置 |
| order_unit + pack_size | 必须同时填写；一个订货单位含多少当前库存单位，不猜包装量 |

当前“规则设置”只更新 `minimum_quantity`，没有其余字段。新 minimum_stock 会覆盖规划读取中的旧阈值；后续旧阈值变化又可能让原偏好失效。建议统一阈值设置入口，或明确显示当前来源并在变更后重新读取、提示核对，避免双套阈值互相覆盖。

### 5.2 库存盘点核实

显示当前数量/单位/版本，用户实际盘点后确认。请求 `stock_verification={quantity,unit}`。与库存不一致返回 `STOCK_COUNT_MISMATCH`：先走现有库存调整、刷新版本，再由用户重新确认盘点。

新增“已核对时间/来源”“待盘点/已失效”状态。不能因为刚编辑过物品就自动标为已盘点；业务变化后旧证明会失效。AI 默认还检查 168 小时新鲜度，最终以服务规则和返回原因处理。

### 5.3 消费记录完整性日历

每个已结束的家庭业务日期填写 `records_complete`、`stockout`、`unexplained_adjustment`。允许用户明确核对一组日期，但不能默认把所有天数选为“完整”。今天/未来不可提交，每次最多 366 天、总计最多 3660 天。

UI 区分：未知、记录完整、记录不完整、缺货、无法解释的调整、原证明已失效。没有事件的日期不自动当作零消费。撤销某天通过 `records_complete=false`，不是删除整个 coverage 或提交空数组。

### 5.4 标签与储存资料

| 字段 | 选项/边界 |
|---|---|
| category | food / medicine / household / unknown |
| label_date_type | use_by / best_before / expiry / unknown |
| label_context_valid | true / false / 未知，必须由用户核实 |
| storage_condition | ambient / refrigerated / frozen / 未知 |
| label_storage_condition | 包装要求的保存条件；不从位置名称推断 |
| is_opened | true / false / 未知；已存在 opened_at 时不能否认已开封 |

原库存过期日期仍通过 `expires_on` 保存，实际开封日期走 OPEN；“资料页”不能绕开开封事务直接假造 opened_at。标签日期缺失却声明 label_context_valid=true 会返回 `LABEL_DATE_REQUIRED`。

### 5.5 统一读写、冲突与恢复契约

首次 GET 获取 `inventory_version`、`facts_version`、`invalidated_sections`、资料与 provenance。PATCH 至少包含：

```json
{
  "operation_id": "11111111-1111-4111-8111-111111111111",
  "expected_inventory_version": 3,
  "expected_facts_version": 1,
  "source": "家庭成员手动盘点核对",
  "stock_verification": {"quantity": "5", "unit": "盒"}
}
```

这是格式示例，版本和数量必须来自实际 GET 与用户核对。资料写入本身返回 `inventory_written=false`。

- 区块未提供表示不修改；preferences/risk_facts/stock_verification 显式 null 表示清除；非空区块内部完整替换。因此先读取当前资料，避免只传一个字段时把同区块其余偏好清空。
- Android JSONObject 清除必须使用 `JSONObject.NULL`；不能把“未提供”和“显式清除”混成一种 nullable 状态。
- 一个批次只有一套 facts_version，四个区块应共享版本与写入队列，不各自缓存、并发覆盖。
- 新请求先持久保存 operation_id、原正文和作用域；结果未知时仅原 ID/原正文重放。返回旧回执不等于当前资料未再变化，随后 GET 核对最新状态。
- 对 `INVENTORY_VERSION_CONFLICT`、`PLANNING_FACTS_VERSION_CONFLICT` 重新读取并由用户复核；不能自动塞入新版本继续提交。
- `invalidated_sections` 要显示为待重新核对，不能伪装成用户从未填写。

## 6. 模块二：AI 结构化结果与关注概览（P1）

当前 `AssistantEntry` 保存了原始 result，但 `AssistantTaskCard` 主要展示 reply、候选、草稿和回执。没有消费、预测、风险、建议等结构化卡片，不能把“服务器返回一段文字”当作完整页面接入。

| 结果字段 | 建议组件与内容 |
|---|---|
| consumption_summary[] | 消费总量、有效事件次数、观察天数、统计窗口、资料状态；可点进真实流水 |
| forecast[] | 已登记库存、日均记录消费、参考剩余天数/日期、计算条件、无法预测的具体原因 |
| recommendations[] | 当前量、待购量、目标量、建议数量/单位、minimum_stock 或 recorded_history 来源 |
| risks[] | attention、level、事实证据、缺失字段、建议行动、审核来源；unknown 不能显示安全 |
| guidance[] / data_gaps[] | 可操作的补录任务，按 batch_id 导航到资料页对应分区 |
| sections[] | 风险与规划分别显示 available/partial/unavailable、读取时间和快照，不能一个模块失败就伪报全成功 |
| truncated / total_count | 明示仅展示部分结果；概览最多展示部分条目，不自行伪造后续分页 |

入口：保留现有聊天窗口，在库存详情或助手中增加“消费统计”“还能用多久”“本次补货建议”“今天需要关注什么”快捷入口。当前拉绳仅有查库存、临期、补货三个快捷项。

**无需让手机直连 AI**。上述查询可以通过已有 `conversation-messages` 发送明确文本，读取返回的 `task.result`。AI 的 `/consumption/query`、`/forecast/evaluate`、`/procurement/suggest`、`/risk/evaluate`、`/overview/query` 是内部接口，前端不能持有内部令牌直接调用。当前后端没有为它们逐一提供独立公开查询路由；需要结构化筛选/统计主页时，再由后端定义公开查询适配。

AI 预测条件包含至少 14 个连续完整日、至少 5 个有效消费事件且分布于至少 3 个日期，以及可用库存核对依据。界面必须解释进度和缺失项；不能从“没有预测日期”推导为库存足够，也不能用缺失资料显示 0 消费。

现有首页提醒按本地 expiry/minimum 计算，名称应保持“登记日期/阈值提醒”；新的 AI 风险结论独立展示。不要把 `StockStatus.label=状态正常` 当作食品安全结论。当前审核规则为 0，缺少专业结论属于 AI/业务审核依赖，不能由前端补文案变成“安全”。

## 7. 模块三：批次操作中心与消费流水（P0/P1）

### 7.1 库存详情操作入口

在现有编辑、增量、消耗、采购之外增加：

- **开封**：展示当前 opened_at，只要求有效日期，不填写数量。重复开封或批次终态时使用后端原因提示。
- **部分丢弃**：明确数量/单位，展示预计剩余与独立 Discarded 事件。
- **全部丢弃**：显示“当前批次全部余量”，不让用户编辑 quantity/unit/mode，不把删除记录当作丢弃。
- **询问这批**：展示名称、位置、数量、批次身份；不要只拼接名称后假设对象唯一。
- **正式消耗**：修复 F01，确保产生 Consumed。丢弃和盘点差额均不计入消费。

复用现有 AssistantStore 的状态、确认和回执恢复，不在详情另建一套直接写库存的“成功”状态机。UI 应扩展开封/丢弃的版本、前后状态展示；当前详情和聊天辅助批次信息主要覆盖 MOVE/CONSUME。

### 7.2 可信批次引用的适用方式

聊天内“查询唯一对象 → 它在哪里”等自动引用已有服务器实现，不需要强制额外调用 reference-messages。

独立指定批次入口可新增 AgentClient.referenceMessage，调用：

`POST /api/v1/agent/reference-messages`

请求字段为 `household_id,text,request_id,source_task_id,source_revision,batch_id`。来源必须是可核验的原 AI 任务事实/候选，不能直接拿库存列表 ID 伪造 source_task。需要时先查询得到来源任务，再明确绑定选中的批次。引用最长 15 分钟，事实每次重读；多对象、过期、删除、版本变化、换家庭都应重新核对。

### 7.3 消费流水

对接 `GET /api/v1/households/{household_id}/consumption-events?limit=100&offset=0`。保存 event ID、operation_id、inventory_item_id、quantity、unit、occurred_at、before/after，支持按批次筛选、查看原业务回执。

该接口目前只返回 Consumed，`planning_history_complete=false` 也不代表数据错误：事件分页列表本身不能证明日常记录完整。每日曲线可以按已读完的真实事件绘制，但覆盖不明的日期不能补零。日期按家庭时区解释。

若产品要求同时分页浏览开封、移动、丢弃和纠正等全量流水，需要后端补统一事件读取契约；当前不能把仅消费接口包装为“全部业务事件”。已有最近 30 条 history 仍可保留为近期说明。

## 8. 模块四：采购来源、偏好和建议复核（P1）

当前 `CloudStore.plan()` 从库存添加采购时会传 source_inventory_item_id，已有正确关联。独立 `saveShopping()` 新增采购不传关联，编辑表单也没有来源选择。规划读取遇到未关联/单位不兼容的待购时，会将 pending_complete 降为 false，以防重复采购。

应增加：

1. 新建采购时可选择“关联现有库存批次 / 新物品暂无关联”，选择批次后带真实 `source_inventory_item_id`。
2. 清单显示关联来源、待购数量、已购状态；资料不足时解释为什么 AI 补货建议需要核对。
3. 将“按最低库存差值补货”和“本次 AI 建议”分开展示，说明数量来源、已待购扣除和包装单位。
4. `automatic_planning_commit=false` 时不开放计算建议直接 commit。短期只能让用户独立明确手动采购数量，不能静默把 AI 建议改标为 user_input 来绕过重算。

后端缺口：当前 `ShoppingItemUpdate` 只允许 name/quantity/unit，不能 PATCH 既有 source_inventory_item_id。因此“给旧待购补关联/改关联”需要后端新增受认证的关联编辑契约；前端不能擅自删除重建已有采购记录来冒充更新。

## 9. 模块五：家庭管理扩展（P1）

当前成员被转换成 `List<String>`，丢失 user_id、role、joined_at 的结构，UI 只逐行 Text。先改成结构化 CloudMember DTO，再做角色操作。

| 功能 | 接口 | 权限与交互 |
|---|---|---|
| 退出家庭 | POST `/api/v1/households/{h}/leave` | 普通成员/管理员；所有者须先转让或解散 |
| 移除成员 | DELETE `/api/v1/households/{h}/members/{u}` | 所有者可移除非所有者；管理员只能移除普通成员 |
| 设置/取消管理员 | PATCH 同一 members/{u}，`role=admin/member` | 仅所有者 |
| 转让家庭 | POST `/api/v1/households/{h}/transfer-ownership`，`new_owner_user_id` | 仅所有者，目标须为已有有效成员 |
| 解散家庭 | DELETE `/api/v1/households/{h}`，`confirmation_name` | 仅所有者，输入当前完整家庭名，明确删除范围 |

成功后的 204 空正文已可由 CloudApi 接收。刷新家庭列表/角色和成员，切走失效家庭，清除活动引用与新资料缓存；保留其他家庭的历史隔离。权限最终以服务器为准。

## 10. 需要完善的公共基础设施（P0/P1）

### 能力、错误与日期

- 在已有 discovery 上读取 `planning_facts_protocol`、`execution_preview`、`household_timezone`。不修改当前严格 TLS/服务身份规则，不为上线新模块放宽到任意服务器。
- `AssistantStore.send()` 的旧协议时区当前硬编码 Asia/Shanghai，与当前部署一致；新增日期页面应读取能力中的家庭时区，不能跟随界面英文设置改协议日期。
- `ChatMessages` 增加规划资料专用码：STOCK_COUNT_MISMATCH、PLANNING_FACTS_VERSION_CONFLICT、INVENTORY_VERSION_CONFLICT、COVERAGE_DAY_OUT_OF_RANGE、COVERAGE_LIMIT_EXCEEDED、LABEL_DATE_REQUIRED、OPENED_STATE_CONFLICT、HOUSEHOLD_TIMEZONE_MISMATCH、OPERATION_ID_CONFLICT。
- 当前通用 409/422 文案主要解释库存数量/购买，不能准确指导盘点和覆盖声明。新模块要保留原表单、指出具体原因和下一步，而不是所有错误都显示“名称数量不能为空”。
- 规划资料写入使用独立的稳定出站记录；不能因为界面重建生成新的 operation_id。复用已有作用域隔离原则，不需要重写整个聊天 outbox。
- 取消按钮与文字“算了”的当前任务/引用收尾要专门联验：文字控制分支会清理 activeRequestId/referenceLabel，直接 cancel() 分支目前只改任务条目状态。应统一展示，并用服务器支持的清引用流程同步会话，不能只在本机清空后假设服务端也已解绑。
- 新字段、错误和模块须同时提供中文/英文 UI。用户名称、位置、单位、AI 原文和协议枚举不自动翻译。

### 语音聊天（P2，可选）

现有语音入口是“系统识别 → parseVoice → 录入表单”，没有把识别原文发送到云端助手。可在聊天输入增加麦克风，识别结果先显示给用户，确认后作为文本走现有 conversation。保留识别失败时手动输入。

AI 当前不支持音频上传。图片 AI 识别、云端 ASR、TTS、系统推送、WebSocket 和自动下单都不是本轮已部署能力，不应作为“只接前端即可完成”的必做项。

### 提交后 AI 反馈（P2，后端前置）

AI 有内部 `/feedback/after-commit`，但后端没有对应的公开 feedback 适配，前端也没有调用。需要该产品功能时，后端先定义以已认证 operation_id 为入口的公开契约，核实回执并调用 AI；前端不能直接访问内部接口。当前 PLAN_ADD 无库存 batch_versions，内部库存回执不适用，采购反馈还需明确规则。

反馈失败只提示“已提交，刷新/解释暂未完成”，不能把 COMMITTED 改成失败或再次提交业务操作。

## 11. 前端接口对接清单

| 接口 | 当前前端 | 应做工作 |
|---|---|---|
| GET health、execution-capabilities | 已调用 | 读取新增能力/时区字段，沿用缓存 |
| POST conversation-messages | 已调用 | 联验多字段补充、序号、换话题，不重复开发 |
| POST tasks/{id}/chat-control | 已调用 | 联验自然修改/取消、nullable 日期、已取消草稿 |
| POST drafts/{id}/execution-preview | Client 已声明，未走主调用 | 增加独立预览能力分支，避免与 control 双重调用 |
| POST reference-messages | 未封装 | 仅为有真实来源任务的显式批次入口接入 |
| GET task/draft/execution、POST commit/cancel、GET operation | 已调用 | 保留原请求、版本与回执校验，扩展详情入口复用 |
| GET/PATCH inventory-items/{id}/planning-facts | 无调用/DTO/UI | P0 新增四分区资料中心和持久写入恢复 |
| GET households/{h}/consumption-events | 无调用 | P1 新增分页消费流水 |
| 库存 CRUD/adjustments | 已调用 | 修复“消耗”误用调整；接收 opened_at/status |
| 购物创建/编辑/购买 | 已调用 | 新建来源选择、单位统一；旧待购改关联待后端契约 |
| 家庭 leave/member role/remove/transfer/delete | 无调用 | 结构化成员与角色操作 UI |
| internal/v1/*、AI 专用地址 | 不应接手机 | 继续由后端持有服务令牌调用 |

完整参数与返回约束以 [当前后端 OpenAPI](backend-ai-alignment/backend-openapi.json)、[规划资料 DTO](../backend/server/app/planning_fact_schemas.py)、[现有执行 DTO](../backend/server/app/execution_schemas.py) 为准。

## 12. 建议任务拆分

| 优先级 | 任务 | 类型 | 完成标志 |
|---|---|---|---|
| P0-1 | 修复手动消耗的业务语义 | 前端 + 选定后端接入方式 | 正式 Consumed 事件与回执产生一次 |
| P0-2 | 统一 DTO、开封/终态、单位/类别/数量 | 前端 | 普通表单创建的数据可被 AI 读取，详情不丢字段 |
| P0-3 | 规划资料 Store 与四分区页面 | 前端，现有后端可用 | GET/PATCH、版本冲突、清除与重放全部跑通 |
| P0-4 | 新资料错误/作用域/出站保存 | 前端 | 断网、换家庭、重建后不误写、不换 ID |
| P1-1 | 统计/预测/风险/建议结构化卡片 | 前端 | 有结果可核实，无资料可跳转补录 |
| P1-2 | 库存详情开封/丢弃/批次问答 | 前端 + 可选结构化草稿契约 | 指定真实批次，预览后确认，终态不重执行 |
| P1-3 | 消费流水 | 前端 | 分页、按批次查看、回执关联 |
| P1-4 | 家庭完整管理 | 前端 | owner/admin/member 角色操作与失权刷新 |
| P1-5 | 采购新建关联及建议来源 | 前端 + 旧关联编辑需后端 | 准确区分已关联/未知，避免虚假完整性 |
| P1-6 | 最新 App 联合验收 | 两端 + 测试 | 核心流程及断网恢复实机通过 |
| P2 | 语音聊天、提交后反馈、全量事件时间线 | 部分需后端 | 契约先行，不把预留能力当作已上线 |

建议保留当前四栏导航；把资料与盘点、批次操作、流水放到库存详情，把 AI 卡片和概览放到现有助手/首页，把家庭操作放到“我的 → 家庭”。这些是现有页面的功能扩展，无需一口气增加六个主导航。

## 13. 联合验收场景

1. 普通表单新增合规单位/分类的物品，随后 AI 查询成功；“件”、过长名称和非法单位有明确核对提示。
2. 点击库存“消耗”，正式账本新增一个 Consumed，重复原操作只恢复原回执；普通盘点调整不计为消费。
3. 查询多批次 → “第二个” → 补多个字段 → “改成三盒” → 最终确认，同一任务/最新修订，只写一次。
4. 唯一对象查询后追问位置；库存详情绑定指定批次，不误选同名对象；过期/跨家庭拒绝。
5. 开封只改日期/版本，数量不变；刷新、重启和其他成员设备都能看到 opened_at。
6. 部分丢弃准确扣减；全部丢弃按当前余量归零，模式不可通过普通编辑切换；Discards 不计入消费。
7. 盘点数量不符 → 提示先修正 → 刷新库存版本 → 用户再次确认证明。
8. 明确填写 14 天完整记录与足够真实消费事件后生成预测；缺一天、缺货、无盘点或事件不足时显示准确原因。
9. 预测展示条件和统计窗口；null 日期不显示为 0 天，未知风险不显示安全。
10. 偏好只修改一个字段时保留同区块其他已读取值；明确 null 清除正确，未提供区块不变。
11. 同批次两人改资料，一方成功另一方冲突；不自动更新版本后覆盖。
12. 资料写入响应丢失，使用原 operation_id/原正文恢复；不重复创建请求。
13. 库存或历史事件变化后，盘点/覆盖/风险资料显示失效并能重新核对。
14. 从库存添加采购有真实关联；独立新增未知物品保持未知；旧待购改关联在后端契约就绪前不提供虚假入口。
15. 自动建议仍禁止直接提交；用户明确手动数量与 AI 计算来源清晰区分。
16. 退出/移除/转让/解散后，权限、家庭列表、当前页面、活动任务与资料缓存一致更新。
17. 中文/英文与浅色/深色均展示新模块；语言切换不改数量、协议值、日期业务含义或 AI 原文。
18. 确认后刷新失败仍显示已执行；网络未知不会自动重新调用模型或换 operation_id。

以上用于前端开发与排期。本次报告没有宣称这些待办已实现，也没有将原有历史测试结果解释为本轮新手机验收。
