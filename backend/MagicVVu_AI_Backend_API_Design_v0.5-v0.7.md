# MagicVVu AI × 后端接口设计规范（v0.5–v0.7 草案）

> 编写日期：2026-10-14  
> 对接基线：线上 MagicVVu FastAPI v0.4.0 / Alembic `20261014_0003 (head)`；AI 队友交付的 `agent(1).zip` 中 `agent/p1/`、`agent/p0/`；《V1-P1 AI开发工作记录》和《V1-P1 后端协同开发与接入说明》。  
> 状态：**设计方案，尚未实装到 v0.4，也未完成真实 PostgreSQL + AI + Android 端到端验收。**  
> 原则：尽量遵循既有 P1 契约；本规范中额外提出的 App 网关路由、数据表和错误码应经团队审阅后冻结。

## 0. 现有能力与职责界线

- **AI P1 已实现（以源码为准）**：`GET /health`、`POST /agent/message`、`POST /agent/clarification`。支持 `ADD`、`CONSUME`、`QUERY_INVENTORY`、`QUERY_LOCATION`、`PLAN_ADD`、`OPEN`、`MOVE`、`DISCARD`，返回 `answered`、`needs_clarification`、`needs_confirmation`、`unsupported`、`error`。AI 不保存任务、不直接写库存、不实现撤销。
- **MagicVVu v0.4 已部署并检查过**：手机号/密码认证与家庭相关业务 API；PostgreSQL 连接健康；数据库迁移至 0003。v0.4 尚未实现本文件提出的 AI 网关与 AI 库存内读接口。**精确表字段须在实施迁移前核对实际 v0.4 SQLAlchemy 模型和数据库列**，不得按示意直接覆盖线上表。
- **App 负责**：提交输入、选择家庭、展示事实/候选/草稿、提供明确确认动作；不掌握 AI 服务 token，不自行生成确认后状态，不提交完整澄清上下文。
- **业务后端负责**：用户会话鉴权、家庭成员验证、库存读写、任务上下文存储、草稿审阅、事务、幂等、审计事件、撤销。
- **AI 负责**：自然语言解析和澄清、根据只读库存事实生成命令与拟议 `preview`；其草稿只是建议，后端必须重新校验。

调用路径：`Android → FastAPI (用户 Bearer Token) → AI P1 (AI_SERVICE_TOKEN) → FastAPI 只读工具 (BACKEND_TOOL_TOKEN) → PostgreSQL`。AI 响应返回业务后端，后端保存状态后向 App 返回；确认写入单独走 FastAPI 事务。

## 1. 两套认证和总体约定

| 连接 | 认证方式 | 授权依据 | 网络暴露 |
|---|---|---|---|
| Android → `/api/v1/*` | v0.4 登录得到的用户 Bearer Token | 用户身份和家庭成员关系 | 后续经 HTTPS 网关提供；当前 8000 仅本机 |
| FastAPI → AI `/agent/*` | `Authorization: Bearer <AI_SERVICE_TOKEN>`，附后端生成的 `X-User-Id`、`X-Household-Id` | 后端先校验用户会话与家庭成员关系 | Docker 内网，不向公网开放 8767 |
| AI → FastAPI `/internal/v1/*` | `Authorization: Bearer <BACKEND_TOOL_TOKEN>`，附 `X-User-Id`、`X-Household-Id` | 校验独立只读令牌 **和** 用户有效成员关系；按家庭过滤查询 | Docker 内网；不向公网开放专用内部端口 |

两种服务 token 必须不同，使用高熵随机值，通过运行时密钥配置注入，不提交 Git、不出现在 App/浏览器及日志中。不能单独凭 `X-Household-Id` 或 `X-User-Id` 信任来路；要验证服务令牌及用户/家庭是否仍有效。内部读取接口只允许 GET，不能用工具令牌调入库接口。

**通用约定（新增后端 API）**：
- JSON UTF-8；日期 `YYYY-MM-DD`，时间戳含时区；数量以**十进制字符串**表示，如 `"1.500000"`，严禁 JS 浮点数参与库存金额/数量计算；数量非负，变更数量须大于 0、最多 6 位小数且不超过 10 亿。
- 单位与 P1 `p0.domain.normalize_unit` 对齐：`ml`、`L`、`g`、`kg`、`盒`、`瓶`、`包`、`袋`、`个`、`卷`、`片`。只在 ml↔L、g↔kg 之间自动换算；不得臆测一盒或一瓶的容量。库存 API 输出**规范化单位**。
- ID 对 AI `Batch` 表达为字符串；若数据库用 UUID/整数，在序列化边界转换为字符串，不猜测客户端格式。
- 所有 `/api/v1` 请求的家庭标识必须由已登录用户选择并经服务端成员鉴权；不允许从客户端请求头伪造用户 ID。AI 返回的 `scope`、`preview` 和数量不可直接认作可信写入参数。
- 本文件示例 `household_id`、`batch_id` 为占位，客户端须使用实际返回的 ID。

## 2. 批次契约（必须首先对齐）

AI `agent/p1/schemas.py::Batch` 实际字段：

```json
{
  "id": "batch_001",
  "household_id": "household_001",
  "name": "牛奶",
  "quantity": "3",
  "unit": "盒",
  "location": "冰箱",
  "purchased_at": "2026-10-12",
  "label_expiry": "2026-10-20",
  "opened_at": null,
  "status": "ACTIVE",
  "version": 7
}
```

- 必填：`id`、`household_id`、`name`、`quantity`、`unit`、`status`、`version`。`quantity` 可以为 `0`；`version >= 1`。
- 可空：`location`、`purchased_at`、`label_expiry`、`opened_at`。未知必须为 JSON `null`，绝不填虚构默认日期、库位。
- 状态：`ACTIVE`（有效库存）、`FINISHED`（消耗完）、`DISCARDED`（丢弃完）、`REVERSED`（撤销/反转后的终态；具体用途待与当前库存模型对齐）。不可将 `FINISHED` 和 `DISCARDED` 混用。
- 任一真实状态变化，包括数量/位置/开封/结束状态，`version` 每成功提交一次加 1；读取不增版本。
- 现有 v0.3/0.4 “每家庭一张共享购物清单”和 `source_shopping_list_item_id` 防重复入库语义必须保留；同一物品多批次可以共存，切勿将商品名设为家庭内唯一键。
- 落库可扩展现有 `inventory_items` 作为批次主体（如果当前模型确实是每行一批次），或建立批次表并迁移映射；实施前先检查真实 schema、数据约束和外键。

## 3. 后端给 AI 的库存只读接口（v0.5，必须兼容 P1 原样代码）

### 3.1 `GET /internal/v1/inventory/search?name=牛奶`

**请求头**：`Authorization: Bearer <BACKEND_TOOL_TOKEN>`；`X-User-Id`；`X-Household-Id`。  
**参数**：可选 `name`，省略时按家庭返回全部库存批次；包含同名多个批次、零库存历史批次和真实终态；不得静默只返回第一个匹配。数据量高于 P1 上限（1000）时应协调分页/能力升级或明确报错，不能悄悄截断导致模型认定库存不完整。

响应 HTTP 200：

```json
{
  "data": {
    "batches": [
      {"id":"batch_001","household_id":"household_001","name":"牛奶","quantity":"3","unit":"盒","location":"冰箱","purchased_at":"2026-10-12","label_expiry":"2026-10-20","opened_at":null,"status":"ACTIVE","version":7}
    ]
  }
}
```

不存在匹配批次时返回 `{"data":{"batches":[]}}`，非 404。必须先根据经过验证的家庭作用域过滤，再搜索名称。

### 3.2 `GET /internal/v1/inventory/batches/{id}`

请求头同上；成功 HTTP 200：

```json
{"data":{"batch":{"id":"batch_001","household_id":"household_001","name":"牛奶","quantity":"3","unit":"盒","location":"冰箱","purchased_at":"2026-10-12","label_expiry":"2026-10-20","opened_at":null,"status":"ACTIVE","version":7}}}
```

不存在，或批次不属于经过验证的家庭，统一返回 404，避免通过状态码探测其他家庭数据。成功返回的 ID 必须与请求 ID 完全一致。AI 会再次验证家庭归属、重复批次和 ID 一致性。

### 3.3 内部接口错误

| HTTP | 含义 | 建议错误码 |
|---|---|---|
| 401 | 只读工具令牌缺失或无效 | `UNAUTHENTICATED` |
| 403 | 认证用户不属于目标家庭 | `HOUSEHOLD_FORBIDDEN` |
| 404 | 指定批次不可访问（不存在或跨家庭） | `BATCH_NOT_FOUND` |
| 503 | 库存依赖暂时故障或数据不完整 | `TOOL_UNAVAILABLE` |

建议使用 `{"success":false,"data":null,"error":{"code":"...","message":"..."},"trace_id":"..."}`；**P1 的成功解析依赖 `response.json()["data"]`，不能擅自改名或加一个内层 envelope。**

## 4. FastAPI → AI P1 现有接口（不改队友源代码）

### 4.1 `POST http://ai:8767/agent/message`

**服务认证头**：`Authorization: Bearer <AI_SERVICE_TOKEN>`、`X-User-Id`、`X-Household-Id`。  
请求体遵从现有 `p1.schemas.Message`：

```json
{"text":"牛奶昨天开封了","request_id":"req_001","household_timezone":"Asia/Shanghai"}
```

`text` 长度 1–1000，`request_id` 长度 1–100，时区必须为有效 IANA 时区。`household_timezone` 由业务后端确定/校验，不凭模型或用户随意伪造。

### 4.2 `POST http://ai:8767/agent/clarification`

服务认证头同上。请求体**只由后端装配**，上下文来自数据库当前版本：

```json
{
  "context": {"...":"从后端 ai_tasks.context_json 读取的完整 P1 ClarificationContext"},
  "revision": 1,
  "answers": {"batch_id":"batch_001"}
}
```

这里的 `context` 为说明性占位，**不是可直接发送的请求**；实际内容必须包含 P1 的完整 `id`、`revision`、`scope`、`original_text`、`request_id`、`trace_id`、`household_timezone`、`created_at`、`expires_at`、`parsed`、`candidates`、`selected_batch_id`、`allowed_fields`。不能由 App 上传完整 context；不能允许 App 更改 intent、家庭 ID、期望库存版本或 `discard_mode`。用户补字段**不调用第二次模型**。

### 4.3 AI 返回值处理

P1 成功响应是裸 `AgentResult`，**没有业务网关外层 envelope**。核心字段：`status`、`intent`、`reply`、`trace_id`、`original_text`，可附 `draft`、`preview`、`clarification`、`candidates`、`facts`、`missing_fields`、`error_code`、`retryable`、`manual_entry`、`trace`。

| `AgentResult.status` | 网关动作 | 是否写入库存 |
|---|---|---|
| `answered` | 返回文本与真实 `facts`，适用于查询、重复开封、原地移动等 | 否 |
| `needs_clarification` | 保存完整 context、候选及 revision；返回业务 `task_id` | 否 |
| `needs_confirmation` | 保存结构化 `draft`、`preview`、trace_id、draft revision；返回 `draft_id` | 否 |
| `unsupported` | 返回能力边界提示，不创建可执行草稿 | 否 |
| `error` | 返回错误码和可恢复信息；可能需要存储更新后的 context | 否 |

**注意：AI 的 HTTP 200 可能包含 `status="error"`；必须先判断 `status`，不能以 HTTP 200 等价于成功处理。** HTTP 401 表示服务认证失败，422 表示请求结构校验失败。AI 完整处理有 10 秒截止时间，网关读超时建议约 12–15 秒并严格限制总耗时；不要自动重发可能计费的 LLM 调用。

## 5. App → FastAPI 业务接口（拟新增）

以下新接口统一要求 `Authorization: Bearer <USER_ACCESS_TOKEN>`。推荐外层响应：

```json
{"success":true,"data":{},"error":null,"trace_id":"trace_..."}
```

错误统一：`{"success":false,"data":null,"error":{"code":"VERSION_CONFLICT","message":"库存已变化，请重新核对。"},"trace_id":"trace_..."}`。`error.code` 为稳定机器码、`message` 为可显示中文；不得把 AI 供应商密钥或内部堆栈返回 App。

### 5.1 `POST /api/v1/agent/messages` — 发起 AI 任务（v0.6）

```json
{
  "household_id":"household_001",
  "text":"牛奶昨天开封了",
  "request_id":"android_req_uuid_001"
}
```

- 后端凭用户 Token 获取 `user_id` 并校验家庭成员；通过家庭配置取得 `household_timezone`；禁止 App 自填 `X-User-Id`。
- 按 `(user_id, household_id, request_id)` 建唯一业务请求记录；重复相同请求优先返回已持久化结果，避免双重付费。若第一次仍在处理中，应返回可查询的任务状态，不能同时并发发送同一 request_id 到 AI。相同 ID 不同正文应 `409`。
- 成功返回沿用 P1 `status`，并额外添加网关 ID、修订号及草稿 ID（按状态出现）：

```json
{
  "success":true,
  "data":{
    "task_id":"task_001",
    "status":"needs_confirmation",
    "intent":"OPEN",
    "reply":"草稿已生成，尚未写入。请核对后确认。",
    "draft_id":"draft_001",
    "draft_revision":1,
    "draft":{"action":"OPEN","name":"牛奶","batch_id":"batch_001","expected_version":7,"opened_at":"2026-10-13"},
    "preview":{"prospective":true,"batch_id":"batch_001","event_type":"Opened","quantity_delta":"0","inventory_changes":true},
    "trace_id":"trace_001"
  },
  "error":null,
  "trace_id":"trace_001"
}
```

完整 P1 `preview` 和候选字段应**原样保留**而非仅使用以上精简示例；App 可以显示 `before`、`after`、`facts`、`candidates`。明确标记：`preview.prospective=true` **不等于已经落库**。

### 5.2 `GET /api/v1/agent/tasks/{task_id}` — 读取任务状态（v0.6）

- 校验任务所属用户、家庭及访问权限（任务原文、草稿私有数据不得跨用户读取；家庭共享任务是否开放需产品层明确授权）。
- 返回当前 `status`、`reply`、`revision`、`expires_at`、允许填写的字段、候选及关联 `draft_id`；**不返回原始服务令牌，也不允许客户端重新提交服务器存储的完整 context**。
- 用于超时、断线及 App 重启后恢复。

### 5.3 `POST /api/v1/agent/clarifications/{task_id}` — 澄清续接（v0.6）

```json
{"revision":1,"answers":{"batch_id":"batch_001"}}
```

- `revision` 必须等于数据库中的最新澄清版本；身份/家庭由任务记录派生且再次验证。
- `answers` 仅允许数据库保存的 `allowed_fields` 中出现的字段，批次选择必须属于候选集合；不能传完整 `context`、`intent`、`discard_mode` 或任意新的批次版本。
- 后端锁定或条件更新任务 revision，调用 AI 后将新 context/草稿/错误上下文持久化，再返回更新后的 `status`；同版本并发续接最多成功一次。
- task 默认 15 分钟有效期；补充字段不延长有效期；相对日期沿用原始参考时间。过期或冲突返回 `409`（建议 `CLARIFICATION_EXPIRED`、`CLARIFICATION_CONFLICT`）。库存版本变化导致 `VERSION_CONFLICT` 时返回**新候选并让用户重新选择**，不自动确认。

### 5.4 `GET /api/v1/drafts/{draft_id}`、`PATCH /api/v1/drafts/{draft_id}` — 草稿（v0.6）

`GET` 返回草稿当前 `status`、`revision`、`action`、`command`、`preview`、关联 `task_id`、有效期与候选事实。

`PATCH` 示例：

```json
{"revision":1,"changes":{"to_location":"厨房"}}
```

- 仅允许按动作字段白名单修改，不能修改 `action`、`batch_id`、`household_id`、`expected_version`、`actor`。
- 后端重新校验 P1 同等数量/单位/日期规则，刷新预览并使 draft revision 加 1；需要重新解析自然语言时应发起新任务，而不是暗中修改原动作。
- 建议状态 `DRAFT`、`CONFIRMED`、`CANCELLED`、`EXPIRED`；状态码以最终后端实现为准。过期/重复修订用 `409`。

### 5.5 `POST /api/v1/drafts/{draft_id}/confirm` — 确认写库（v0.7）

**必须带** `Idempotency-Key: <client-generated-unique-key>`；请求：

```json
{"revision":2}
```

示例成功结果（说明性）：

```json
{
  "success":true,
  "data":{
    "draft_id":"draft_001",
    "draft_status":"CONFIRMED",
    "event_id":"evt_001",
    "batch_id":"batch_001",
    "batch_version":8,
    "inventory_committed":true
  },
  "error":null,
  "trace_id":"trace_001"
}
```

业务操作按 AI `command.action` 决定，**只从数据库读取受保护的 command，禁止客户端在确认请求中替换 command/preview**：

| action | 确认事务语义 |
|---|---|
| `ADD` | 创建新库存批次，version=1，写入 Added 事件；不覆盖同名旧批次 |
| `CONSUME` | 扣减指定批次数量；用相容单位换算；归零 → `FINISHED`；事件 `Consumed` |
| `OPEN` | 写入 `opened_at`，数量不变；开封过则不得重复写事件；事件 `Opened` |
| `MOVE` | 改 `location`，数量不变；目标位置相同时不得重复事件；事件 `Moved` |
| `DISCARD` partial | 只扣减指定量；仍有数量保持 `ACTIVE`；事件 `Discarded`，与消费分账 |
| `DISCARD` all | 重新检查版本、当前数量与状态；扣至零 → `DISCARDED`，不允许自动用新数量替换旧草稿 |
| `PLAN_ADD` | **不是库存入库**；向该家庭唯一共享购物清单添加待购条目，记录 `added_by_user_id`；不创建库存批次 |

**单个数据库事务严格执行顺序**：
1. 校验用户会话、家庭成员关系、草稿归属、草稿 revision/状态/有效期、幂等键及其请求指纹。
2. 对目标批次加锁或使用 `UPDATE ... WHERE id=:id AND household_id=:hid AND version=:expected_version` 做乐观并发更新；再次校验日期、库存、单位、状态、库存版本以及 AI 已读事实。`ADD/PLAN_ADD` 使用相应并发唯一约束。
3. 执行真实库存或共享清单写入；将受影响批次 version +1。
4. 追加带 before/after 快照的不可变事件（`PLAN_ADD` 可写购物清单审计事件，而不是库存事件）；将草稿置 `CONFIRMED`，保存幂等结果与关联 `request_id/trace_id/actor`。
5. **统一提交**；任一步失败则全部回滚。响应丢失时同键重试只返回先前已提交结果，不重复写入。

`Idempotency-Key` 至少在 `(household_id,user_id,operation,key)` 域内唯一；相同键 + 相同请求返回原结果，相同键 + 不同请求 `409 IDEMPOTENCY_CONFLICT`。不应使用“收到请求就直接成功”的缓存代替数据库唯一性/行锁保障。版本不符 `409 VERSION_CONFLICT`，余额不足 `409 INSUFFICIENT_STOCK`，草稿 revision 冲突 `409 DRAFT_CONFLICT`。并发下最多一个修改成功。

**购物清单特别约束**：家庭只拥有一份共享购物清单，已购标记继续沿用 v0.3 的事务自动入库与 `source_shopping_list_item_id` 唯一保护；`PLAN_ADD` 仅创建待购条目，不能假装已购或绕过原幂等逻辑。

### 5.6 `GET /api/v1/inventory/batches?household_id=...` — App 库存（v0.5）

用户 Bearer Token；分页和 `name/status` 筛选，由家庭权限过滤。返回 Batch 列表及页游标。App 库存展示必须以这里的**已提交真实事实**为准，不能使用 P1 `preview.after` 替代。

### 5.7 `GET /api/v1/inventory/events?household_id=...` 与 `POST /api/v1/inventory/events/{id}/undo` — 事件与撤销（v0.7）

- 事件查询需按家庭鉴权，提供 actor、action/type、`quantity_delta`、before/after、时间、trace/request；敏感内部元数据可过滤。
- 撤销请求携带 `Idempotency-Key` 和 `{"expected_version":8}`；同一事务锁定批次，要求欲撤销事件是**该批次最新可撤销事件**且版本一致。
- 成功时保留原始事件、追加 `Correction` 事件，并恢复 **数量、日期、位置与状态** 等 before 状态，version 再 +1；若已有后续事件/冲突则 `409`，不能覆盖新事实。
- 不执行模型调用；结果同键可重复获取。对 `ADD`、购买自动入库、已有其他实体引用的批次撤销应定义特殊业务约束，不能简单删除历史数据或破坏共享清单来源关联。

## 6. 推荐持久化结构（只新增缺失字段/表；实施前确认 v0.4 schema）

| 表或修改点 | 核心字段（建议） | 作用 |
|---|---|---|
| `inventory_items` 批次结构扩展/映射 | `opened_at DATE NULL`, `status`, `version INT NOT NULL DEFAULT 1`, `quantity NUMERIC(20,6)`；校验名称、单位、家庭外键等 | 兼容 AI P1 `Batch`；保留现有 shopping→stock 来源唯一约束 |
| `inventory_events` | `id`, `household_id`, `batch_id`, `actor_user_id`, `event_type`, `quantity_delta`, `before_json`, `after_json`, `request_id`, `trace_id`, `created_at`, `correction_of_event_id` | 可追溯变更和撤销；事件不可物理覆盖 |
| `ai_tasks` | `id`, `user_id`, `household_id`, `request_id`, `original_text`, `status`, `clarification_context_json`, `revision`, `created_at`, `expires_at`, `trace_id`, `response_json` | 保存最新澄清状态、任务恢复和 AI 请求去重 |
| `ai_drafts` | `id`, `task_id`, `user_id`, `household_id`, `action`, `command_json`, `preview_json`, `revision`, `status`, `created_at`, `expires_at`, `confirmed_at` | 用户编辑、查看和确认；P1 不存草稿 |
| `idempotency_records` | `id`, `household_id`, `user_id`, `operation`, `key`, `request_hash`, `result_json`, `state`, `created_at` | 确认、撤销等防重；复用已存在同类表时不重复创建 |

重要约束：
- `ai_tasks` 唯一索引 `(user_id, household_id, request_id)`；`idempotency_records` 唯一 `(user_id, household_id, operation, key)`。
- `inventory_events` 以 `household_id/batch_id/created_at` 建索引；事件和批次必须关联同一家庭，避免跨家庭外键漏洞。
- 任务内存快照是敏感家庭数据，应限制访问、保留期限和日志输出，不向 App 暴露完整 `ClarificationContext.scope`。
- PostgreSQL 为权威事实源；澄清快照只作对照，不替代最新查询。
- 逐项核对原 `inventory_items` 的字段命名、已有状态、主键类型和购物清单入库函数；新增迁移版本应从 `20261014_0003` 继续，不得重建六张旧表、删除数据卷、修改历史 migration。

## 7. 可复用的异常码与 HTTP 语义（建议业务网关版）

| HTTP | `error.code` / 情况 | App 处理 |
|---|---|---|
| 400/422 | `VALIDATION_ERROR`, `INVALID_UNIT`, `INVALID_CLARIFICATION` | 提示重新填写 |
| 401 | `UNAUTHENTICATED` | 重新登录 |
| 403 | `HOUSEHOLD_FORBIDDEN` | 不展示其他家庭数据 |
| 404 | `BATCH_NOT_FOUND`, `TASK_NOT_FOUND`, `DRAFT_NOT_FOUND` | 刷新或返回列表 |
| 409 | `VERSION_CONFLICT`, `DRAFT_CONFLICT`, `CLARIFICATION_CONFLICT`, `CLARIFICATION_EXPIRED`, `IDEMPOTENCY_CONFLICT` | 展示最新候选/任务，不自动提交 |
| 409 | `INSUFFICIENT_STOCK`, `NOT_LATEST_EVENT`, `UNDO_NOT_ALLOWED` | 显示真实库存及拒绝原因 |
| 503/504 | `TOOL_UNAVAILABLE`, `AI_UNAVAILABLE`, `AI_TIMEOUT` | 保留原文和字段，通过任务 ID 查询/手动恢复 |

AI 内部可能以 HTTP 200 + `status=error` 返回 `AGENT_TIMEOUT`、`VERSION_CONFLICT` 等：网关须区分**AI 任务状态**与**业务 HTTP 状态**，不能把 AI `error` 变成可确认的草稿。业务错误映射须通过实装测试对齐 P1 `DomainError` 的实际行为。

## 8. 最小部署与配置方案（暂不执行）

现有 Docker Compose 项目继续保留 `backend` 和 `db`；增加 `ai` 服务，容器内监听 `0.0.0.0:8767`，**不添加任何 `ports:` 公网映射**。容器内部通信：

- backend 调 AI：`http://ai:8767/agent/message` 与 `/agent/clarification`。
- AI 读 backend：`BACKEND_BASE_URL=http://backend:8000`。
- AI 运行：在 `agent/` 目录执行 `python -m uvicorn p1.app:create_app --factory --host 0.0.0.0 --port 8767`。
- 秘钥配置（保密、不提交）：`AI_SERVICE_TOKEN`、`BACKEND_TOOL_TOKEN`、`P1_ENGINE=rules|deepseek`；真实模型额外设置 `DEEPSEEK_API_KEY`、`LLM_MODEL`。
- P1 默认 `deepseek`，初次联调建议先用 `rules`（无需付费），对齐结构后再切真实模型。
- P0/P1 共享 `agent/.cache/p0/budget.sqlite` 费用账本；必须配持久化卷，否则替换 AI 容器可能丢失账本。原项目 20 元额度是团队管理预算，不是云端供应商的强制限额；还要在供应商端设置限额和审计。
- 保留 API/数据库端口最小暴露，禁止公网发布 PostgreSQL 5432、FastAPI 内网直连 8000、AI 8767。Android 正式外网接入后通过单一 HTTPS 反向代理。
- 当前云服务器资源较小，先检查 `docker stats`、Swap、AI 容器 RSS 与吞吐；AI 不运行本地大模型推理，无需 GPU，但仍占 CPU/内存。

## 9. 推荐实施里程碑与验收

### v0.5：库存模型与可信只读工具（优先实施）

1. 备份 v0.4 源码和 PostgreSQL，检查实际表结构及现有自动入库行为。
2. 通过增量 Alembic 迁移补齐批次 `opened_at/status/version` 等，并建立事件表骨架；回归共享清单自动入库测试。
3. 开发两个 `/internal/v1/inventory/*` 接口 + 面向 App 的库存列表 API；严格限定工具令牌和家庭身份。
4. 建立符合 P1 `Batch` 的契约测试：同名多批次、零库存、未知字段、跨家庭 404、数量精度、版本递增、目标 ID 一致性。

**验收条件**：P1 `RemoteInventoryReader` 能真实读到 PostgreSQL 的同一家庭数据；跨家庭读取禁止；既有已购→入库幂等不回归。

### v0.6：AI 网关、澄清与草稿存储

1. 部署 P1 内网服务，先 `P1_ENGINE=rules`；通过不同 token 建立双向认证。
2. 实装 `/api/v1/agent/messages`、`/api/v1/agent/tasks/{id}`、`/api/v1/agent/clarifications/{id}`、`GET/PATCH /api/v1/drafts/{id}`。
3. AI 五种状态映射，保存完整 P1 context、revision、TTL、候选、草稿与预览；任务去重和断线恢复。
4. 验证“未确认不写库存”、重复请求不二次付费、澄清不二次模型调用、候选变化/旧 context/过期拒绝。

**验收条件**：从 App/Swagger 发自然语言，可得到真实批次事实、候选和待确认草稿；库存仍不因 AI 消息而变动。

### v0.7：确认、事件与撤销

1. 逐一实现 ADD/CONSUME/OPEN/MOVE/DISCARD 的事务与事件，PLAN_ADD 连接家庭唯一共享清单。
2. 实装幂等键、乐观版本/行锁、事件追溯和 Correction 撤销。
3. 注入数据库写入失败、并发旧版本、响应超时、服务/容器重启、重复确认、跨家庭越权，保证不重复、不串户、不半提交。
4. 使用 DeepSeek 真实 API 做受控小规模端到端测试，并请前端验证核对表单与确认显示。

**验收条件**：同键重试不会二次入库，旧版本写入被拒；撤销只针对该批次最新可撤销事件；所有事实重启后持久化且有审计记录。

## 10. 团队需要冻结的设计决策

1. **批次映射**：现有 `inventory_items` 是否本身代表批次？其已有字段、主键格式与购物清单关联是什么？先检查线上代码/数据库再落迁移。
2. **任务隐私**：同一家庭成员是否能查看另一成员的 AI 草稿？建议默认仅创建者可见，真实库存按家庭共享。
3. **家庭时区**：目前若无家庭时区配置建议默认 `Asia/Shanghai`，但不能每次由 App 任意传入未经校验的值。
4. **撤销范围**：撤销“购物清单购买→自动入库”与撤销普通 ADD 不完全一样；必须保护采购来源外键和历史记录。
5. **草稿寿命**：澄清文档明确 15 分钟；确认草稿是否也采用 15 分钟需团队确定，且必须重新校验批次版本。
6. **PLAN_ADD 的去重、采购历史与责任人**：记录添加者，不立即购买；与单家庭唯一购物清单的 v0.3 规则一致。

## 11. 依据与非依据

**直接依据**：`agent(1).zip` 的 `agent/p1/app.py`、`agent/p1/schemas.py`、`agent/p1/tools.py`、`agent/p1/domain.py`、`agent/p1/manager.py`、`agent/p0/domain.py`；两份 2026-10-14 队友 docx 协作文档；已上传的 P1 OpenAPI。

**本设计新增的提议**：`/api/v1/agent/messages`、任务/草稿读取编辑路由、统一业务响应封装、数据表及索引细节、错误映射、分阶段版本划分、最小 Docker 部署方式；这些不是队友声称已经实现的功能，也不是线上已验收功能。

**实施前仍需核验的资料**：线上 v0.4 对应完整 `backend/app/models.py`、Alembic 0001–0003、v0.3 自动入库函数和现有 Compose 配置。待对照后才能生成安全的完整升级代码包和迁移脚本。
