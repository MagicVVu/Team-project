# 现有页面对应的 P3 字段与状态

AI 输出始终 inventory_writes=false、shopping_writes=false；生成草稿仍明确“尚未写入”。现有前端页面是展示依据，本轮未修改 Android 或新增页面。

| 现有页面 | AI 字段 | 展示要点 |
|---|---|---|
| 对话面板 | intent / reply / trace_id / original_text | 文字解释来自确定性计算；错误保留输入，可转手动 |
| 商品选择 | item_candidates | 每项 item_key、名称、单位、商品版本及完整批次事实；同名不默认选第一项 |
| 物品详情 | consumption_summary[] | 窗口起止（右侧日期不包含）、完整观察日、有效消耗量、事件数、消费日期数、质量与原因 |
| 物品详情 | forecast[] | 当前登记库存、记录日均消耗、参考剩余天数/日期、条件、策略与统计依据；无合格记录时日期为空 |
| 补货建议 | recommendations[] | 依据 minimum_stock 或 recorded_history、现有量、未购量、目标、新增待购量、原因 |
| 确认表单 | draft / preview / planning_basis | 仅一个 PLAN_ADD，可编辑数量/单位；preview.inventory_changes=false，basis 单独保存供确认校验 |
| 状态/可追溯 | snapshot_id / evaluated_at / risks | 同一读取状态和可信评估时间，P2 风险作为附带依据，不自动扣库存 |

AgentResult 仍只有 answered、needs_clarification、needs_confirmation、unsupported、error 五种状态。

forecast 内部状态：

| 值 | 页面说明 |
|---|---|
| estimated | 最多28完整日的连续有效窗口，至少14日、5有效事件、3消费日期；按已登记速率给条件性日期 |
| insufficient_data | 有效日/事件不足，不提供耗尽日期 |
| no_recorded_consumption | 完整有效窗口没有记录消费，不能解释为实际不消耗；不返回无限天 |
| current_zero | 当前登记库存为零，不制造未来耗尽日 |
| needs_review | 单位、事件关联、记录质量或库存事实有冲突，需要核对 |

窗口实际起点可能因记录缺口缩短，observed_days 是该有效窗口的完整自然日数，不能把无记录日简单补成零。数量与速率按 Decimal 字符串返回；前端可适当格式化显示，但计算和确认依据保留原值。参考日期使用 `库存×观察日/消费总量` 后向上取整，避免先舍入日均速率带来额外一天。

recommendation 内部状态：suggested（有新增建议）、covered（现有库存和已确认待购已覆盖）、insufficient_data（缺明确偏好）、needs_review（未购/可用量等待核实）、excluded（药品采购越界）。只有 suggested 且明确选择单商品的草稿请求才返回 needs_confirmation。

历史建议目标为 `max(最低量, 窗口消费总量×(覆盖日+提前日)/观察日)`。缺合格历史或明确覆盖/提前日时，仅可用已登记最低量降级。新增量 `max(0,目标-登记库存-已确认共享未购量)`；已购条目和未确认草稿不重复扣减。整包装取整需要明确 order_unit/pack_size；超过六位小数或上限时要求核对，不静默截断。

当前对话支持明确的“过去N天/最近N天”（1..28）、“过去两周/最近两周”，未给窗口默认28日；不支持任意日期区间、按周/月分组或更长时间查询。名称须在原文中有依据；“这个/这盒/这批”不能自动扩展为全家查询。只读全家统计/建议可以返回列表，草稿始终一项。

用户修改草稿量后，后端应记录“人工修改量”并保留 original_suggested_quantity，不再把修改值显示为算法原建议。不能把现有页面的本地批量加入逻辑直接视作云端批量执行授权。
