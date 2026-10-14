# V1-P1 AI 接口与现有页面映射

这是内部只读 AI 契约。实际注册接口由 `python -m p1.export_contract` 导出到 [ai-openapi.json](ai-openapi.json)，无需模型或业务后端。P0 接口、App 网络客户端和未完成的业务网关均不在本次修改范围。

完整、可按 schema 校验的请求／响应以及澄清续接示例见 [examples.json](examples.json)，使用明确标注的合成测试夹具生成，不代表运行中的假库存服务。

## 页面与字段

| 现有设计 | AI 输出 | 后续页面接入要求 |
|---|---|---|
| 首页 AI 卡片／对话面板 | `reply`、五种 `status`、`trace_id`、`trace` | 显示回答或下一步；历史回答为当时快照；错误保留原输入 |
| 录入核对表单 | `draft`、`preview`、`original_text` | 开封只核对日期，移动只核对目标位置，丢弃核对定量／全部及实际减量；明确尚未写入 |
| 批次选择与补字段 | `candidates`、`missing_fields`、`clarification` | 候选显示名称、数量、单位、位置、开封日期、状态和版本；不默认选择第一批 |
| 物品详情 | `facts` 中真实批次字段 | 日期未知显示未知；结束状态和开封时间独立展示 |
| 冲突／失败反馈 | `error_code`、`retryable`、保留的澄清上下文 | 版本变化重新选择／核对；失败不显示成功写入 |

当前 App 客户端仅保留候选 ID，且草稿统一要求数量；后续接入需扩展这些数据结构。现有设计的多项语音录入不改变 P1 单物品、单动作限制。风险、预测、语音音频和自动推荐不属于此版本。

## 请求与响应

`POST /agent/message`：

```json
{"text":"牛奶昨天开封了","request_id":"request-1","household_timezone":"Asia/Shanghai"}
```

家庭时区默认 Asia/Shanghai，正式调用由可信后端填写有效 IANA 名称；当前时间取 AI 服务器时钟，不由模型或 App 提供。相对日期以任务创建时刻为参考，跨午夜续接不会重新解释“昨天”。日期只支持严格 YYYY-MM-DD、今天、昨天，其他表达进入澄清。未来开封日期拒绝。

五种状态与 P0 相同：`needs_confirmation`、`needs_clarification`、`answered`、`unsupported`、`error`。HTTP 成功直接返回 AgentResult，不包业务网关 envelope。身份认证错误 HTTP 401；请求格式错误 HTTP 422；处理期间的业务／模型错误在 AgentResult 中返回 `error_code`。

`draft` 按 `action` 区分，JSON Decimal 为字符串：

| action | 草稿字段（除 name） | 规则 |
|---|---|---|
| ADD | quantity、unit、可选 location／purchased_at／label_expiry | 不带 batch_id，不覆盖旧批次 |
| PLAN_ADD | quantity、unit | 用户明确指定的采购草稿，不改变库存 |
| CONSUME | batch_id、expected_version、quantity、unit | 只扣目标活动批次，不超库存 |
| OPEN | batch_id、expected_version、opened_at | 整批开封，无 quantity／unit；已开封返回 answered |
| MOVE | batch_id、expected_version、to_location | 整批移动，无 quantity／unit；目标相同返回 answered |
| DISCARD | batch_id、expected_version、discard_mode、quantity、unit | partial 为明确数量；all 的实际数量、单位来自工具；归零建议状态 DISCARDED |

所有定量操作最多六位小数、上限 10 亿，仅 ml↔L、g↔kg 可换算。数量与“全部”同时出现时要求重新表达，不静默选择一种解释。终态或零库存批次不生成新变更。缺字段、模糊数量、多批次不会进入待确认草稿。

`preview` 是**拟议结果**：`prospective:true`，包含 before、after、event_type、quantity_delta；after 不分配新版本或事件 ID。开封／移动的数量差为 0；丢弃对应 Discarded，不作为消费。采购草稿 `inventory_changes:false`。这些字段不意味着已执行，也不能代替后端事务校验。

## 结构化澄清续接

`POST /agent/clarification` 接收 `{context, revision, answers}`。其中 answers 的示例片段为：

```json
{"batch_id":"milk-1","opened_at":"昨天"}
```

完整请求见 examples.json 的 `continuation_request`。context 必须是 OpenAPI 所定义的对象，revision 对应该任务的当前修订。业务调用方保存上一响应的完整 `clarification`：任务 ID、revision、scope、原文、已解析字段、完整候选、选中批次、允许补充字段、创建时间、15 分钟有效期及原 trace_id。

1. 已认证业务后端根据任务 ID 读取保存的**最新**上下文，核对拥有者和最新修订；不能直接转发 App 提交的 context。
2. `revision` 必须与所保存上下文一致；`answers` 只接受当前 `allowed_fields` 中的非空字段，以及当前候选内的 batch_id。动作、全部／部分模式、家庭身份、预期库存版本不能通过答案修改。
3. AI 保留已补字段并递增 revision；继续缺字段时返回更新上下文。同一任务沿用 trace_id、创建时间和有效期，补字段不延长有效期。
4. 唯一批次在第一次澄清时也保存快照；续接重新 GET 目标批次。版本或事实变化返回 `VERSION_CONFLICT`、最新候选和新修订，要求重新选择；“全部丢弃”随后从最新快照取量。
5. 结构化补字段不再次请求模型；工具超时或失败保留已填内容，允许重试。已过期任务需要重新提交原文。

AI 无状态，无法独立判断调用方是否重放了一份“内部自洽的旧 context”。业务后端必须通过任务存储、拥有者绑定、有效期和最新 revision 管理防止乱序／重放；本阶段测试只证明 AI 对所提供受信上下文的校验行为。不要宣称已实现业务任务持久化或重放防护。

## 错误与后端交接

| 错误码 | 行为 |
|---|---|
| UNAUTHENTICATED／HOUSEHOLD_FORBIDDEN | 停止，跨家庭结果不返回候选或上下文 |
| BATCH_NOT_FOUND | 初次查询提示改名称；续接目标已消失返回错误，不能替换其他批次 |
| BATCH_TERMINAL | answered，不产生草稿 |
| INVALID_UNIT／INSUFFICIENT_STOCK／VALIDATION_ERROR | 保留任务，修改单位或数量 |
| VERSION_CONFLICT | 展示最新批次，必须再次选择／核对 |
| CLARIFICATION_CONFLICT／CLARIFICATION_EXPIRED | 获取最新任务或重新提交原文 |
| INVALID_CLARIFICATION／INVALID_CANDIDATE | 拒绝越界补字段或非候选选择 |
| AGENT_TIMEOUT／TOOL_UNAVAILABLE | 保留原文与已填字段，允许显式重试 |
| MODEL_TIMEOUT／MODEL_UNAVAILABLE／MODEL_HTTP_*／INVALID_MODEL_OUTPUT／EMPTY_MODEL_OUTPUT | 模型失败，不写库存，不自动付费重试 |
| MODEL_NOT_CONFIGURED／PRICING_NOT_VERIFIED／BUDGET_EXCEEDED | 修正配置、费率或预算；不绕过限制 |

正式后端以后实现草稿编辑、确认事务、幂等、事件与撤销。确认时必须重新读取事实并验证 expected_version；OPEN／MOVE 的事件数量差为 0 但提交仍需递增库存版本；丢弃归零为 DISCARDED，消费归零为 FINISHED。AI 返回的 preview、trace 或 needs_confirmation 都不是库存变更成功凭证。
