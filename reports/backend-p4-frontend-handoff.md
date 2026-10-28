# MagicVVu P4 Android 业务数据交接

2026-10-23，本地实现未部署。Android继续用公开认证网关 `POST /api/v1/agent/messages` 或P2会话/可信引用入口，四字段消息契约不变；任务GET仍用于恢复。内部规划路径不属于Android API，禁止在APK保存BACKEND_TOOL_TOKEN/AI_SERVICE_TOKEN或直接调用内部端口。本轮未改Android源代码。

## 当前可接入

消息示例：`{"household_id":"<当前家庭>","text":"牛奶消耗统计","request_id":"<稳定请求ID>","household_timezone":"Asia/Shanghai"}`。恢复与草稿确认继续遵循P2/P3前端交接，不混用引用或客户端自建内部context。

- 消费详情事实：`GET /api/v1/households/{household_id}/consumption-events`（沿用现有公开认证与分页），只计真实Consumed。Discarded/Opened/普通数量调整不显示成吃掉/喝掉。列表分页未结束不能声称全部历史。
- AI结构化统计：任务`result.consumption_summary`包含item_key/name/unit、window_start/window_end_exclusive、observed_days、effective_quantity、effective_events、event_ids、status/reason_codes。窗口为家庭时区完整日，排除今天；显示真实返回窗口，不强行标固定28天。
- 数据更新时间：展示result.evaluated_at和snapshot_id；它是本次计算使用的快照采集时刻，不是库存人工核实时间。普通库存updated_at同样不是核实时间。
- 耗尽依据：result.forecast的current_stock、daily_recorded_consumption、remaining_days、reference_date、summary及reason_codes。只有estimated且有可信数据时显示估计日期；显示“按记录消费，未来不补货、消费接近窗口”的条件，不能标为保证可用。
- 建议：result.recommendations的source/status/current_stock/pending_quantity/target_stock/suggested_quantity/unit/reason_codes。Decimal字符串避免客户端浮点舍入；数量和单位整体展示。没有suggested_quantity时显示不可用，不补0。

## 当前真实不可用状态

现有业务没有消费覆盖或人工库存核实来源，正常出现RECORDING_COMPLETENESS_UNKNOWN、NO_COMPLETE_COVERAGE_DAYS、STOCK_VERIFICATION_REQUIRED、USABLE_STOCK_REQUIRES_REVIEW。统计可能携带effective_quantity=0的算法占位，但status!=complete或observed_days=0时必须显示“记录覆盖不足，无法判断消费量/速率”，**不得展示成0消费**。可以另展示已记录Consumed事件列表及对应范围，文案明确“已记录”，不要等同现实全部消费。forecast.rate/date为null时显示不可用原因。

PENDING_INCOMPLETE表示家庭待购读取/关联不能证明完整；同名待购可能存在，不能以局部空列表标无重复采购。过期快照STALE_PLANNING_SNAPSHOT需重新查询，不延用旧数。PLANNING_INCOMPLETE/PLANNING_CONTEXT_UNAVAILABLE/TOOL_UNAVAILABLE显示暂不能提供完整数据并允许重试，保留原任务请求去重策略。

## 已有偏好与最低库存0

公开库存创建/PATCH已有minimum_quantity。新请求显式包含这个字段时后端保存“明确业务输入”来源，可区分0和未设置；客户端仅在用户明确设置时发送，不能为未设置字段自动补0。PATCH仍要expected_version及稳定operation_id。创建省略该字段沿用DB0，但规划视图标未知。旧记录0无历史证据仍未知；正值是真实规则阈值，旧操作者/时间可能未知。

原StockResponse.minimum_quantity仍是兼容的数值列，**不能仅据公开DTO的0在偏好界面声称用户已设置**；原公开DTO尚无minimum_stock_known/source字段。当前可通过AI结果的不可用原因展示限制；需要专门显示“已设置/未设置”全量偏好时，P5应增加经家庭认证的公开偏好DTO（minimum_stock:null/"0"、source、version），不可让Android读取内部来源区。本轮该偏好展示DTO未实现。

补货覆盖天数、提前期、订货包装均无保存入口，UI显示未设置/暂不可用，不将默认7天/1盒写为用户偏好。“最低库存规则”以用户阈值为目标；“AI记录预测补货”以完整消费窗口速率×覆盖+提前期为目标。source必须区分minimum_stock/recorded_history。当前AI还缺核实/风险事实，不能因为已有最低库存就直接确认自动建议。

继续先读`GET /api/v1/agent/execution-capabilities`，automatic_planning_commit=false。AI预测补货不得直接调用普通PLAN_ADD绕过；用户明确购物计划仍通过原确认草稿/operation_id链路。当前自动建议提交会被后端拒绝PLANNING_REVALIDATION_UNAVAILABLE。

## P5需要新增的业务入口（草案，均未实现）

1. 库存盘点确认：建议公开 `POST /api/v1/households/{household_id}/inventory-verifications`，只允许当前登录成员；请求operation_id、expected_batch_versions完整集合、盘点结果/明确确认及范围。后端应锁定/比对当前完整库存集合与版本，漏批次/新增批次/版本变化返回冲突，绑定操作者/服务端checked_at/source/各批次版本，保留不可变审计记录及幂等回执。不得由新增或编辑自动触发，不得让客户端传user_id/可信checked_at/verified=true。盘点当前数量不等于确认历史消费完整，也不直接等于风险意义上的usable_quantity_verified。
2. 消费记录覆盖：单独明确用户确认的家庭/商品/日期区间及该期间是否全记、是否缺货/未知调整；后端需要业务审核后的完整性证据与中断/纠正规则。不能单凭“库存准确”勾选自动生成过去28天完整记录。该接口和持久模型需产品/AI/后端联合确定，当前没有路由或存量覆盖。
3. 商品目录：显式选择稳定product_id并维护包装/可换算单位，历史批次仅由用户或有审计来源的匹配确认，不按名称批量回填。保留批次日期/状态。当前一批次一item，不做商品级跨批次消费总量。
4. 补货偏好：经认证/版本校验的显式设置/清除；区分null与0，覆盖天数/提前期/订货单位与容量成对校验。先交公开偏好可知状态，再接界面，不能沿旧非空零列猜设置状态。
5. 标签事实：可选登记日期类型、厂家标签、储存条件与来源，位置选择不自动等于冷藏条件；审核安全规则仍由业务/AI同事负责。

上述是后续接口要求而非本轮已完成能力。真实响应见backend-p4-http-evidence.json、backend-p4-sqlite-examples.json；完整覆盖示例键TEST_ONLY不用于产品演示或生产结论。P5需Android真机、弱网/进程恢复、权限切换联测后另行获准发布。
