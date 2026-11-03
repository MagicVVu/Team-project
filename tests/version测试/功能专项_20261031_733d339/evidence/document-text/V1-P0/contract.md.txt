# 接口契约 p0-1

`openapi.json` 为 Mock 实际注册的团队契约；`ai-openapi.json` 为正式只读 AI 契约。由 `agent/export_contract.py` 导出，请勿手工修改生成文件。正式业务接口由 CaviarHidon 实现。

## 数据与认证

- JSON 中 Decimal 响应为字符串；请求接受数字或十进制字符串，拒绝 NaN / Infinity。日期 YYYY-MM-DD；事件时间带时区。批次数量不能跨不兼容单位汇总。
- 业务响应 `{success,data,error,mode}`；字段校验及业务失败返回 `{success:false,data:null,error:{code,message},trace_id,mode}`，字段错误可含 fields。`mode:mock` 是开发演示标记，正式后端不得宣称 Mock 已持久化。
- 前端只调用业务后端；后端从已认证用户取得 household。AI 服务入站使用 `Authorization: Bearer <AI_SERVICE_TOKEN>` 与后端信任的 X-User-Id / X-Household-Id；共享服务密钥不能暴露给浏览器。
- AI 读工具使用独立 `BACKEND_TOOL_TOKEN` 与同一身份上下文。业务后端须验证 token、用户成员关系及资源归属；不能把 X-Household-Id 当作任意用户可修改的权限。
- `/agent/message` 直接返回 AgentResult；统一网关包裹 Envelope，并由业务后端为写草稿分配 draft_id。AI 服务不存储、编辑或确认草稿。

## 接口与例子

| 接口 | 请求 / 结果 |
|---|---|
| POST `/api/v1/agent/messages` | `{text,request_id}`；AgentResult 状态与可选 draft_id |
| POST `/agent/message` | 同上；直接 AgentResult，含 original_text、trace_id、draft / candidates / facts |
| GET `/internal/v1/inventory/search?name=牛奶` | `{data:{batches:[Batch]}}`；name 省略则返回该家庭库存，不能包含别家数据 |
| POST `/api/v1/drafts` | 手动 Command，经相同业务校验生成 DraftRecord |
| GET `/api/v1/drafts/{id}` | 草稿及 revision、status、command、trace_id |
| PATCH `/api/v1/drafts/{id}` | `{revision,command}`；重新校验并 revision+1 |
| DELETE `/api/v1/drafts/{id}` | 标记 CANCELLED，不删除库存或事件 |
| POST `/api/v1/drafts/{id}/confirm` | `{revision}` + Idempotency-Key；库存批次 + 事件，或采购清单 |
| GET `/api/v1/inventory` | `{batches:[Batch]}`，含零库存，隐藏已撤销新增的 REVERSED 批次 |
| GET `/api/v1/inventory/events` | `{events:[Event]}`；当前家庭历史，Correction 引用原事件 |
| POST `/api/v1/inventory/events/{id}/undo` | `{expected_version}` + Idempotency-Key；恢复批次 + Correction |
| GET / PUT `/api/v1/shopping-plans/current` | 读 PlanRecord / 写 `{revision,items:[{name,quantity,unit}]}` |
| POST `/api/v1/shopping-plans/current/confirm` | `{revision}` + Idempotency-Key；清单 CONFIRMED，库存不变 |

文字输入：

```json
{"text":"买了两盒牛奶放冰箱上层","request_id":"req-demo-1"}
```

可编辑新增 Command（字段缺省即 null）：

```json
{"action":"ADD","name":"牛奶","quantity":"2","unit":"盒","location":"冰箱上层"}
```

选择 milk-1 后的消耗 Command：

```json
{"action":"CONSUME","name":"牛奶","quantity":"1","unit":"盒","batch_id":"milk-1","expected_version":1}
```

草稿确认请求体 `{"revision":1}`，头 `Idempotency-Key: confirm-demo-1`；成功返回新 batch、event、draft_id 和 trace_id。重试使用同一请求体及同一键；确认后原 draft 变为 CONFIRMED。

失败示例：

```json
{"success":false,"data":null,"error":{"code":"VERSION_CONFLICT","message":"库存已变化，请重新核对并确认。"},"trace_id":"trace_example","mode":"mock"}
```

## 状态、错误与重试

AI 状态固定：needs_clarification、needs_confirmation、answered、unsupported、error。候选由库存读工具提供；商品多个批次不静默猜测。错误结构不接受 SQL、工具名、自由执行动作等额外字段。

| 错误 | HTTP / 处理 |
|---|---|
| UNAUTHENTICATED / HOUSEHOLD_FORBIDDEN | 401 / 403，停止；不存在或无权资源统一不可访问 404 |
| BATCH_NOT_FOUND / DRAFT_NOT_FOUND / EVENT_NOT_FOUND | 404，重查目标，不自动替换批次 |
| VALIDATION_ERROR / INVALID_UNIT / INSUFFICIENT_STOCK | 422，用户修改字段，不自动换算容器容量 |
| VERSION_CONFLICT / DRAFT_CONFLICT / PLAN_CONFLICT | 409，重新读取并明确确认 |
| IDEMPOTENCY_REQUIRED / IDEMPOTENCY_CONFLICT | 422 / 409，补齐键或纠正不同请求体复用键的问题 |
| DRAFT_CLOSED / INVALID_STATE_TRANSITION / UNDO_NOT_LATEST | 409，停止并核对状态 |
| TRANSACTION_FAILED / TOOL_UNAVAILABLE | 503，事务回滚；库存提交重试原键，读取可重试 |
| MODEL_TIMEOUT / MODEL_UNAVAILABLE / EMPTY_MODEL_OUTPUT / INVALID_MODEL_OUTPUT | AgentResult error，原文保留、手动录入；不自动付费重试 |
| PRICING_NOT_VERIFIED / BUDGET_EXCEEDED / MODEL_NOT_CONFIGURED | AgentResult error，修正配置或手动录入；不能绕过预算 |

## 正式后端必须实现的约束

确认时校验用户 / household、草稿最新 revision、库存 expected_version、数量与单位；同事务写 batch、event、草稿状态和成功幂等结果。幂等键按用户与家庭隔离，配合请求哈希及唯一约束；数据库应保证同版本并发最多一个成功。

撤销核对该批次最新事件与当前版本，追加 Correction 和恢复状态，不删除原事件。库存读工具只公开查询，AI 凭据不授予命令执行能力；正式网关和确认接口由后端持有，用户确认不依赖模型置信度。

Mock 使用 RLock 与内存快照模拟这些契约，进程重启不持久化；正式实现必须补真实数据库验证。开发专用 `/api/mock/*` 不进入 service 模式或正式前端契约。
