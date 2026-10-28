# MagicVVu P2 Android 接入交接

日期：2026-10-23。**以下是本地已实现契约，尚未部署或完成 Android 联合验收。** 正式后端仍为 households-20261022，Agent 为 p74-6630097c1f56；正式可信引用能力仍 false。

机器契约：[后端 OpenAPI](backend-p2-backend-openapi.json)、[Agent 内部 OpenAPI（仅供服务端）](backend-p2-agent-openapi.json)。验收与限制见 [P2 报告](backend-p2-conversation-report.md)。不要让 Android 调用 Agent 内部接口。

## 1. 主聊天框使用的新接口

`POST /api/v1/agent/conversation-messages`

需要正常登录的 `Authorization: Bearer <登录令牌>`。后端会核实用户、会话、任务归属和家庭成员关系。

首次独立请求：

```json
{
  "household_id": "11111111-1111-4111-8111-111111111111",
  "text": "把牛奶移到冰箱",
  "request_id": "chat-20261023-001"
}
```

已有当前任务时，**每次发送必须一起带 task_id 和当前 revision**；这只是并发选择器，不是可信上下文。后端从数据库重读实际数据。包括换话题、指代查询和“开始新任务”都带当前选择器。例：

```json
{
  "household_id": "11111111-1111-4111-8111-111111111111",
  "text": "就第二个吧",
  "request_id": "chat-20261023-002",
  "task_id": "22222222-2222-4222-8222-222222222222",
  "revision": 1
}
```

请求只允许这五个字段，task_id/revision 可同时省略、不可只给一个。禁止提交 binding、scope、allowed_fields、候选、库存版本、可信时间、selected_batch_id 或引用对象。额外字段返回 422。

本接口不接受手机时区。继续任务使用数据库中的原任务 IANA 时区；独立新任务使用服务端 `MAGICVVU_HOUSEHOLD_TIMEZONE`，默认 Asia/Shanghai。相对日期保留原文，由既有 AI 私有上下文 created_at 锚定。不要用手机时钟预转“昨天”。

## 2. 四种响应

固定外层字段如下。这里展示对已有任务发送“开始新任务”的完整响应：

```json
{
  "protocol_version": "backend-conversation-1",
  "request_id": "chat-20261023-003",
  "original_text": "开始新任务",
  "resolution": {
    "protocol_version": "p7-reply-routing-1",
    "kind": "clear_reference",
    "answers": {},
    "revision": null,
    "error_code": null,
    "clear_reference": true,
    "model_calls": 0
  },
  "task": null,
  "reference": null,
  "inventory_written": false
}
```

clarify/new_task/needs_input 的 task 为完整既有公开 Task 对象；重置响应为 null。选择第二批的 resolution 为 `kind=clarify`、`revision=1`、`answers={"batch_id":"33333333-3333-4333-8333-333333333333"}`，task.revision 则使用处理后的最新值。任务字段如下；result 原样保留既有 AI 结构，不在手机上重建或只保留 reply。

| task 字段 | 类型/规则 |
|---|---|
| task_id / household_id | UUID 字符串 |
| status | processing / needs_clarification / needs_confirmation / answered / unsupported / error |
| revision | 正整数；使用响应最新值发下一条，不能自行 +1 |
| expires_at | ISO 8601 带时区字符串或 null |
| draft_id | UUID 字符串或 null |
| result | 既有公开 AI 结果或 null；澄清仅公开 revision、allowed_fields、expires_at，不含私有 context |
| inventory_written | false；这是 AI 任务结果，不是确认执行回执 |

| resolution.kind | 前端动作 |
|---|---|
| clarify | 后端已调用原结构化澄清并持久化同一任务。**不要再自行调用一次 clarifications**。替换当前 Task，使用其最新 revision。仍缺字段时继续询问；needs_confirmation 时显示现有草稿确认页。 |
| needs_input | 没有模型提取或新任务；保留当前绑定，展示 error_code 和有效候选。Task revision 不因这条路由结果改变。不能默认选第一批。 |
| new_task | 后端已经创建独立任务；替换当前 Task。clear_reference=true 表示旧引用已清除；false 只表示尝试保留已经核实的引用，不代表引用一定存在。 |
| clear_reference | 清除活动绑定与引用；task/reference 为 null。提示输入新任务；不删除历史、不取消草稿或撤销已提交操作。 |

例如“两盒”只在当前 allowed_fields 同时允许 quantity/unit 时转换为 `{"quantity":"2","unit":"盒"}`。只有 quantity 时不会覆盖已有单位；“这个”没有显式已选对象时继续询问。候选序号只在当前修订的数据库候选顺序中解析。

`resolution.revision` 是被补充的原修订；下一次使用 **task.revision**。成功澄清后即使直接生成草稿，也会推进任务 revision，避免快速连发沿用旧修订。

`original_text` 是这条用户回复原文，边界空格也保留。`task.result.original_text` 仍是原任务第一句话；不要把两者混为一条消息。

## 3. 可信引用

部署验证完成且服务端显式启用后，`GET /api/v1/agent/execution-capabilities` 才会给出 `trusted_reference_messages=true`。默认关闭；本地测试启用不代表正式服务已经开启。

新聊天接口会在唯一对象查询成功、或候选被明确选中后保存服务端引用，并在响应 reference 中给出证据：

```json
{
  "protocol_version": "p7-object-reference-1",
  "scope": {
    "user_id": "44444444-4444-4444-8444-444444444444",
    "household_id": "11111111-1111-4111-8111-111111111111"
  },
  "source_task_id": "22222222-2222-4222-8222-222222222222",
  "source_revision": 2,
  "batch_id": "33333333-3333-4333-8333-333333333333",
  "issued_at": "2026-10-23T02:00:00+00:00",
  "expires_at": "2026-10-23T02:15:00+00:00"
}
```

它是展示证据，**不是可由手机签发的令牌或可回传的可信事实**。实际引用保存在数据库；发送“它在哪里”时仅按第 1 节提交原文、当前 task_id/revision。服务端复核来源、TTL 和权限，并通过 Agent 读取当前批次位置/版本。不得从上一条消息拼出名称、数量、位置或版本。

引用最长 15 分钟，可能因原任务到期更早失效。重放、重开页面、连续指代查询不会延长 TTL。同一源任务继续补字段时 source_revision 可推进，issued_at/expires_at 保持原值。

已有结构化批次选择 UI 也可使用正式实现的预留入口：

`POST /api/v1/agent/reference-messages`

```json
{
  "household_id": "11111111-1111-4111-8111-111111111111",
  "text": "它在哪里",
  "request_id": "reference-20261023-001",
  "source_task_id": "22222222-2222-4222-8222-222222222222",
  "source_revision": 2,
  "batch_id": "33333333-3333-4333-8333-333333333333"
}
```

响应也为 `backend-conversation-1`。batch_id 必须是来源结果中的真实对象；提交该字段表示用户明确选择，不表示任意 UUID 均可引用。兼容 DTO 的 household_timezone 可省略；实际使用原任务可信时区，不使用该选择器值计算日期。不要增加 scope、issued_at 或 reference 字段。

该入口不能绕过 reset、家庭/登录会话切换或把旧引用绑定到新话题。多候选未选择时不自动建立引用。原有直接确认库存的 commit 流程继续独立存在，任何引用都不能直接写库存。

## 4. 请求持久化、冲突与恢复

发送前持久化完整请求 JSON。`request_id` 在当前用户＋家庭内去重，跨两个新适配入口也共用去重域。一个键只能对应原始文本、入口及选择器完全相同的一条请求；不要在重试时替换 revision 或正文。

成功响应与 Task/草稿在同一事务内保存。HTTP 响应丢失时重发**原键＋原完整请求体**即可恢复原响应，不重复澄清或创建任务。重放返回历史响应快照，不能把它当作当前库存重新查询；需要当前事实时使用新 request_id 发新查询。GET 原 Task 后可能获得更高 revision。

| HTTP / code | 客户端处理 |
|---|---|
| 401 / CONVERSATION_SESSION_EXPIRED 或原登录错误 | 清本机当前上下文和引用，重新登录。不要用旧登录会话的任务选择器接到新会话。 |
| 404 / DRAFT_NOT_FOUND、REFERENCE_NOT_FOUND、原任务错误 | 可能是权限或对象不可访问，不证明操作从未执行。引用对象消失时要求重查。部分既有错误 detail 仍为字符串。 |
| 409 / TASK_SELECTOR_REQUIRED | 已有活动任务，携带其 task_id/revision。不要默默用最后一条聊天推断。 |
| 409 / TASK_REVISION_CONFLICT、TASK_SNAPSHOT_CHANGED、CANDIDATES_CHANGED | GET 最新任务并让用户重新核对/选择；新输入使用新 request_id 和新选择器。旧序号不能复用到变化后的候选列表。 |
| 409 / CONVERSATION_PROCESSING、TASK_PROCESSING、CONCURRENT_DUPLICATE_REQUEST | 保留原请求，稍后重试相同键/体或查询原 Task；不要并发发送第二个补充。 |
| 409 / REQUEST_ID_CONFLICT | 相同键被用于不同请求，客户端应停止重试并修正键管理。 |
| 409 / CONVERSATION_BINDING_CHANGED、CONVERSATION_SUPERSEDED | 会话、家庭或活动任务已切换；重新读取当前页面状态，不把旧引用接到新任务。 |
| 409 / REFERENCE_EXPIRED、REFERENCE_TERMINAL、REFERENCE_SOURCE_CHANGED | 明确提示重新查询或选择，不延长 TTL。 |
| 503 / REPLY_ADAPTER_UNAVAILABLE | Agent 内部续接适配尚未发布或暂不可用；保留原请求，使用旧结构化表单。不能偷偷发普通消息触发模型重试。 |
| 503 / TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE | 引用开关关闭，不能显示可用。改为明确名称的新查询或等待正式开放。 |
| 409 / AI_OUTCOME_UNKNOWN | 新任务可能已触发模型；不得自动换键/再次提取。detail 带原 task_id 和查询路径，先 GET 原 Task。仍为 processing 表示理解结果未知，不表示业务已写入。 |
| 422 | 请求结构、选择器或候选不合法；纠正后作为新的明确输入，不能注入内部上下文。 |

澄清计算是零模型路径，网络超时可用同键/体重试；首次新任务理解的响应丢失则保守封存，避免重复计费。当前 Agent 没有按 request_id 持久化付费提取结果的恢复 API，未知状态无法自动变成成功；需要人工核对后决定是否明确发起新任务。

保持 P1 确认恢复规则：持久化稳定 operation_id；确认超时查询 operation 或 draft/execution；刷新失败不重复执行。P2 request_id 与正式写入 operation_id 是两类不同的键。

## 5. 新旧客户端与发布配合

- 旧 `/agent/messages` 四字段、`/agent/clarifications/{task_id}` 九字段结构化 answers、草稿确认/取消/回执接口保持可用。旧客户端不会自动获得新主聊天框续接功能。
- 新客户端在主聊天会话内统一使用 conversation-messages，避免与旧普通消息入口交错维护活动游标；历史查看仍可 GET Task。没有活动绑定时可显式接入一条已鉴权历史任务，服务端仍检查修订和 TTL。
- 同一登录用户只保留一个服务端活动游标。不同设备/窗口的任务切换会产生明确绑定冲突，不自动合并聊天历史。切换家庭、注销、换账号时清除本机引用和选择器；换家庭第一条请求不带旧 task_id/revision。
- 本轮没有修改 Android。真实 APK 的关闭窗口/进程重建、家庭切换、并发发送、弱网及确认后刷新仍需队友联合验收。
- 发布需同时准备后端 0008 兼容迁移和 Agent 的 `/agent/reply-resolution` 适配器；旧 Agent 缺路由时后端明确 503。Dockerfile 已复制 conversation 目录，新文件随现有构建进入镜像，无新运行依赖。
- OPEN/DISCARD 仍不可正式确认；日期续接本地通过不表示这两类执行已开放。自动补货确认仍关闭。
