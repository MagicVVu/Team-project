# 后端与 AI 线上对接检查

检查日期：2026-10-25，北京时间。通过 `ssh magicvvu` 检查实际运行容器、HTTP 健康接口、应用路由与 schema、能力声明、数据库迁移标识和运行源码。本文以线上 V1-P8.2 为准，不将 P8/P8.1 历史待办直接认定为当前缺陷。

## 结论

基础通信与认证正常，没有发现需要重新配置连接才能使用的断点。双方已有会话、规划事实读取和草稿执行配套实现。仍需双方继续设计和实施的主要内容是：审核风险规则及商品匹配、旧采购来源修正、商品跨批次规划、完整事件账本，以及自动补货确认重验。

本次仅检查并新增本地报告；没有修改服务器配置、部署服务、迁移数据库、调用付费模型或写入业务数据。未执行真实账号的完整任务与确认流程，因此路由、代码及预检通过不代表端到端业务验收完成。

## 线上状态与已对接能力

| 检查 | 结果 |
| --- | --- |
| 后端 | `magicvvu/backend:p82-05fa3203a7cb`，healthy；健康接口维护版本 V1-P8.2 |
| AI | `magicvvu/agent:p82-05fa3203a7cb`，healthy；DeepSeek；维护版本 V1-P8.2 |
| 数据库 | PostgreSQL 17，healthy；迁移 `20261023_0010` |
| P8 只读预检 | 13 项全部通过：双方认证、AI 地址与契约、执行路由、规划路由及数据库结构等 |
| 动作 | ADD/MOVE/CONSUME/PLAN_ADD/OPEN/DISCARD 六类均开启 |
| 规划读取 | `v1-planning-context-1`；资料接口 `backend-planning-facts-1` |
| 会话记忆 | 双方均声明 `conversation-memory-1`；后端实际调用 AI `/agent/conversation-turn`，校验 AIResolution；沿用已有会话表，无新增迁移需求证据 |
| 草稿与来源 | 可信引用、chat controls、执行预览、全部消费编辑保护已声明支持；PLAN_ADD 执行源码会保存经验证的 `source_inventory_item_id` |
| 业务读取与反馈 | 家庭操作摘要、归档读取、公开操作反馈路由及 AI `/feedback/after-commit` 已存在 |

会话记忆公开接口为 GET `/api/v1/agent/conversation`、POST `/api/v1/agent/conversation/reset`、POST `/api/v1/agent/conversation-turns`、GET `/api/v1/agent/conversation-turns/{request_id}`。双方已具备相应接口和适配代码，本次没有用真实用户调用这些写入会话的接口。

公开后端 OpenAPI 入口未提供路径定义，本次改用运行容器内 `app.openapi()` 检查 schema；AI OpenAPI 可从内部网络读取。未为检查开放任何额外入口。

## 仍需对接和实施的内容

| 优先级 | 内容与线上证据 | 后端工作 | AI/规则侧工作 |
| --- | --- | --- | --- |
| 高 | 风险规则尚未启用：AI health 的 `active_human_rule_count=0`；后端规划批次的 `product_id` 仍为 null | 为需要具体商品适用范围的规则提供稳定商品关联及真实标签/储存资料；现有规划事实入口继续使用 | 完成真实人工审核、来源与适用范围核实及规则发布；零规则时继续保留未知/需审核结果。补齐用户资料不能代替平台规则审核 |
| 高 | 旧采购不能修改/清除来源：线上 ShoppingItemUpdate 仅 name/quantity/unit，禁止额外字段；未关联未购项会使快照 `pending_complete=false` | 给现有 PATCH 增加显式来源修改/清除语义，同家庭、单位、已购限制、并发与幂等校验 | 约定待购完整性影响范围，明确区分未知关联与零待购；不能按同名猜关联 |
| 中 | 商品级跨批次规划缺少身份：`item_key=str(row.id)`，`batches=[batch]`，provenance 为 `inventory_batch_only` | 定义稳定商品、基准单位、显式批次归组及迁移；明确 coverage、盘点和偏好如何聚合及失效 | 依据正式商品映射做聚合，重新验收同名不同商品、多批次和采购入库后的消费预测与补货 |
| 中 | 完整事件账本和纠错未闭环：普通库存记录写入 `history_json` 且仅保留 30 条；规划事件 `related_event_id=None` 并标记当前账本不支持关联 | 普通 CRUD、盘点与购买入库纳入持久事件；设计更正/反向事件、权限、版本与幂等 | 对接事件类型及关联语义；盘点差额不能当消费，没有记录不能推断零消费 |
| 按版本目标 | 自动补货不能直接确认：`automatic_planning_commit=false`、`manual_plan_only=true`；自动建议执行被 `PLANNING_REVALIDATION_UNAVAILABLE` 阻止 | 确认时重新读取并校验库存、事件、偏好、盘点、规则和待购依据，重算并事务落库，保存原建议与人工改动 | 明确建议依据与版本字段、失效原因及重算协议；通过联合验收后再协商开启能力 |

自动补货仍关闭是明确能力边界，本次没有证据表明它是基础连接故障。商品和账本是规划扩展的基础，实施时应先确认模型与契约，再扩展 AI 行为。

## 证据定位（线上容器路径）

- 后端 `/app/app/routers/draft_execution.py:19`：运行能力声明；自动提交关闭，手工采购开启。
- 后端 `/app/app/services/draft_execution.py:130`、`:201`：自动计算 PLAN_ADD 的执行阻断；`:337` 起验证并保存手工采购来源。
- 后端 `/app/app/services/planning_context.py:109` 起：批次身份、空 product_id、单批次 batches；`:165` 起待购来源及完整性；`:197` 自动提交限制。
- 后端 `/app/app/routers/shopping.py:112`：旧采购修改入口；运行 OpenAPI 的 ShoppingItemUpdate 不含来源字段。
- 后端 `/app/app/routers/inventory.py:34`：history_json 最多保留 30 条。
- 后端 `/app/app/services/session_memory.py:235`：向 AI `/agent/conversation-turn` 传可信作用域与服务认证；`:240` 起校验返回结构。
- AI `/app/agent/conversation/memory_schemas.py`：`conversation-memory-1` 的请求上下文与响应定义。
- AI 内部 `/health`：V1-P8.2、规则数为 0；`production_chain_verified` 与 `frontend_integration_verified` 为 false，仅作未验收声明，不单独作为功能故障证据。

## 建议下一步

优先处理规则审核发布和旧采购来源修正；如目标包含“某商品整体还能用多久”与自动补货，再落实商品归组、完整账本和确认重验。已存在的会话记忆、全部消费、手工采购来源及反馈先做专用测试家庭的端到端联合验收，重点验证同名两批、确认前版本变化、超时后沿用原请求恢复以及成功后反馈失败不重复执行。
