# V1-P9 后端与 AI 契约

状态：后端候选，未部署。实际路由/字段以 [backend-openapi.json](backend-openapi.json) 为准。AI 服务由 MagicVVu 维护，本轮只读审计，未修改其源码。

## 兼容策略

保留 `conversation-memory-1`、`v1-planning-context-1`、`backend-planning-facts-1`。原 `data.items[*].item_key` 继续是批次 UUID，`batches` 仍是该批次；旧 AI 不会被静默切换到商品级算法。已有内部规划接口继续使用服务 Token + X-User-Id + X-Household-Id，并检查活跃用户及家庭成员关系。

兼容扩展放在 `provenance.product_aggregates_v1`、`provenance.revalidation_basis` 等字段。AI 的旧 Reader 丢弃 provenance，因此“后端提供聚合”不等于“当前 AI 已使用商品聚合”。AI 待新增解析适配；禁止直接对旧 `data.items` 的同名记录求和。

## 采购 PATCH

`PATCH /api/v1/households/{household_id}/shopping-list/items/{item_id}`。

```json
{
  "operation_id": "<本次操作UUID，重试沿用>",
  "expected_version": "<GET返回的64位version>",
  "source_inventory_item_id": "<同家庭批次UUID或null>"
}
```

省略 source 字段保留关联；非空 UUID 显式设置；null 清除。任何提交来源字段的请求必须带 operation_id 与 expected_version。只有 name/quantity/unit 的旧请求仍合法；旧客户端采用原有串行更新行为，若需检测过期编辑应升级使用版本字段。版本是内容摘要，不是单调序列号。

数量严格大于0、最多3位小数；单位合法，来源关联后名称和规范化单位必须与该批次一致。跨家庭及不存在的来源统一404 SOURCE_INVENTORY_NOT_FOUND，避免泄露外家庭资源。来源生命周期、名称或单位不匹配为409 SHOPPING_SOURCE_MISMATCH；过期编辑为409 SHOPPING_VERSION_CONFLICT。已购或已入库项目沿用原有409保护。

来源 PATCH 锁住采购项和来源批次。持久回执按 operation_id、家庭、操作者、完整请求摘要隔离；相同请求返回原结果，即使后续关联已变化，也不能恢复旧关联。同 ID 不同内容为409 OPERATION_ID_CONFLICT。数据库唯一冲突回滚后重新做相同权限与摘要检查。

待购三态在规划 provenance：none（存在唯一采购清单、无未购项）；association_unknown（存在未购项，来源未知或单位不能换算，pending_complete=false）；linked_complete（未购项均有有效关联）。清单缺失单独为 shopping_list_missing。pending_count 包含未关联项，不能把 pending 数组为空解释为待购为零。

## 商品与批次

`POST /api/v1/households/{household_id}/products`：客户端 UUID id、name、base_unit、source 必填；specification、category、tags 可选。同名商品可创建不同 UUID，无名称唯一约束。商品是家庭级身份，所有信息标为 household_attested，不能变成平台审核结论。

`PUT /api/v1/households/{household_id}/inventory-items/{batch_id}/product`：operation_id、expected_inventory_version、product_id（必填，可null）、source。仅显式成员确认建立映射；修改/清除都会增加批次 version 并记录 ProductLinked。跨家庭商品404 PRODUCT_NOT_FOUND，版本冲突409 INVENTORY_VERSION_CONFLICT。批次旧 UUID、草稿目标、采购外键不变。

库存规划和库存内部读取的 batch.product_id 提供稳定商品 UUID。现有 planning-facts 的 provenance.product_identity 复用相同来源，未知记录明确 product_id=null。采购入库从锁定的显式来源批次继承商品映射，每次采购新建批次，不合并批次数量。没有来源的手工新库存/AI ADD 继续没有商品关联，需显式确认。

`provenance.product_aggregates_v1` 每项包括 product_id、规格、基准单位、标签及来源、version、identity_status、batches、quantity_complete、total_quantity、nonexpired_active_quantity、usable_quantity、consumption_coverage_days、version_token。

- 合法换算仅相同规范单位、g/kg/吨、ml/L；盒/瓶/包之间不猜测包装换算。
- 任一批次不能换算时，total_quantity和nonexpired_active_quantity为null，原数量/单位与批次详情仍完整保留。
- total_quantity 为所有显式关联批次记录数量；nonexpired_active_quantity仅 ACTIVE 且业务日未过标签日期的数量。未知期限通过expiry_known=false明示。
- usable_quantity始终null，不能把未过标签日期等同已审核安全。无审核风险规则、覆盖天数或有效盘点时，不推算可用量和消费覆盖天数。
- 偏好和完整记录证明仍属于批次，不自动相加或套用到整商品。盘点差异必须保持非消费语义。
- version_token包含商品、映射、批次数量/状态及资料版本，是内容摘要。快照 ID 与筛选无关；跨日期的过期状态变化可使其失效。

## 事件账本 inventory-ledger-1

复用 business_events，扩展普通 CRUD 来源 mutation_receipts；草稿仍使用原 DraftOperation/DraftDecision，不改变幂等链。

`GET /api/v1/households/{household_id}/inventory-events?batch_id=&limit=100&offset=0`，用户 Bearer 认证和家庭隔离，limit最大1000。返回next_offset；分页面向审计展示，不应作为AI一致性快照。AI使用原内部规划快照中的完整事件及provenance。

| 事件 | 语义 | 旧AI投影 |
| --- | --- | --- |
| StockAdded/Created | AI添加/普通创建 | Added |
| StockMoved | 移动位置，数量空 | Moved |
| Consumed | 唯一实际消费事件 | Consumed |
| Opened | 打开，不扣数量 | Opened |
| Discarded | 显式丢弃扣量 | Discarded |
| PlanAdded | 创建手工采购项，无库存变化 | 不进入批次消费事件 |
| Purchased | 采购完成并新建批次 | Purchased |
| Adjusted | 盘点或数量调整，不能认作消费 | Adjusted |
| Edited | 普通资料/数量编辑 | Adjusted（保守） |
| Archived | 普通删除的软归档，保留原数量 | Adjusted（保守） |
| Counted | 与当前库存一致的盘点证明 | 仅provenance，不进入消费事件 |
| ProductLinked | 显式商品身份变更 | Adjusted（保守） |
| Corrected | 有原因与原事件引用的库存更正 | Adjusted，**不是消费替换** |

event_id 为 UUID；household、actor、batch、product、request_id、before/after、occurred_at、created_at、related_event_id、version可追溯。quantity沿用原事件绝对量语义；quantity_delta由before/after计算，换单位或非库存事件为null，不能按缺失delta推断零消费。软归档数量未改变，delta=0但状态不可用。

`POST /inventory-items/{batch_id}/corrections` 需operation_id、expected_version、related_event_id、quantity（明确核对后的数量）、reason。检查原事件家庭和批次；保留原事件，新增更正，调整版本和数量。当前仅允许ACTIVE/FINISHED批次；终态恢复需另行授权业务方案。

库存、回执、事件在同一数据库事务内提交，事件失败整次回滚。回执不受history_json30条限制。保留旧history_json，不把模糊历史迁为消费。覆盖范围为“P9之后普通写入 + 原有草稿持久事件”；history_complete只是完整读取已存账本，不证明现实每天记录完整。

## 风险规则发布交接（AI侧待实施）

由AI规则负责人提供经过审核的规则注册表，至少包含rule_id、version、review_status、reviewer、reviewed_at、source_refs、effective_from/to和scope（product_ids/batch_ids/category）。平台审核权限不能开放给普通家庭资料接口。规则商品匹配必须同时核对商品身份及适用规格，不按同名匹配；类别规则必须明确类别来源和限制。

后端本轮不发布规则，不接受用户输入review_status=approved。当前risk_rules固定unknown/version=null；AI健康规则计数仍真实为零。双方需另行确定经过服务认证的审核注册表同步和版本撤销机制，才能让重验依赖其有效版本。

## 自动补货确认重验 planning-revalidation-1

规划快照provenance.revalidation_basis包含protocol_version、snapshot_id、event_watermark、shopping_version、inventory_versions、facts_versions、product_versions、risk_rules。snapshot_id同时覆盖来源关联、偏好、盘点、商品映射、事件更正及待购内容；这些是摘要，不是客户端可更改的授权。

AI待将原basis原样写入服务端保存的task.result_json.planning_basis，并保存procurement_source={batch_id,expected_version}。用户不能通过确认body替换basis。现有AI严格schema尚未接受这份新basis，必须由AI负责人适配并通过联合契约测试。

`POST /api/v1/drafts/{draft_id}/planning-revalidation` 使用现有PreviewRequest（draft_revision、task_revision、edits）。读取原建议和最新一致快照，比较所有basis字段，重新验证来源，检查待购完整性、盘点存在及24小时新鲜度、消费覆盖未知/差异、商品身份、人工修改字段与数量/单位合法性。返回status=stale或blocked、mismatches、blockers、current_basis、original_suggestion、effective_request、effective_request_hash、user_adjusted，两个写入标记均false。

现有commit入口识别新协议basis后执行同一重验：版本变化返回409 PLANNING_BASIS_STALE并要求重新生成；即使未变化仍409 PLANNING_REVALIDATION_UNAVAILABLE。旧自动建议保持原阻断，手工PLAN_ADD保持原提交路径。重复草稿提交仍优先恢复原operation receipt，不因反馈失败重执行业务。

**自动提交实现未放行。** automatic_planning_commit=false、manual_plan_only=true。本轮只完成可运行的重验诊断和确认入口拒绝逻辑；没有启用自动重算后的采购提交、审核规则同步或自动建议全程保存/提交闭环。未来批准后必须在统一锁与事务中重读、重算、保存原建议/人工修改/执行结果，不能把这次只读诊断结果作为稍后写入的许可。需要双方联合验收与明确版本批准。
