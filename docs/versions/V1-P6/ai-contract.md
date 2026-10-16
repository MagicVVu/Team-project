# P6 AI契约与接口预留

日期2026-10-16，AI版本0.6.0，策略v1-completion-1，提示v1-extract-1。代码入口为 v1.app:create_app；复用既有认证、模型与共用账本，不自动读取.env。Jev状态为deferred_by_user。

## 1. 当前AI接口

全部业务接口需要内部Bearer服务认证及可信X-User-Id/X-Household-Id，家庭权限继续由业务工具验证；前端不得持有内部令牌。

| 方法/路径 | 用途 | 实际行为 |
|---|---|---|
| POST /agent/message | 用户确认文字或最终语音转写 | 原有动作/查询及位置反查、明确用完、关注摘要；首次至多一次模型提取，字面明确的新路径可零次 |
| POST /agent/clarification | 缺字段/候选续接 | 修订/作用域/有效期/重新读取校验；0次模型调用，不执行确认写入 |
| POST /risk/evaluate、GET /knowledge/rules | 确定性风险与适用审核规则 | V1发布配置只启用human_review；当前默认5条source_check规则不算人工审核 |
| POST /consumption/query、/forecast/evaluate、/procurement/suggest | 消费、条件预测、建议/单项草稿 | 复用P3算法；缺少可靠数据时降级，PLAN_ADD仅待确认 |
| POST /overview/query | 按需关注摘要 | 风险与规划分块给出状态、时间与快照；展示上限50，truncated与total_count明确，不后台推送 |
| POST /feedback/after-commit | 已提交操作的只读重算 | 只接operation_id及时区；从后端GET验证凭证、批次版本，再计算；不再次提交 |
| POST /capabilities/check | 受信调用方主动检查真实读取能力 | 声明缺少的接口/事实/人工审核；不写数据库 |
| GET /health | 进程/版本配置 | 不读取业务数据；production_chain_verified=false，不能当正式正向验收 |

初次和澄清各有覆盖模型、读取和计算的10秒总截止。无自动付费重试；已有部分事实/已提交凭证时，超时保留已核实结果并说明刷新未完成。

## 2. 现有数据库网关保持不变

公开消息仍仅 household_id/text/request_id/household_timezone。公开澄清仍用revision和非空answers，原九字段：name、quantity、unit、location、purchased_at、label_expiry、opened_at、to_location、batch_id。

P3商品候选通过真实batch_id作锚点；AI在受信上下文和重读快照中映射item_key，并统计该商品全部批次。没有批次锚点时仅允许名称唯一确定；同名无法消歧时继续核对，不猜选。恢复使用GET原任务，禁止空answers、伪造batch_id或将item_key塞入公开协议。

v1.tasks.TaskClient只操作消息、澄清、任务和草稿；继承现有HTTP/幂等/权限规则。v1.tasks.Task增加P6结果字段，旧interaction客户端与旧工厂保持原样。不要将旧严格结果解析器直接用于P6新增结果；发布前处理旧待澄清任务的版本兼容，不迁移或改写任务数据库。

新续接协议为v1-local-1及v1-batch-selection-1；受信业务方保存并传回完整私有context，公开返回仍只暴露网关已有的修订、允许字段及有效期。AI保持无状态。已有P1/P2/P5通用补字段上下文继续由原流程处理；旧内部P3 item_key入口仍在原P3/P5配置保留。

## 3. 草稿与页面字段

Command仍按action区分，未增加FINISH/UNDO/ADJUST命令。明确“已经用完”最终输出CONSUME，quantity/unit来自选定批次当前登记量，expected_version是该次读取版本，预览为FINISHED；用户仍须核对确认。Finished不是另一条可重复累计的消费。全部丢弃仍为DISCARD，不进入消费统计。

| 返回字段 | 页面用途 |
|---|---|
| status、reply、trace_id、original_text | 五种AI状态、解释、原文保留；processing仍由网关任务层表达 |
| draft、preview、candidates/item_candidates | 现有确认表单、前后状态和真实候选，不默认选择第一批 |
| quantity_source | user_input/current_batch/planning_calculation，区分用户数量、登记剩余量和建议计算 |
| risks、guidance | 等级/证据/规则/缺失事实与补录指引；提示不等于已保存事实 |
| consumption_summary、forecast、recommendations、planning_basis | 观察窗口、有效消耗、条件预测、待购抵扣及确认时复核依据 |
| sections、data_gaps、truncated、total_count | 摘要各块可用性、数据欠项、展示上限与读取完整性 |
| feedback | 已核实业务提交、原业务trace、较新变更/待刷新；刷新失败不抹掉成功 |
| decisions、request_id、runtime | 四节点实际来源、请求关联、提示/规则/模型版本及调用数；不含内部推理或密钥 |

所有AI路径均不写库存/清单。只有业务服务的确认结果可展示已写入；pending草稿、预览或用户文本“我已确认”不能充当提交凭证。撤销/纠错仍由业务服务关联原事件完成。

## 4. 预留规划事实接口

**GET /internal/v1/planning/context**，Bearer内部工具认证、可信身份头；name/item_key二选一，可均不填查询完整范围。响应为data包裹的PlanningSnapshot，机器规范见planning-context.schema.json及backend-read-openapi.json。该路由在本轮后端0.8.0 OpenAPI中尚未提供。

建议protocol_version=v1-planning-context-1；兼容旧p3-planning-context-1。必需事实沿用P3：scope、snapshot_id、as_of、event_watermark、shopping_version、完整性、稳定商品、批次数量/版本、已提交语义事件、发生与录入时间、覆盖/来源、偏好和共享待购。AI不解析展示历史文本、不猜商品对应、不把未返回的待购当零。

新增每商品stock_verification：checked_at（带时区的实际核对时间）、source（业务可解释来源）。默认核对最大年龄168小时；这是版本化项目策略，非经真实回测证实的阈值。API快照刚读取不代表实际库存刚核对；缺失、未来或陈旧核对时保留有效消费统计，但不给精确耗尽日期或自动采购草稿。

快照最多1000商品，超规模或分页未完成应返回明确不可用/冲突。as_of超过300秒或不可信也拒绝。业务要保证快照、水位、版本和完整性含义；来源字符串本身不是用户记录真实完整的证明。公开采购JWT接口不能直接用内部service token调用；由业务合法聚合已有共享清单，明确source_inventory_item_id到商品的映射。

## 5. 预留提交凭证接口

**GET /internal/v1/operations/{operation_id}**，相同认证和身份校验，data包裹CommitReceipt，详见operation-receipt.schema.json。本轮未部署。

字段：protocol_version=v1-operation-receipt-1、scope、operation_id、status、committed_at、batch_versions、event_ids、trace_id。只有committed且有可信时间、正整数版本和非空事件引用才算有效提交；processing/rejected不触发成功反馈。凭证和批次都须属于当前用户/家庭，返回操作ID必须匹配。

AI重读所有目标批次；低于提交版本时提示待刷新，高于该版本时标明后续已有变化。预测快照也必须不早于该次提交且覆盖目标提交版本，否则不返回旧预测。后续计算失败保留已提交事实，不建议重发确认。

## 6. 不可用与实施边界

规划模块缺失：PLANNING_CONTEXT_UNAVAILABLE；凭证模块缺失：OPERATION_CONTEXT_UNAVAILABLE。格式不符分别返回PLANNING_CONTRACT_INVALID/OPERATION_CONTRACT_INVALID；过期、权限、版本问题用明确原因，不自动切换到假库存。

两份GET契约可由后端独立业务工具实现，现有数据库任务网关无需改动。AI不实现确认事务、数据库迁移、采购写入或逆向事件；已有库存PATCH/adjustments不能冒充Consumed事件。规划依据随任务结果保留，后端确认时必须取出并重新验证，不只读取简化草稿命令。
