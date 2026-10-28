# MagicVVu 后端 P3 开封与丢弃验收报告

日期：2026-10-23。工作目录：`D:/project/Team_Project_Shared/Team-project`。

本地已实现 OPEN、DISCARD partial、DISCARD all，继续经过原草稿确认事务、操作账本及回执恢复。完整后端 SQLite **244 passed / 35 skipped**，PostgreSQL **263 passed / 16 skipped**，Agent **772 passed**；最终均无失败。尚未部署，正式 OPEN/DISCARD 仍关闭。

## 1. 基线与边界

`git rev-parse --show-toplevel`实际返回上述内层根目录，HEAD=`124abd3`（完善后端家庭功能）。保留 P1/P2 所有未提交成果；未执行 reset、clean、提交、推送或修改外层工作区。P3 开始时，P1/P2 源码、0008、测试与报告已经存在。最终 Git 工作区同时包含三个阶段的未提交成果，不能把全部 diff 当作 P3 新改动。

只读核查时间：`2026-10-23T02:20:11.115460+00:00`。实际正式后端为 0.9.0 / `magicvvu/backend:households-20261022`，Agent 为 DeepSeek V1-P7 / `magicvvu/agent:p74-6630097c1f56`，容器 healthy；数据库版本 `20261017_0007`。正式 capabilities：ADD/MOVE/CONSUME/PLAN_ADD=true，OPEN/DISCARD=false，automatic_planning_commit=false，trusted_reference_messages=false。正式 Agent 没有 `/agent/reply-resolution`。详见 [只读证据](backend-p3-runtime-evidence.json)。P1/P2/P3 均未正式发布。

P3 未修改认证、家庭、Android、AI 理解算法或生产配置。生产与本地认证源文件哈希差异已经存在，沿用 P1/P2 已测试的本地实现；未把本地文件覆盖到运行目录。未访问真实用户库存执行写入测试，未输出密码、模型 Key、内部令牌或连接密钥。

## 2. P3 实际修改

| 文件 | 修改原因 |
| --- | --- |
| `backend/server/app/execution_schemas.py` | OPEN 严格日历日期、DISCARD 显式模式与六位 Decimal、只读预览 DTO、回执文档 Schema。 |
| `backend/server/app/services/draft_execution.py` | 两个独立默认关闭开关；三种新业务分支；共用只读投影；权限、版本、状态、数量、日期校验；真实事件和同事务回执。 |
| `backend/server/app/routers/draft_execution.py` | capabilities 与执行同一开关；新增只读 execution-preview；原 commit/operation 路由声明实际回执 Schema。 |
| `backend/server/app/execution_models.py` | 在现有动作和事件 CHECK 内增加已被 P7/V1 支持的 OPEN/DISCARD、Opened/Discarded；Opened 数量 NULL。 |
| `backend/server/app/shopping_schemas.py` | StockResponse 加上已有数据库字段 opened_at，避免开封事实在返回时丢失。 |
| `backend/server/app/routers/agent_gateway.py` | 持久化最终引用草稿的期限上界；后续澄清响应不能延长后端已保存的任务/引用期限。 |
| `backend/server/alembic/versions/20261023_0009_open_discard.py` | 从 0008 单一 head 追加必要 CHECK 变更；有新审计数据禁止降级；有账本的 SQLite 在 DDL 前拒绝重建。 |
| `backend/server/tests/test_backend_p3_open_discard.py` | 82 个 P3 用例，包含 12 个 PostgreSQL 并发场景，以及真实 P7 HTTP 适配、事务、迁移与恢复。 |
| `tools/p72_local_postgres_tests.py` | 追加 stage=p3 的隔离集群、迁移往返与独立证据路径；保留既有 P1/P2 用法。 |
| `tools/backend_p1_runtime_audit.py` | 允许只读 stage=p3 证据输出。 |
| `tools/backend_p2_export_contract.py` | 允许导出 P3 双方实际 OpenAPI；继续校验所有本地引用。 |
| `tools/backend_p3_write_reports.py` | 从最终 JUnit、真实 JSON 和迁移结果生成三个交付报告；失败时拒绝生成通过结论。 |

原 `planning_context.py` 已映射 Opened/Discarded，P3 核实后直接复用，无需增加不兼容枚举。原 `agent/conversation/reply_adapter.py` 和路由安装保留 P2 改动，P3 未改 AI 算法。未发现新增冲突标记、重复路由或循环导入；原四字段消息、九字段澄清及 P2 五字段续接契约回归通过。

## 3. 三种执行语义

| 动作 | 正式库存变化 | 事件 | 终态与规则 |
| --- | --- | --- | --- |
| OPEN | 仅 opened_at、version+1 及审计历史变化；数量、位置不变 | Opened，quantity=NULL | ACTIVE 且有余量、原 opened_at=NULL 才能开封。已开封的新操作返回 409 ALREADY_OPENED；原 operation_id 同请求仍返回旧回执。 |
| DISCARD partial | 精确扣减换算后的正数量，version+1 | Discarded，真实批次单位/实际扣减量 | 剩余>0 为 ACTIVE，等于0 为 DISCARDED。不会记为 Consumed 或普通调整。 |
| DISCARD all | 行锁内读取当前批次全部余量，归零，version+1 | Discarded，当前真实余量 | 必须与草稿原 expected_version 和精确换算后的原数量同时一致；终态 DISCARDED。数量来源 current_batch，不接收数量/单位/模式编辑。 |

OPEN 原草稿必须有真实 batch_id、name、expected_version、opened_at，无开封数量。只允许编辑 opened_at；有效 ISO 日期且不得晚于可信服务器当前业务日期。编辑“今天/昨天”使用原 task.created_at 与持久化 household_timezone 的 IANA 时区解析，重复预览/提交不会跨午夜改变含义；正常 AI 草稿的相对日期已经由原 P7 链路解析。不合法时区拒绝。日期数字、布尔值、时间戳、非法日期、未来日期均拒绝。

DISCARD partial 仅允许编辑 quantity/unit；显式 discard_mode 不可变。复用现有单位字典及确定性十进制换算，数量最多六位小数，不截断、不四舍五入；单位不可兼容或换算后超精度则拒绝。测试含 500ml→0.5L、最小 0.000001、等于库存、超过库存和吨级换算超精度。

DISCARD all 不从普通数量猜模式。即使版本没有变化、原草稿数量与数据库不一致，也返回 DISCARD_ALL_QUANTITY_CONFLICT，不能扩大丢弃量。只读预览显示 current_batch、变更前后数量/状态、原版本和预计新版本；预览没有库存写入或执行预约效力。

实际 JSON 证据：[PostgreSQL 样例](backend-p3-postgres-examples.json)、[SQLite 样例](backend-p3-sqlite-examples.json)，均为本次合成用户/库存的真实 HTTP 返回，无登录凭证。

## 4. 事务、并发、权限与恢复

沿用 AITask/AIDraft、DraftDecision、DraftOperation、BusinessEvent。锁顺序为 task→draft→家庭成员→库存；业务行、事件、操作账本、最终决策在一个事务中提交。正式确认同时校验 task_revision 与 draft_revision，检查任务/草稿一致性、TTL、当前登录身份和当前家庭成员权限。

同 operation_id 同请求返回已保存 JSON，不再执行；不同 draft/请求/编辑内容返回 OPERATION_ID_CONFLICT。回执恢复在有效家庭权限下可越过已经过去的执行 TTL 和后来关闭的能力开关，不能因此再次写入。退出家庭后的旧草稿和旧回执不能越权读取或提交。

12 个 PostgreSQL 场景 = 三种动作 × 同 key 并发 / 同草稿不同 key / 同批次不同草稿 / 确认与取消竞争。每个场景最多一个操作、一个事件、一次版本变化；同 key 的四个并发请求返回相同结果。

事件故障注入及真实库存 CHECK 失败分别覆盖三种动作，确认库存、开封日期、版本、事件、决策和操作记录全部回滚；解除故障后用原 key 可成功执行。库存约束失败沿用 409 EXECUTION_CONFLICT。

提交后响应序列化失败用来模拟“已提交但客户端未获得成功响应”，三种动作均能从原 operation_id、原草稿 execution 查询恢复真实回执。模拟库存刷新404后重试原 key 不会再写入。没有将超时或查询404当作未执行证据；这不是实际 Android 断网测试。

## 5. P2 多轮与可信引用

真实 P7 应用、原后端 HTTP 网关、reply-resolution 纯解析器和真实隔离数据库共同验证：

- “牛奶开封了”→“昨天”；“扔掉牛奶”→“两盒”；三候选“扔掉剩下的牛奶”→“第二个”，维持原任务后生成草稿，经原 commit 真正执行和恢复。
- 已唯一绑定查询后“它开封了”→“昨天”，以及“扔掉剩下的它”，能指向合法真实批次；没有唯一绑定的“它”不生成可执行目标。
- 结构化续接期间提取次数不增加，样例保留 before/after 计数。确定性规则引擎用于离线夹具，不是新建 Mock AI 服务，也未宣称调用真实 DeepSeek。
- 带引用直接生成确认草稿时，任务 expires_at 不晚于引用 expires_at；后续澄清响应也不能延长原持久化期限。引用过期后即使未满普通15分钟也拒绝确认。历史缺引用期限的确认任务 fail closed。原 P2 来源修订号、会话/家庭/登录绑定与过期测试保留。

## 6. 迁移及现有数据兼容

唯一新 head 为 20261023_0009，父修订 20261023_0008。不增加平行模型、不改库存列、不重写历史事件、不删除 P2 表。库存已有 opened_at/ACTIVE/FINISHED/DISCARDED/REVERSED；不追溯收紧 DISCARDED 与数量关系，避免破坏历史手动操作数据，新 P3 写入由后端保证终态数量0。

PostgreSQL 原生 ALTER CHECK，经真实有 P1 回执/事件/决策与 P2 游标/会话行的数据库验证 0008→0009→0008→0009，所有既有业务行逐字段不变，旧回执原样恢复。写入 Opened 后尝试降级必须报错，revision 仍0009，所有行保持不变，约束均 validated。空库另验证从初始链升级及跨0008/0007/0006往返，完整日志见 [迁移日志](backend-p3-migration-log.txt)。

明确限制：**有执行账本的 SQLite 不支持本次约束表重建迁移**，在任何 DDL 前明确拒绝。专门用外键ON的 SQLite 证明数据、0008版本和 foreign_key_check 全部保留；没有关闭约束。正式数据库是 PostgreSQL，该限制不影响本次 PostgreSQL 发布路径。详见 [迁移与回滚说明](backend-p3-migration-plan.md)。

## 7. 实际运行命令与结果

以下命令工作目录均为仓库根；测试仅使用合成数据或专用临时集群。

| 命令 / 证据 | 实际结果 |
| --- | --- |
| `.venv\Scripts\python.exe tools/backend_p1_runtime_audit.py --stage p3` | exit0；只读核实正式基线，没有执行部署或迁移。 |
| `.venv\Scripts\python.exe -m pytest backend/server/tests -q --tb=short --basetemp=.cache/p3-sqlite-deadline-final --junitxml=reports/backend-p3-sqlite-tests.xml` | **244 passed, 35 skipped, 0 failed/error**；[JUnit](backend-p3-sqlite-tests.xml)。 |
| `.venv\Scripts\python.exe tools/p72_local_postgres_tests.py --stage p3` | **263 passed, 16 skipped, 0 failed/error**；[JUnit](backend-p3-postgres-tests.xml)、[运行/启动/迁移证据](backend-p3-postgres-evidence.json)。 |
| `$env:PYTHONPATH='<仓库根>;<仓库根>/agent'` 后 `.cache\p2-agent-venv\Scripts\python.exe -m pytest agent/tests -q --tb=short --basetemp=.cache/p3-agent-final --junitxml=reports/backend-p3-agent-tests.xml` | **772 passed, 0 failed/error**；[JUnit](backend-p3-agent-tests.xml)。 |
| `.venv\Scripts\python.exe tools/backend_p2_export_contract.py backend --stage p3` | exit0；[实际后端 OpenAPI](backend-p3-backend-openapi.json)，所有本地 $ref 可解析。 |
| `.cache\p2-agent-venv\Scripts\python.exe tools/backend_p2_export_contract.py agent --stage p3` | exit0；[实际 Agent OpenAPI](backend-p3-agent-openapi.json)，所有本地 $ref 可解析。 |
| `git diff --check` | exit0。 |

后端共279个用例。P3 增加82个，SQLite运行70个、12个并发用例只在PG运行。其余197个为既有 P1/P2 与原系统回归：SQLite174通过/23跳过，PG181通过/16跳过。SQLite最终35跳过=19个PG用例+16个可选Nginx用例；PG16跳过均为可选Nginx环境，未标成通过。Agent使用已有锁定依赖环境，Windows有tzdata，未改算法。

真实 Uvicorn 已在本次 PostgreSQL head0009 临时数据库启动，health=ok/version0.9.0/isolated_test=true，ready=ready/database=ok。不是仅 compileall/import；本机无 Docker CLI，**没有执行镜像构建**。临时 PostgreSQL 已停止并仅删除本次新建 data_directory，没有操作既有 volume。

## 8. 失败记录及未验证范围

- 新 P3 初次聚焦：57通过、12跳过、1失败，原因是测试误用旧 p3.schemas 的 PlanningSnapshot；改用实际 v1.schemas 后聚焦65通过/12跳过。见 [首轮XML](backend-p3-first-tests.xml)、[修正后聚焦XML](backend-p3-focused-tests.xml)。后续新增迁移与故障测试纳入最终全量。
- 首次全量 SQLite：240通过/35跳过/3失败；首次 PG：259通过/16跳过/3失败。三项都是新增库存故障注入用例误写预期500，现有接口实际约定409 EXECUTION_CONFLICT。只修正测试预期，并完整重跑，最终验证了原来没跑到的回滚和同key重试断言。[SQLite初次XML](backend-p3-sqlite-initial-tests.xml)、[PG初次XML](backend-p3-postgres-initial-tests.xml)、[PG初次运行证据](backend-p3-postgres-initial-evidence.json)。
- 后续全量曾达到SQLite243/PG262通过；最终复核新增内部续接响应延长引用期限的故障注入测试，实际复现1项失败：[修复前XML](backend-p3-deadline-before-fix-tests.xml)。随后修复save_result，后端以原持久化期限为上限，新响应只能缩短不能续期；新增用例和全部后端再次运行，本文最终数字来自最后一次完整JUnit。
- SQLite有账本迁移明确受限并拒绝，不伪装兼容；PG带数据迁移已验证。
- 第三方 anyio/Starlette、Alembic 配置弃用警告存在，未导致失败；未为消除警告引入框架或升级依赖。
- 未运行可选Nginx集成、Docker构建、真实DeepSeek付费模型、Android真机、生产写入/迁移/灰度。未验证生产负载规模和全库备份恢复耗时；不把离线合成夹具当正式验收。

## 9. 发布状态与团队配合

| 项目 | 已实现 | 本地已验证 | 已部署 |
| --- | --- | --- | --- |
| 三种新操作、预览、真实事件与稳定回执 | 是 | 是 | 否 |
| P1四动作、P2续接/可信引用回归 | 保留 | 是 | 否（P1/P2本地成果） |
| PostgreSQL0009与P2数据兼容 | 是 | 是 | 否 |
| Agent续接适配器 | P2已实现 | 772回归及HTTP联调 | 否 |
| 正式OPEN/DISCARD启用 | 配置能力已具备 | 两开关独立验证 | 否，默认false |

发布前需后端/DB负责人审查0008→0009及备份恢复演练；Agent队友发布P2适配器并确认鉴权和原草稿契约；Android按 [前端交接](backend-p3-frontend-handoff.md) 接入预览、日期和数量来源、稳定operation_id及恢复。运维在另行获准的发布窗口部署和迁移，先保持两个开关false，分别完成联调验收后才决定开启。本文没有授权或执行这些正式操作。

## 10. P4 规划事件准备

数据库已有独立 Opened/Discarded/Consumed 事实，关联真实库存、operation、操作者、家庭、变更前后、精确数量/单位和提交时间。Opened 的业务开封日保存在 after_json.opened_at；occurred_at/recorded_at 仍是实际登记/提交时刻，不把回填日期伪造成精确历史发生时间。

现有 `/internal/v1/ai/planning-context` V1快照能读取三类事实。Opened 在规划 DTO 中数量0，Discarded保留真实扣减量；消费接口及P3历史计算只计Consumed。真实导出经V1 Schema验证，另以**仅测试内合成的完整性/覆盖注解**验证消费净量只为Consumed1，而不是Consumed1+Discarded1；没有将合成覆盖写入业务数据库。

P4仍需真实覆盖天、记录完整性来源、商品目录/跨批次关系、可用库存核验、购物项关联及策略版本等业务数据。当前不伪造 coverage/stock_verification 或历史消费，automatic_planning_commit仍false。P3事件已准备，不能据此宣称自动补货已可正式执行。
