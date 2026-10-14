# V1-P2 AI 风险接口与协作说明

本阶段仅增加 AI 服务内部能力。现有 Android 对话、详情和提醒页面是输出设计依据，前后端接入暂缓。实际契约见 [ai-openapi.json](ai-openapi.json)；P0/P1 历史契约不变。

## 认证与读取

所有业务接口要求 AI_SERVICE_TOKEN Bearer 认证及可信后端提供的 X-User-Id、X-Household-Id。App 不持有内部服务密钥。库存只读凭据仍为独立 BACKEND_TOOL_TOKEN，使用现有两条 GET 工具接口：

- `/internal/v1/inventory/search?name=...` → `{data:{batches:[Batch]}}`。
- `/internal/v1/inventory/batches/{id}` → `{data:{batch:Batch}}`。

后端需要继续核验家庭成员关系与资源归属。AI 检查跨家庭、重复 ID、目标 ID 和读取数量上限。

## P2 批次新增字段

| 字段 | 值与说明 |
|---|---|
| category | food／medicine／household／unknown；默认 unknown，不能由名称猜类别 |
| product_id | 具体商品标识或 null，用于匹配该商品的包装开封规则 |
| label_date_type | use_by／best_before／expiry／unknown；默认 unknown，不能把“保质期”等文字自动当成 use-by |
| label_context_valid | true／false／null；仅在已确认当前处理状态仍适用原标签时为 true；烹调、冷冻、分装等不能默认为原标签有效 |
| storage_condition | ambient／refrigerated／frozen／null；明确登记的实际保存条件，不从 location 推断 |
| label_storage_condition | 同上，表示包装要求，未知为 null |
| is_opened | true／false／null；未知与未开封不同，不能从 opened_at 缺失直接推定 false |

原有 opened_at、label_expiry、purchased_at、status、version 等字段保留。后端尚未返回新字段时，P2 接受旧记录并保守待核对；不要为了消除待核对提示伪造默认值。P2 委托 P1 时将扩展字段投影为原契约，库存查询结果仍保留实际已读扩展事实。

## 直接风险评估

`POST /risk/evaluate` 不调用模型。请求可按名称、明确批次 ID 列表或整家庭查询；name 与 batch_ids 不能同时出现。批次 ID 最多 100 个，整家庭读取最多 1000 条。

```json
{"batch_ids":["milk-1"],"household_timezone":"Asia/Shanghai","reminder_days":3,"attention_only":false}
```

reminder_days 是用户提醒偏好，0～365，默认 3；不是食品或药品安全天数。时间来自服务时钟，家庭时区为有效 IANA 名称，默认 Asia/Shanghai。请求不得携带库存事实、规则、风险等级或伪造当前时间。

响应含 trace_id、evaluated_count、returned_count、facts、risks、inventory_writes:false。每条 RiskResult 包含：

- 批次 ID、名称、读到的 version，level、attention、excluded。
- reason_codes 与 evidence；证据含实际字段、规则 ID／版本与来源引用。
- missing_information、recommended_action、evaluated_at、household_timezone。
- ruleset_version、rule_versions、source_human_reviewed、safety_guaranteed:false。

## 等级与缺失规则

| 等级 | 产品含义 |
|---|---|
| red | 当前适用标签期限已超过，需优先核对和处理 |
| orange | 保存条件不符，或商品包装开封窗口已达到，需要核对 |
| yellow | 进入提醒窗口，或已超过品质日期；品质日期不能单独确定安全 |
| unknown | 必需事实或规则不足／冲突，显示待核对 |
| green | 已知登记事实未触发规则，不能显示“已检测安全”或作使用保证 |

确定的 red／orange 原因保留，同时返回缺失信息。普通日期关注或无触发若仍缺必要事实，则降为 unknown。结束、已撤销或零库存批次 excluded=true，不纳入关注列表；单批查询仍可解释其结束状态。排序为 red、orange、yellow、unknown、green，再按名称和批次 ID。

食品 use-by 与药品 expiry 在家庭日期超过标签日后触发；同一天仍可进入日期提醒。只有明确确认标签类型与适用性时才应用期限规则。原标签日期不因开封规则变长。对烹调、冷冻等后的新期限，本阶段不推断。

已开封需要对应 product_id、适用保存条件和包装来源的审核规则；没有则缺 after_open_rule。按天数记录的开封窗口在 opened_at＋规则天数当天保守提示核对，不宣称精确小时。多个同类规则同时适用时返回冲突，不自动选择最新版本或最宽松天数。

## Manager 与页面

`POST /agent/message` 保留 text、request_id、household_timezone，并新增可选 reminder_days。新增 QUERY_RISK 意图，如“哪些需要关注”“牛奶为什么被提醒”“开封的牛奶还能喝吗”。模型只提取任务与原文名称，等级、事实和解释来自确定性工具及受控中文模板。

无名称的关注问句评估当前家庭并仅展示 attention=true 项，待核对也属于关注；带名称时返回该名称的所有匹配批次。指代不清的“这批”要求补名称，不默默扩展为整家庭。多物品明确列表或变更加风险请求提示分次提交。同名多批次的风险查询逐批展示，不选择一个批次覆盖其他结果。

P1 的草稿及澄清流程继续可用。风险缺字段返回 answered＋unknown＋missing_information，不把用户问句中的日期或保存断言当成已确认事实。资料补充应由业务后端的编辑／确认路径保存，再重新评估；本阶段不提供风险事实写入或风险专用澄清数据库。

| 现有页面 | 后续接入内容 |
|---|---|
| AI 对话 | 基于工具的中文解释；保留原文与历史快照；不把用户问题当写入 |
| 物品详情 | 等级文字、触发事实、来源与规则版本、计算时间及待补信息 |
| 库存提醒 | 关注列表包含待核对，排除终态；按等级排序，不使用颜色作为唯一说明 |
| 资料编辑 | 由后端保存新字段并重新评估；位置与实际保存条件分开 |

## 本地规则与错误

`GET /knowledge/rules?category=food` 返回本地规则与 ruleset SHA256；只读，不进行联网检索。reviewed=false 或 enabled=false 不参与计算。review_kind 区分自动来源核对和人工审核，不能把 source_check 报告为专家审核。配置中的包装引用仅作证据，不在运行时抓取或执行引用内容。

鉴权失败 HTTP 401，字段失败 HTTP 422；直接工具故障和总超时 HTTP 503 返回 error envelope。消息接口处理中的故障返回 status=error、error_code、manual_entry 和 retryable，与 P1 的消息状态方式一致。跨家庭失败不返回库存 facts 或 risks；库存变化后的风险查询每次重新读取，不缓存旧判断当成当前事实。

后端联调仍需：新增可为空的事实字段、可靠时间和家庭时区、标签及保存数据核验、人工规则审核、正式环境测量。P2 不实现预测、自动采购、主动通知、图片识别、RAG 或多 Agent 拆分。
