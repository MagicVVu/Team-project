# V1-P9 实施记录

初次交付为可测试的后端候选，开发基点90594f8、分支codex/backend-ai-p9。后续用户已授权推送和生产部署，现已合入dev并部署P9及0011迁移，详见[生产发布记录](backend-ai-p9-production-release.md)。未改AI源码、入口、端口、防火墙或模型配置。以下开发阶段说明保留历史上下文，生产执行结果以发布记录为准。

## 已实现

1. 采购 PATCH 的显式来源设置/替换/清除、字段省略保留；同家庭、生命周期、名称、单位、数量、已购限制。增加内容版本、可选旧客户端兼容及新来源请求的强制版本/幂等字段。持久回执防止延迟重试覆盖新关联。
2. pending_state/pending_count解释三态；来源未知和单位不能换算不能被当成零待购。原后端已有的pending_complete保护保留。
3. 家庭商品Product和显式ProductBatch映射，不按名称归组。保留旧批次主键。资料有来源、操作者、版本和household_attested可信状态；用户标签不等于审核规则。
4. 商品聚合在现有规划接口provenance扩展提供，批次数量、状态、位置、期限、打开状态、盘点和资料版本保留。基准单位合法换算，不兼容时汇总null；过期和终态批次不计入nonexpired_active_quantity。
5. 采购完成在同事务中继承来源商品映射、新建批次和Purchased事件，保留采购来源外键。无来源数据保持未知。
6. 复用BusinessEvent覆盖普通创建、编辑、调整、软归档、盘点、采购及商品关联；新增库存更正与原事件关联，保存原事件，不删除history_json。普通CRUD幂等从最近30条提升为永久回执。事件失败回滚库存和回执。
7. 原AI消费净额算法对Corrected具有特定语义，因此库存更正对旧AI投影为Adjusted。更正会使原事件日期的覆盖证明失效，不把盘点差额解释为消费。
8. 自动建议重验诊断接口，以及原commit入口对新basis的失效拒绝。比较库存、商品、事件、资料偏好/盘点、待购来源和风险版本；校验人工修改内容。原建议仍存在原task/draft，不从客户端接受替换basis。

## 文件与职责

| 源码 | 修改 |
| --- | --- |
| app/shopping_schemas.py、routers/shopping.py | 来源PATCH、版本与回执校验 |
| app/product_models.py、product_schemas.py、routers/products.py | 商品身份、批次映射、审计事件读取 |
| app/models.py、execution_models.py | 注册新表、扩展现有事件 |
| app/services/products.py | 显式聚合、严格单位换算、未知可用量 |
| app/services/ledger.py | 永久幂等、追加事件、冲突回滚和来源验证 |
| app/routers/inventory.py | 普通写入账本、持久重试及更正 |
| app/services/shopping.py | 锁定来源、采购入库映射与事件 |
| app/services/draft_execution.py | 原草稿事件商品关联、新basis重验拒绝 |
| app/services/planning_context.py、planning_facts.py | 现有快照兼容扩展、事件来源、盘点事件、覆盖失效 |
| app/routers/ai_inventory.py | 内部批次读取返回显式商品ID |
| app/services/planning_revalidation.py、routers/draft_execution.py | 只读重验和确认入口 |
| app/main.py | 注册商品与账本路由 |
| alembic/versions/20261026_0011_products_ledger.py | 增量迁移及保护性回退 |
| tests/test_p9_integration.py | 新验收与PostgreSQL并发 |
| 既有相关测试 | 新事件覆盖预期、当前候选契约、迁移必须先于当前应用运行 |
| tools/p9_baseline.py、p9_export_contract.py | 脱敏线上基线、候选OpenAPI导出 |
| tools/p9_http_probe.py、p72_local_postgres_tests.py | 双HTTP服务、隔离PostgreSQL与清理证据 |

上述app路径均相对backend/server；完整变更以本分支git diff为准。

## 数据结构与迁移

候选迁移0010→`20261026_0011`：新增products、product_batches、mutation_receipts；business_events增加request_id、related_event_id、product_id和created_at，operation_id允许空以支持普通业务API。原DraftOperation/DraftDecision表不变；原六类事件数量约束继续生效。

旧事件created_at仅由对应已持久DraftOperation.committed_at回填，没有从模糊history_json推断语义。历史库存无商品映射，不自动迁移或合并。旧batch UUID和采购来源不变。

存在任何P9商品/回执/新事件时，downgrade拒绝删除审计证据。不能强行删除新列/新表或清空业务数据。空库往返与带旧执行回执往返已在隔离库验证；后续生产0011迁移已执行且旧字段哈希一致。出现P9新业务证据后，旧版规划读取器不兼容这些普通账本事件，因此不能无条件回退P8.2镜像，需保留数据并修复或前向发布，详见生产记录。

## 生产操作计划（后续已获授权并执行，详见发布记录）

1. 负责人复核候选提交与实际生产镜像。核对Git源码/构建摘要，生产没有Git元数据，禁止直接改容器文件。
2. 经授权后制作受保护的完整pg_dump自定义格式备份（含schema/data、所需角色/权限和迁移版本），校验摘要与权限；在独立恢复环境演练restore及关键表计数/原回执恢复。备份不得进入普通Git或聊天输出。
3. 核实数据库大小、备份恢复耗时、锁等待与维护窗口。0011修改现有事件约束及可空属性，会涉及表锁；不可直接当作零风险在线DDL。设置受控锁/语句超时，失败整体回滚。
4. 使用现有受控发布流程构建候选镜像。先迁移、后启动新应用；本轮不提供直接替换正式容器的快捷脚本。保留P8.2镜像与Compose配置备份。
5. 部署后执行只读健康与契约检查。旧P8预检硬编码migration=0010，P9部署后应升级其允许版本检查，不能篡改数据库版本让旧预检显示PASS。
6. 在明确授权的专用生产测试家庭做最少量真实DeepSeek端到端验收；失败仅回退应用，保留账本证据。若需恢复整库会覆盖新业务写入，必须另行授权并安排停写窗口。

初次交付时没有生产备份或迁移授权；后续已完成完整备份恢复演练、旧字段一致性校验和受控生产发布。专用生产家庭写入及付费DeepSeek验收仍等待单独明确授权。

## 仍未完成的边界

- AI未消费product_aggregates_v1或新的重验basis；当前AI仍使用批次规划。真实平台规则审核注册表与同步/撤销待AI负责人实现。
- 自动建议的事务重算和自动采购提交未启用、未完成联合闭环。现有手工提交已保留，自动提交固定false/manual_plan_only=true，没有可以通过环境变量单独开启的入口。
- 商品级消费覆盖、可用量和商品偏好仍为未知/不聚合。不能在缺完整覆盖、盘点和风险审核时捏造消费天数。
- 当前更正只恢复/修正ACTIVE或FINISHED批次的盘点数量；不提供终态撤销或原消费量替换。AI需按关联关系提出复核，覆盖证明失效后不得沿用旧消费结论。
- 新Product目录当前为追加身份与显式映射，未提供商品资料编辑、包装密度换算、条码平台目录或自动识别可信发布。
- 既有PLAN_ADD操作没有库存版本，原库存反馈接口返回not_applicable；采购建议执行结果面向AI的单独反馈适配仍待双方确认。不能宣称该库存反馈接口已为手工采购发送库存反馈。
- 没有做生产写入验收、付费模型验收或断电持久性测试。临时PG为加速独占测试关闭fsync等磁盘同步；只用于事务/并发/迁移验证，生产配置未变。
