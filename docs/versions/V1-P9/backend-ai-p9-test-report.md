# V1-P9 测试报告

日期：2026-10-26，Asia/Shanghai。以下完整回归来自开发候选；后续用户已授权并完成P9生产部署及0011迁移，新增16/16生产只读预检通过，见[生产发布记录](backend-ai-p9-production-release.md)。目前所有验收业务写入仍仅在临时数据库的合成家庭执行，付费模型调用0次；生产专用家庭验收待单独授权。

## 最终执行结果

| 环境 | PASS | FAIL/ERROR | BLOCKED/SKIP | 证据 |
| --- | ---: | ---: | ---: | --- |
| SQLite | 420 | 0 | 39 | backend-sqlite.xml |
| PostgreSQL | 443 | 0 | 16 | backend-p9-postgres-tests.xml |
| AI locked runtime | 269 | 0 | 0 | agent-pinned-regression.xml |

证据目录：[reports/backend-ai-p9](../../../reports/backend-ai-p9)。逐个测试名称、功能模块、环境、预期、实际、状态及JUnit定位见[test-index.json](../../../reports/backend-ai-p9/test-index.json)。跳过项没有标为PASS：SQLite的23个行锁用例由PG执行；双方仍有16个公网Nginx用例因未指定P8_NGINX_EXE跳过，本轮不改公网入口。

## 关键场景与证据

以下表格中的“本地HTTP”指真实套接字上的后端和原有Agent进程，连接临时PG；“双库”指真实认证的TestClient/ASGI和隔离数据库。RuleEngine是项目已有实现，不是手写伪造AI返回。

| 测试名称/功能 | 环境 | 预期 | 实际结果 | 状态 | 证据定位 |
| --- | --- | --- | --- | --- | --- |
| P8只读预检及最终线上状态 | 正式服务器，只读SSH | 13项通过，无业务写入 | 均通过；仍P8.2/0010 | PASS | production-baseline.json、production-final-check.json |
| 来源设置/替换/清空/省略、旧PATCH | 双库 | 显式三义，旧客户端可用 | 断言通过 | PASS | test_source_set_replace_clear_omit_replay_and_old_client |
| 跨家庭/不存在来源、已购、非法数量/单位 | 双库 | 404/409/422且不修改 | 断言通过 | PASS | test_source_validation、原shopping校验用例 |
| 来源过期版本与延迟重试 | 双库 | 拒绝过期；旧回执不覆盖新关联 | 断言通过 | PASS | test_source_set_replace_clear_omit_replay_and_old_client |
| 两机同时修正来源/同请求并发 | PG | 不同请求仅一次成功，同请求同回执 | 断言通过 | PASS | test_parallel_source_updates_and_same_request[False/True] |
| 无待购/未知来源/完整来源 | 双库 | none/association_unknown/linked_complete | 断言通过，未知不当零 | PASS | test_pending_three_states_and_product_identity |
| 商品同批聚合/同名不合并 | 双库 | 5+3=8，或两个独立商品 | 断言通过，保留批次 | PASS | test_product_aggregation_scenarios[same/homonym] |
| 合法/非法单位聚合 | 双库 | 500g+2kg=2500g；盒与g汇总null | 断言通过 | PASS | test_product_aggregation_scenarios[convertible/incompatible] |
| 过期批次排除 | 双库 | 总量8、未过期ACTIVE量5，可用量未知 | 断言通过 | PASS | test_product_aggregation_scenarios[expired] |
| 采购完成商品/批次/来源关联 | 双库 | 新批次继承商品，重复购买不再入库 | 断言通过，Purchased事件1条 | PASS | test_purchase_preserves_mapping_provenance_and_one_event |
| 永久账本/旧UI30条/重试 | 双库 | 33次调整全部保留，首请求不重扣 | 断言通过，history仍最多30条 | PASS | test_ledger_retention_replay_correction_and_family_scope |
| 事件失败与库存事务回滚 | 双库 | 库存、事件、回执均回滚，原ID可重试 | 断言通过 | PASS | test_event_failure_rolls_back_inventory_and_retry |
| 更正关联/不伪造消费/原日期覆盖失效 | 双库 | 原事件保留，更正非消费，旧日期需复核 | 断言通过 | PASS | test_correction_invalidates_original_consumption_day |
| 空库迁移往返与结构一致性 | PG | head→0010→head→0009→head；alembic check无差异 | 各步骤exit0 | PASS | backend-p9-postgres-evidence.json:migration/schema_check |
| 带数据迁移和保护性回退 | 双库/PG | 原回执保留，新证据不得删除 | 断言通过 | PASS | 原迁移保留用例、test_p9_downgrade_preserves_new_evidence |
| 自动建议逐维重验 | 双库 | 库存/事件/偏好盘点/商品/待购/规则过期均拒绝 | 断言通过，未建采购 | PASS | test_revalidation_compares_every_basis_dimension（7维） |
| 人工改量及未知规则阻断 | 双库 | 保留原建议与有效请求；未知规则不可执行 | 断言通过 | PASS | test_revalidation_stale_edits_unknown_rules_and_commit_disabled |
| 六类操作完整流程 | 本地HTTP+PG+Agent | AI解析→草稿→确认→持久化→回执/反馈 | 六类均通过，重复提交同回执 | PASS | http-e2e.json:chains |
| 会话记忆/重试/恢复/重开 | 本地HTTP+PG+Agent | 原request恢复，历史会话可读 | 通过 | PASS | http-e2e.json:session |
| 已提交后AI服务不可用 | 本地HTTP+PG | 反馈不可用，业务不重执行 | 停止真实Agent后原回执恢复 | PASS | http-e2e.json:ai_unavailable_after_commit |
| 超时/无效AI响应/草稿过期/权限隔离 | 双库既有用例 | 明确错误，重试与恢复不重复业务 | 回归通过 | PASS | 原session_memory/v09_execution/local_chain_repairs测试 |
| 平台风险规则真实审核发布 | 未执行 | AI负责人核实并发布 | 规则数仍0，不能后端伪造 | BLOCKED | contract/handoff |
| AI商品级算法与新basis返回 | 未实施AI改动 | 按显式商品读取并通过新协议 | 后端有事实，AI待适配 | BLOCKED | handoff |
| 自动建议事务重算并提交 | 未启用/未完成联合闭环 | 批准后才可提交 | 固定false/manual_plan_only=true | BLOCKED | capabilities、重验测试 |
| 生产完整备份恢复/迁移/部署 | 用户授权，正式服务器 | 恢复演练、事务迁移、旧数据一致性与健康通过 | 已部署P9/0011，16项只读预检通过 | PASS | production-release-*.json、生产发布记录 |
| 生产专用家庭写入/DeepSeek验收 | 单独授权待定 | 专用家庭及最多1次模型调用 | 未执行，未产生测试业务数据或费用 | BLOCKED | 自动审批拒绝及待授权记录 |

PLAN_ADD的原库存反馈接口返回not_applicable，真实HTTP测试验证的是这项既有边界，没有把它标成AI已收到库存反馈。采购专用反馈仍待双方适配。

## 失败、修复和执行限制

- 基线392通过/37跳过/2失败：历史OpenAPI与本地Pydantic2.14.1的Decimal schema差异。P9导出测试改为核对候选契约，历史文件不改。
- first-focused.xml记录SQLite增量约束迁移失败，以及新账本/不兼容单位导致旧预期不符；已采用batch迁移并更新与业务变化对应的断言。
- backend-sqlite-initial.xml记录旧迁移测试错误使用当前应用操作旧结构；修正为先在匹配结构生成回执，再验证安全往返和SQLite保护。
- postgres-initial-timeout.json保留首轮300秒超时。临时集群检查点延迟停止后已单独验证停止并清理。最终集群在finally正常停止/清理。
- http-e2e-initial.json保留旧任务与当前会话绑定不一致导致409；网络验收使用对应任务澄清接口后，六类链路和独立会话链路通过。
- postgres-flags-initial.*保留网络烟测开关泄漏到默认关闭用例的7次失败。烟测环境和单元测试默认开关分开，未更改产品认证或业务校验。
- agent-regression.xml在后端运行环境出现5个历史schema差异失败；使用AI锁定依赖Pydantic2.12.5/FastAPI0.135.1后269项全通过，未修改AI代码或伪造快照。
- 临时PG17.11独占本机随机端口，认证和家庭权限未关闭。为加速大量独立schema测试，仅该临时集群关闭磁盘同步；不能把结果解释为断电/硬盘故障恢复验证。生产PG17配置未改。
- 未验证真实付费DeepSeek语义、生产写入链路、公网网关或自动补货正式提交；这些不能标为PASS。

## 复核命令

```text
.venv/Scripts/python.exe tools/p9_baseline.py
.venv/Scripts/python.exe tools/p9_export_contract.py
.venv/Scripts/python.exe -m pytest backend/server/tests -q --basetemp=.cache/p9-release-sqlite-tmp --junitxml=reports/backend-ai-p9/backend-sqlite.xml
.venv/Scripts/python.exe tools/p72_local_postgres_tests.py --stage p9
# 在agent目录，使用其已锁定依赖环境：
../.cache/p2-agent-venv/Scripts/python.exe -m pytest tests/test_session_memory.py tests/test_p3.py tests/test_v1.py tests/test_local_chain_repairs.py -q
```

上述PG工具有独占目录、随机端口与data_directory断言，禁止替换为生产地址。正式部署仍需用户第十一节规定的明确授权。
