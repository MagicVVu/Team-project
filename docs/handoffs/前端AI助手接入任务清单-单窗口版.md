# 前端 AI 助手接入任务清单（单窗口版）

日期：2026-10-29；2026-10-30状态补充。面向前端负责人，综合 P8.3～P8.5，并单列最新自主循环增量。

**当前源码进度：** 队友最新提交已包含 `AgentClient.conversationTurn`、会话能力选择/恢复和聊天90秒超时，下文原接入任务作为核对清单，不再代表这些代码尚未开发。本轮未修改前端。后续主要核对实际安装包、新协议停止提示、逐件库存预览和完整恢复/执行联验；详见[当前适配交接](../versions/V1-P8.6/前后端交接说明.md)及其中的[后端 OpenAPI JSON](../versions/V1-P8.6/contracts/backend-openapi.json)。AI自主循环仍只在本地，不能据此认定服务器已启用。

**按下面任务逐项完成，继续使用现有 AI 聊天窗口。每个用户在每个家庭只有一段当前会话，不做会话侧边栏、多会话列表或独立的新对话页面。**

本文件是接入任务清单，没有修改前端代码，也不表示服务器已启用全部契约。联调前请后端负责人确认目标环境支持的协议；下文 JSON 是当前本地交付契约。

## 先明确三个概念

| 概念 | 对前端意味着什么 |
|---|---|
| 当前会话 | 同一个聊天窗口里的连续交流。`conversation_id` 和会话修订保存在程序中，不必展示给用户。 |
| 当前任务 | 会话中正在澄清、待确认或处理的库存事项。临时聊天、追问状态不应让它消失。 |
| 开始新任务 | 在同一个窗口里换一件事。沿用现有入口，不清空聊天记录，也不自动取消旧草稿。 |

关闭窗口、重启应用、重新登录后恢复当前会话。切换家庭后读取对应家庭的会话，不能串用对象和草稿。历史展示范围是最近 30 天，可在当前窗口向上加载。

## 任务 1：把新版公开接口加入客户端

**核对事项：** 当前源码已有新版 `conversation-turns` 系列接口；验证能力选择及实际安装包是否走该分支，保留旧请求恢复兼容。

**主要改哪里：** [AgentClient.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AgentClient.kt)。

**需要做：**

1. 保留既有确认、取消、回执和旧请求恢复接口。
2. 加入下表接口，并通过能力声明及后端联调结果选择新协议。
3. 新版普通聊天、自然补充、对象追问和草稿改口统一走新消息接口。一次用户交互只发一条处理请求。

| 接口 | 使用时机 |
|---|---|
| `GET /api/v1/agent/execution-capabilities` | 检查部署能力和可执行动作；不根据版本名称猜测支持情况。 |
| `GET /api/v1/agent/conversation?household_id=...&limit=20` | 打开窗口时获取当前会话、消息和最新活动任务；继续分页时传 `cursor`。 |
| `POST /api/v1/agent/conversation/reset` | 服务器返回 `requires_reset=true` 等初始化要求时，按契约建立当前会话。不要每次打开窗口都调用。 |
| `POST /api/v1/agent/conversation-turns` | 发送新版聊天消息。 |
| `GET /api/v1/agent/conversation-turns/{request_id}?household_id=...` | 查询原消息的处理结果。 |

**怎样算完成：** 能在约定环境读取当前会话并发送新版消息；旧任务仍可查询及确认。不增加多会话界面，也不要求新增“新对话”按钮。

**查看契约：** [后端 OpenAPI JSON](../versions/V1-P8.6/contracts/backend-openapi.json)、[消息请求 Schema](../versions/V1-P8.6/contracts/public-message.schema.json)。

## 任务 2：保存会话信息和完整响应

**要解决什么：** 不能只保存回复文字或 `task.result`；寒暄、解释等正常回答可能没有本轮任务。

**主要改哪里：** [AssistantModels.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantModels.kt)、[AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt)。

**需要做：**

1. 按用户、家庭保存服务器返回的 `conversation_id`、最新会话修订和完整消息响应。登录令牌的哈希不能替代业务会话 ID。
2. 分别保存本轮 `task` 和最新 `active_task`。`task=null` 是合法结果；临时问答不能因此清掉待确认任务。
3. 区分会话修订、任务修订、草稿修订和库存预期版本，分别按对应接口传递。恢复返回的当前修订与历史响应修订也要区分，不能把旧修订覆盖为最新值。
4. 保存原 `request_id` 和原请求体，用于恢复；新发消息才生成新 ID。

请求示例（UUID 为格式示例，实际使用服务器返回值）：

```json
{
  "household_id": "11111111-1111-4111-8111-111111111111",
  "request_id": "chat-20261029-0001",
  "conversation_id": "22222222-2222-4222-8222-222222222222",
  "conversation_revision": 7,
  "text": "它现在在哪里？"
}
```

指定续接某个任务时，按契约同时提供 `task_id` 和任务 `revision`。手机不上传可信历史、库存事实、对象版本或执行状态，由后端构建这些信息。

**怎样算完成：** “你好”返回 `task=null` 时正常显示；已有待确认草稿仍在。重启后能读取已保存的请求标识，多个修订号互不混用。

**查看契约：** [消息请求 Schema](../versions/V1-P8.6/contracts/public-message.schema.json)、[公开响应 Schema](../versions/V1-P8.6/contracts/public-response.schema.json)。

## 任务 3：打开窗口先恢复，超时后查原请求

**要解决什么：** 当前本地恢复不能代替云端当前会话；换设备或重新登录后仍要找回经过权限校验的会话和任务。

**主要改哪里：** [AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt)、[CloudAssistant.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt)。

**需要做：**

1. 打开窗口先 GET 当前会话，展示消息、更新会话修订，并恢复 `active_task`。保留本地待发送记录，与云端结果按 `request_id` 合并去重。
2. 有 `next_cursor` 时，在同一个窗口加载更早消息，不创建历史会话列表。
3. 重新登录后用新的登录凭证读取；切换家庭时清除当前活动绑定，读取新家庭数据。处理迟到响应时核对用户和家庭，避免覆盖新页面。
4. 消息超时或响应丢失后，GET 原 `request_id`，不要换 ID 自动重新发送。
5. 会话修订冲突时先刷新，保留用户输入；不要把旧请求的修订悄悄改掉再自动提交。

| 恢复 `phase` | 前端行为 |
|---|---|
| `completed` | 显示原响应，同时用恢复返回的最新活动任务更新当前状态。 |
| `processing` | 显示处理中，保留原请求，按后端约定继续查询。 |
| `prepared` / `result_unknown` | 展示恢复提示或结果待核实；按 `recovery_hint` 处理，不自动开始新一轮推理。 |

历史消息保留当时的状态；当前任务是否执行，以最新任务和执行回执为准。初始化使用 reset 不代表要做多会话产品功能。

**怎样算完成：** 在澄清或待确认时关闭窗口、重启或重新登录，能回到原任务；超时恢复不产生重复消息、重复模型请求或重复执行。

**查看契约：** [历史分页 Schema](../versions/V1-P8.6/contracts/conversation-page.schema.json)、[原请求恢复 Schema](../versions/V1-P8.6/contracts/recovery.schema.json)。

## 任务 4：正确展示自然回复，并保留活动任务

**要解决什么：** 新版不保证每条回复都创建任务；自然文字和结构化任务需要一起展示。

**主要改哪里：** [CloudAssistant.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt)、[AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt)。

**需要做：**

1. 聊天气泡使用公开响应顶层 `reply`；候选、草稿和计算结果继续由结构化字段渲染。
2. 支持问候、解释、查询、需要补充、草稿修改等结果；不要把“没有 task”视为接口失败。
3. 用户问“为什么还没移动”“这个建议依据是什么”时，显示回答，同时保留原待确认任务。
4. `truncated=true` 时，可提示“本次仅使用了部分历史”；不要把它显示成业务执行失败。
5. 未知结果类型保留自然回复并给出可理解提示，不让整条消息丢失。

**怎样算完成：** 待确认草稿后问“为什么还没执行”，能看到解释，原确认表单仍可继续操作。

**查看契约：** [公开响应 Schema](../versions/V1-P8.6/contracts/public-response.schema.json)。

## 任务 5：让批次选择、补字段和改口接上同一任务

**要解决什么：** “第二批”“昨天”“还是两盒”等应续接原任务，不能变成互不关联的新请求。

**主要改哪里：** [AssistantStore.kt](../../frontend/app/src/main/java/com/example/teamapp/data/AssistantStore.kt)、现有候选和草稿表单。

**需要做：**

1. 使用服务器提供的候选顺序和真实批次标识，不默认选第一项。“第二批”只能对应该任务修订的第二项。
2. 新版自然补充走 `conversation-turns`，携带当前会话及需要续接的任务选择器。保留旧结构化澄清时，一次操作只选择一条提交路径，不能两边都调用。
3. 收到草稿修改结果后，更新任务、草稿及其修订，重新展示变更摘要。旧修订上的本地编辑不得覆盖新草稿。
4. 前端表单只开放契约允许的字段；改变动作或目标交由服务重新生成和核对，不能直接改 ID 或预期版本。
5. “先别执行，我只是核对”不等于取消，更不等于确认。不要在新版聊天发送前用旧本地关键词规则抢先执行取消或提交。

开封、整批移动不要求数量；丢弃区分定量和全部，全部数量取服务器核实结果。数量、单位和精度不由前端自行猜算。

**怎样算完成：** “移动牛奶 → 选择第二批 → 生成草稿”连贯完成；支持适用动作的“还是两盒”修订；“先别执行”后仍是待确认，库存不变。

## 任务 6：补齐统计、风险和补货结果的展示入口

**要解决什么：** 现有卡片可以复用，但新版核实计算也可能放在 `evidence` 中，仅渲染 `task.result` 会漏结果。

**主要改哪里：** [AgentResultCards.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/AgentResultCards.kt)、[CloudAssistant.kt](../../frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt)。

**需要做：**

1. 同时承接 `task.result` 和 `evidence` 内 `kind=verified_calculation` 的 `result`，使用对应结果类型的卡片，并避免同一结果重复展示或重复求和。
2. 展示统计范围、计算依据、更新时间、缺失数据及不可用原因。未知数量、耗尽日期和建议量不显示为 0，不把未读到待购清单当作没有待购。
3. 商品和批次按各自稳定 ID 区分，不根据同名商品自行合并。消费记录不完整时显示已记录部分，不声称覆盖全部实际消费。
4. 区分“按最低库存补货”和“本次 AI 建议”；按钮使用对应依据，不能展示 AI 建议却执行另一套数量。
5. 复用已有来源、记录及规划资料页面。相关业务接口尚未提供或没有执行能力时，显示具体缺口及已有可用入口，不补造路由或自动采购。

**怎样算完成：** 没有本轮 `task`、但有核实计算证据时仍显示卡片；数据不足时显示原因，不出现虚假的零消费或耗尽日期。

**查看契约：** [AgentResult Schema](../versions/V1-P8.3/contracts/agent-result.schema.json)、[商品规划 Schema](../versions/V1-P8.3/contracts/product-planning.schema.json)、[规划依据 Schema](../versions/V1-P8.3/contracts/planning-basis.schema.json)。

## 任务 7：保留正式确认链路，准确展示执行状态

**要解决什么：** 聊天处理成功、草稿生成成功和库存执行成功是三个不同结果。现有确认和回执能力继续复用。

**主要改哪里：** 现有确认、取消、执行查询及回执处理代码。

**需要做：**

1. 按后端执行能力决定按钮是否可用；没有正式能力的动作保留草稿和真实可用的手动入口。
2. 用户明确点击确认后，才调用现有正式提交接口。沿用版本校验、稳定操作 ID 和原请求体；首次提交前保存操作标识。
3. 区分需要补充、待确认、提交中、已执行、已取消、已过期、失败和结果待核实。
4. 只有正式成功回执能显示“已执行”。聊天 `completed`、普通成功响应、AI 回复或待确认草稿都不能代替回执。
5. 提交响应丢失时查询原操作状态，不换操作 ID 自动再提交；已执行但库存刷新失败时，保留执行成功，单独提示刷新失败。

聊天响应的 `inventory_written=false` 表示 AI 本身没有写库存，不代表此前正式确认的操作未执行。

**怎样算完成：** 无回执不会显示已执行；提交超时不会重复扣库存；成功后刷新失败不会把操作误判为失败。

**查看契约：** [后端 OpenAPI JSON](../versions/V1-P8.6/contracts/backend-openapi.json)中的既有草稿、执行及操作查询接口。

## 任务 8：单独承接最新自主循环增量

**适用范围：** 这是 P8.3～P8.5 基础接入之外的最新增量。后端启用 `inventory-autonomous-1` 时一起承接；不表示该协议已经在线上启用。

**主要改哪里：** [CloudApi.kt](../../frontend/app/src/main/java/com/example/teamapp/data/CloudApi.kt)、响应解析和消息状态展示。

**需要做：**

1. 聊天读取超时调整为 **90 秒**。原 P8.4/P8.5 文档中的 30 秒只适用于原流程；最新自主流程采用 AI 60 秒、后端 75 秒、前端 90 秒。其他接口无需统一拉长。
2. 等待期间显示处理中。超时仍按任务 3 查询原请求，不换 ID 自动重发。
3. 公开响应顶层协议仍为 `conversation-memory-1`；内部流程通过 `dialogue.protocol_version` 区分。新自主协议计数是非负整数，不再套用旧协议“两次以内”校验。
4. 支持下表状态。保留已核实的文字和卡片，不因部分结果丢弃整个回答。

| `dialogue.status` | 展示方式 |
|---|---|
| `completed` | 本轮回答完成；业务执行另看正式回执。 |
| `needs_input` | 需要用户补充，保留当前任务。 |
| `needs_confirmation` | 展示待确认草稿。 |
| `stopped` | 展示已知结果和 `stop_reason` 对应的说明，例如资料不足或处理超时；不要自动重新运行。 |

自主循环、工具调用和记忆检索均在 AI/后端内部，前端只提交一次消息、接收最终结果及恢复状态。不需要实现模型循环，也不直连 AI 内部接口。

**怎样算完成：** 较长请求不会在原 20 秒配置处提前断开；部分结果可见；模型调用超过两次不会解析失败；停止后不会自动创建新请求。

**查看契约：** [最新公开响应 Schema](../versions/V1-P8.6/contracts/public-response.schema.json)、[自主循环交接说明](../versions/V1-P8.6/前后端交接说明.md)。

## 任务 9：按完整场景联合验收

建议先完成任务 1～3，再完成任务 4～7，最后结合后端启用情况完成任务 8，并验证以下场景。

| 场景 | 应看到什么 |
|---|---|
| 打开聊天窗口 | 恢复当前家庭历史和任务，没有会话侧边栏。 |
| 关闭、重启、重新登录 | 权限校验后恢复原会话；不因登录令牌变化丢失云端记录。 |
| 切换家庭 | 显示对应家庭会话，原家庭对象和草稿不混入。 |
| 发送“你好” | 正常展示回复，`task=null` 不报错。 |
| 查询数量和位置，再说“第二批在哪里” | 承接正确候选，显示服务器核实结果。 |
| “喝了一半”后说“还是两盒” | 展示并修订准确草稿；前端不自行计算比例或覆盖版本。 |
| 待确认后问“为什么还没执行” | 显示解释，原待确认任务仍可继续。 |
| “先别执行，我只是核对” | 没有提交，也没有误取消。 |
| 用户正式确认，随后刷新失败 | 展示正式成功回执，刷新失败单独提示。 |
| 消息或提交响应丢失 | 按原请求或原操作查询，不重复发起业务操作。 |
| 数据不足或自主循环停止 | 显示已知事实和具体缺口，不伪造数值、不自动重跑。 |
| 服务返回修订冲突或权限失效 | 保留输入、刷新或提示重新授权，不提交旧草稿。 |

分别记录前端完成、后端契约可用及 App 联合验收结果；本地接口测试通过不能代替这些场景。

## 契约入口和协作边界

前端优先查看 [后端 OpenAPI JSON](../versions/V1-P8.6/contracts/backend-openapi.json)、[请求 Schema](../versions/V1-P8.6/contracts/public-message.schema.json)、[响应 Schema](../versions/V1-P8.6/contracts/public-response.schema.json)、[历史 Schema](../versions/V1-P8.6/contracts/conversation-page.schema.json)和[恢复 Schema](../versions/V1-P8.6/contracts/recovery.schema.json)。使用同一份契约交付，可通过[契约清单](../versions/V1-P8.6/contracts/manifest.json)核对。

[AI OpenAPI JSON](../versions/V1-P8.6/contracts/ai-openapi.json)是后端调用 AI 的内部契约，供理解流程使用；手机不直接调用，也不保存内部令牌。领域细节参考 [P8.3～P8.5 统一对接方案](V1-P8.3-P8.5-前后端统一对接方案.md)。其中涉及“新会话”的服务端能力不要求增加多会话界面，本次前端按单窗口方案落地。

前端负责接口调用、隐藏标识保存、消息和卡片展示、恢复、确认交互。AI 负责理解、上下文处理、读取核对和草稿生成；后端负责权限、会话和任务持久化、修订、正式执行、幂等与回执。接口未启用、资料缺失或业务能力未完成时，由对应负责人补齐，前端展示真实可用状态。
