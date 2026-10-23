# MagicVVu 后端 P1 集成修复与验收报告

日期：2026-10-23（Asia/Shanghai）。实际 Git 工程：`D:/project/Team_Project_Shared/Team-project`，起始提交 `124abd3`。本次修改仅在本地，**没有部署到正式服务**。

## 1. 结论及验收范围

已修复后端、测试及隔离测试工具中的冲突。四类已开放动作通过实际仓库 P7 服务、后端 HTTP 网关、持久化任务/草稿、人工确认和真实业务表/事件/回执的隔离集成验证。执行服务继续复用既有 `draft_execution`，没有建立新任务系统或 Mock AI 服务，没有修改 Android 或 AI 算法。

本轮实际启动了本地 PostgreSQL 17.11 和 Uvicorn，验证迁移、应用导入、health/ready、事务、行锁、幂等和恢复。最终结果及每项用例见下文 XML/JSON 证据。线上只做只读核查；没有在线创建账号、家庭、库存、采购项目或付费模型调用，因此**不宣称修复后代码已在线验收**。

## 2. 已核实的基线

只读执行 `docker ps`、容器内 health、能力函数、指定源码哈希及 `SELECT version_num FROM alembic_version`。可复现命令：

```powershell
.\.venv\Scripts\python.exe tools/backend_p1_runtime_audit.py
```

结果 exit 0。证据：[backend-p1-runtime-evidence.json](backend-p1-runtime-evidence.json)。该工具只使用既有 SSH alias `magicvvu`，严格校验已知主机，不读取环境变量或业务用户数据。

| 项目 | 本轮只读核实结果 |
|---|---|
| 正式后端 | 0.9.0，`magicvvu/backend:households-20261022`，healthy |
| 正式 AI | `magicvvu/agent:p74-6630097c1f56`，healthy，engine=deepseek，release=V1-P7，inventory_writes=false |
| 正式数据库 | PostgreSQL 17 镜像，healthy；Alembic=`20261017_0007` |
| 开放动作 | ADD / MOVE / PLAN_ADD / CONSUME=true |
| 未开放能力 | OPEN / DISCARD=false；automatic_planning_commit=false；trusted_reference_messages=false |
| 本地迁移 | 0001 至 0007 单链；不存在交接旧分支中的 0008 文件 |

家庭路由、库存路由、执行服务、执行模型本地与容器源码哈希一致。认证三文件存在**本次开始前已有**的差异：本地增加登录限流、未知/禁用用户等成本密码校验及 `Cache-Control: no-store`；本地 `LoginRequest.password` 上限为 128，线上未设此上限。本轮保留本地最新代码，未覆盖这三文件。双方注册规则均为 8–16 位 ASCII 字母数字且必须同时包含两类；现有密码/登录/注销回归通过。部署前需评估既有超过 128 位登录密码的兼容策略，未查询实际密码或用户密码分布。

外层 `D:/project/Team_Project_Shared/.git` 显示大量原有删除及嵌套目录未跟踪；内层实际工程起始工作区干净，但冲突标记已被提交为普通文件内容，`git status` 本身无法发现。没有恢复、清理或暂存外层变更，没有创建提交。

## 3. 冲突分析与修改文件

完整扫描：[backend-p1-conflict-inventory.json](backend-p1-conflict-inventory.json)。初始 HEAD 共 96 行冲突标记；修复后后端及本轮测试工具无冲突标记，仍有 27 行位于下述未处理文件。

| 文件 | 冲突意图与本次处理 |
|---|---|
| `backend/server/app/execution_schemas.py` | 嵌套 HEAD/parent/stash 混合了可信引用选择器及预留协议；保留单一定义、原文空白及 request_id 校验。预留路由继续 503，不开放可信引用。四字段消息模型未变。 |
| `backend/server/app/routers/agent_gateway.py` | 一方加入完整可信引用适配器，另一方维持未开放基线。实际路由和线上能力均未开放，因此移除未挂载适配实现，保留既有预留入口。其余数据库消息/澄清链保留并修复恢复、并发及落库鉴权，见第 4 节。 |
| `backend/server/app/services/planning_context.py` | 一方把事件发生时间当记录时间并把 minimum_quantity=0 作为真实偏好；另一方使用操作提交时间并对未配置阈值返回 null。选择真实 `DraftOperation.committed_at` 及未知阈值 null；不伪造消费覆盖或偏好。 |
| `backend/server/tests/test_v09_execution.py` | 保留有 DB 名、随机端口、data_directory 校验的本地 PG 隔离支持；可信引用断言改为与部署基线一致的 503/false，保留四动作、事务和并发测试。 |
| `backend/server/tests/test_p72_execution.py` | 原文件要求未开放 OPEN/DISCARD 成功，和真实执行服务及数据库约束相矛盾。改为验证能力关闭、执行拒绝且无业务写入，未实现这些动作。 |
| `backend/server/tests/test_p72_reference.py` | 原文件要求未开放可信引用成功；改为验证认证、503、无上游调用及无任务/草稿写入。 |
| `tools/p72_local_postgres_tests.py` | 两套重复脚本存在冲突，保留可验证本轮独立集群的实现；演练 head→0006→head，增加迁移后实际 Uvicorn 启动、JUnit、本轮独立证据文件和测试失败退出码。 |

新增文件：

- `backend/server/tests/test_backend_p1_integration.py`：四动作真实 P7 集成、关联持久化、澄清与超时恢复、响应失败、移除成员、版本冲突、自动规划拒绝、事件快照、过期上下文、旧 worker 防覆盖、重复路由/协议检查。
- `tools/backend_p1_prepare_postgres.py`：复用仓库历史中的 EDB 17.11 便携运行时下载器；固定 SHA256、路径防穿越，仅写本地 `.cache`，不安装系统服务。
- `tools/backend_p1_runtime_audit.py`：脱敏只读基线核验工具。
- 本报告及 `backend-p1-*` 测试/运行证据文件。

保留的冲突：`agent/eval/pricing.json` 以及 `reports/p72/` 下 P0–P5 六份报告和 `evidence/P1-public-checks.json`、`evidence/P6-android-unit-summary.json`。前者两侧涉及计费核验日期/有效性策略，超出本轮后端修复范围；后者是相互矛盾的历史验收证据，不能凭本轮测试改写成历史 PASS。详见完整扫描的路径及行号。本轮没有把这些内容作为已验证证据。**本地 DeepSeek 计费路径仍受 pricing.json 无效 JSON 阻塞**；规则引擎集成不读取该文件，线上 Agent 健康也不等于本地计费配置正确。

## 4. 消息、任务及执行链路

| 公开 API | 实际实现及本轮证据 |
|---|---|
| `POST /api/v1/agent/messages` | Bearer 身份与成员校验；按 user/household/request_id 唯一持久化 AITask 和文本指纹；调用内部 `/agent/message`；四字段 `household_id/text/request_id/household_timezone` 不变。 |
| `POST /api/v1/agent/clarifications/{task_id}` | 同一任务继续；校验所有者、成员、revision、TTL、当前允许字段及九字段白名单；从数据库恢复内部 context，经 `/agent/clarification` 调用，客户端不能提交可信 context。 |
| `GET /api/v1/agent/tasks/{task_id}` | 重新鉴权并读持久化状态、revision、draft_id；公开澄清不暴露内部 scope/context。 |
| `GET /api/v1/drafts/{draft_id}` | 所有者及成员校验；提供原草稿及预览，保持既有 prospective 语义。 |
| `POST /api/v1/drafts/{draft_id}/commit` | 使用客户端稳定 UUID operation_id；锁 task→draft→membership→业务行，检查修订、来源一致性、TTL、可编辑字段、目标及预期版本。单事务写业务数据、operation、event、decision。 |
| `POST /api/v1/drafts/{draft_id}/cancel` | 同一决策表记录取消；重复取消幂等，确认与取消互斥。 |
| `GET /api/v1/drafts/{draft_id}/execution` | 权威执行状态及真实回执；AI 的 needs_confirmation 不充当执行成功证明。 |
| `GET /api/v1/operations/{operation_id}` | 按原操作 ID 恢复持久化回执，重新校验所有者及当前家庭成员资格。 |
| `GET /api/v1/agent/execution-capabilities` | 四动作开放，自动规划及 OPEN/DISCARD/可信引用仍关闭；有登录校验。 |

AITask 的唯一约束、AIDraft.task_id 唯一关联、revision、DraftOperation.draft_id/task_revision/draft_revision 和 receipt 内 task_id 构成原有持久化关联。没有新增数据库表或内存任务注册表。测试实查 request_id→task_id→draft_id→operation_id→event_id 及版本。

本轮网关实际修复：

1. 结果保存和异常恢复均锁定任务并刷新 ORM 状态，持锁校验 nonce；迟到 worker 不能覆盖已接管任务。
2. AI 返回后再次锁定/校验家庭成员资格；等待期间成员被移除，草稿不能落库。正式业务写入继续由确认服务重新鉴权。
3. AI 网络异常保持可恢复的 processing 状态，清除已结束 worker 的 nonce/lease；相同 request_id 可以重试同一任务，不永久缓存为 terminal error。真实返回的 AI error 仍按原语义保存。
4. 已完成 request_id 的结果恢复先于 AI 配置检查；Agent 暂不可用不阻断既有结果查询。新调用仍必须通过配置校验。
5. 拒绝非法、无时区、已过期的 AI clarification expiry，避免存入不能可靠比较的上下文。

HTTP 超时不表明业务失败；正式提交必须先查原 operation_id 或 task→draft→execution，再以**相同 operation_id 和相同确认内容**恢复。404 也可能来自无权限/家庭移除/查询先于提交，不能证明从未执行。成功后刷新失败只能刷新/查回执；原操作回放不会再执行。

## 5. 四类动作逐项验证

真实集成用例 `test_real_message_clarification_commit_recovery` 参数化 4 项：使用实际 `conversation.app.create_app`、项目 `RuleEngine`、真实 `RemoteReader` 和双方 ASGI 路由。HTTP transport 仅把 agent/backend 两个主机名接到本地 ASGI；没有替换网关业务、库存服务、任务持久化或执行服务，没有付费 DeepSeek 调用。

| 动作 | 输入与澄清 | 确认后实际检查 |
|---|---|---|
| ADD | 买了2包纸巾，补 location | 新建真实库存行，数量 2、位置储物柜；StockAdded 事件；回执对象 ID 与数据库相同。 |
| MOVE | 把牛奶移动，补 to_location | 原批次移至书房，数量仍为 5，版本 1→2，StockMoved 事件；另有多候选 batch_id 澄清的既有真实 P7 测试。 |
| CONSUME | 喝了牛奶，补 quantity/unit | 原批次 5→4、版本 1→2；真实 Consumed 事件数量 1，before/after 差值一致；未借用通用调整接口冒充消费。 |
| PLAN_ADD | 计划买纸巾，补 quantity/unit | 创建共享采购行，数量 2，不直接入库；PlanAdded 事件，回执行 ID 与数据库相同。 |

四项均检查：澄清保持 task_id；确认前库存数量/版本不变、采购和事件/操作数为零；草稿与任务关联真实存储；确认后只有一条操作与一条事件；查询任务、草稿执行及 operation 恢复同一回执；相同确认重放不增加写入；重复消息不再调用 Agent。

PLAN_ADD 自动建议分别用 planning_basis、quantity_source=planning_calculation、intent=SUGGEST_PURCHASE 三种来源标记测试；执行状态 unavailable，确认返回 PLANNING_REVALIDATION_UNAVAILABLE，修改数量也不能绕过。明确用户数量的手动采购添加通过；automatic_planning_commit=false 未更改。

单位、精度、日期、部分/耗尽消费、跨家庭目标、保护字段及库存终态仍运行既有回归，未改变公开字段语义。

## 6. 幂等、冲突、权限和恢复证据

以下名称均为本轮实际执行的 pytest 用例，单项结果在 XML 中可查；最终完整套件零失败。

| 场景 | 自动化证据与断言 |
|---|---|
| 同 key 同内容 | `test_each_action_receipt_and_exact_replay` 四动作返回同一回执，操作/事件各一条。 |
| 同 key 不同内容/草稿/用户 | `test_retry_changed_body_or_different_key_never_reexecutes`、`test_top_level_injection_and_foreign_key_reuse` 明确 409，无重复写入。 |
| 草稿之后版本改变 | `test_version_change_after_draft_never_mutates` MOVE/CONSUME 两项 409 INVENTORY_VERSION_CONFLICT，数量、位置无改变且无事件；另有旧 revision/来源不一致测试。 |
| 提交成功但响应失败 | `test_committed_operation_recovers_after_response_render_failure` 在 commit 完成后让 JSONResponse.render 抛异常，HTTP 500；原 operation 查询与同 key 重试均返回已提交回执，库存只扣一次。 |
| 刷新失败 | 四动作集成中制造后续库存查询 404，仍从任务/执行状态/operation 恢复并回放原操作，事件仍只有一条。 |
| AI 网络超时 | `test_message_timeout_reuses_original_task` 从实际 HTTP transport 抛 ReadTimeout，503 后原 request_id 恢复同一 task_id；不生成新任务或业务写入。 |
| 澄清超时及 worker 退出 | `test_clarification_timeout_and_abandoned_lease_keep_original_task` 保留原 context/revision；有效 lease 拒绝并发，过期 lease 可恢复同一任务。 |
| 404 不能反推未执行 | 响应失败用例先查 operation 为 404，再成功提交但响应失败，后查为 committed；成员移除用例显示查询 404 而账本仍存在。 |
| 家庭退出/移除 | `test_removed_member_cannot_read_or_execute_old_work` pending/committed 两项，任务、草稿、执行、operation、澄清、确认、取消均重新鉴权；数据库中旧回执仍在。覆盖成员关系删除后的安全条件，未在线执行退出/移除。 |
| AI 等待期间移除成员 | `test_membership_removed_while_waiting_for_ai` 第二次成员校验拒绝，未持久化草稿。 |
| 旧 worker 返回 | `test_superseded_worker_cannot_publish_or_restore` 错 nonce 保存返回 409，异常恢复也不能覆盖新 worker。 |
| TTL 后恢复成功回执 | `test_receipt_survives_expiry_and_later_stock_changes` 过期和后续库存变化不影响原回执，不触发二次执行。 |
| 原子回滚 | `test_entire_transaction_rolls_back_on_event_failure` 事件持久化失败时库存、操作、决策一起回滚。 |
| PostgreSQL 并发 | `test_postgres_concurrent_commit`：同 key、不同 key、不同草稿、同 key 跨草稿、确认/取消竞争共 5 项，通过真实 PG 行锁验证，最多一次业务效果。 |
| 消费与规划事实 | 消费事件数量约束、事件前后差值、规划快照真实提交时间及未知 minimum_stock=null 均有自动化断言。 |

## 7. 实际命令、结果及失败记录

除说明外，工作目录均为实际内层工程。Python 3.12.8；后端按 `requirements-dev.txt` 安装，未替换框架。依赖版本见 [backend-p1-environment.json](backend-p1-environment.json)。

| 命令/阶段 | 实际结果 |
|---|---|
| `git status --short` / `git log -3` / `rg` 冲突扫描 | 已完成；三处业务文件、三处测试及一个测试工具有冲突，完整清单另存 JSON。 |
| `python -m venv .venv-p1` | 首次失败：沙箱下 ensurepip 无法完成。改用宿主 pip 的 `--python` 将依赖安装到隔离环境；后移至被忽略的 `.venv`。未修改宿主 Python 依赖。 |
| `python -m pip --python .venv-p1/Scripts/python.exe install -r backend/server/requirements-dev.txt` | 沙箱首次网络失败，获执行权限后成功。 |
| 首次 `pytest backend/server/tests -q --tb=short` 及子集诊断 | 非验收 PASS：默认临时目录不可写，随后本地目录父路径缺失；修复路径后沙箱内 TestClient 回环仍阻塞，停止了本轮遗留测试进程；改用允许本地通信的执行环境。 |
| 修复后四份既有针对性套件 | 53 passed / 5 skipped；尚无 PG 时跳过真实行锁测试。 |
| 新增恢复套件首次运行 | 16 passed / 1 failed：测试仅补数量而真实 P7 仍要求单位；修正为补齐当前 allowed_fields 中的数量/单位，没有修改 AI 算法。 |
| `.\.venv\Scripts\python.exe -m pytest backend/server/tests -q --tb=short --basetemp=.cache/p1-delivery-sqlite --junitxml=reports/backend-p1-sqlite-tests.xml` | **143 passed / 21 skipped / 0 failed / 0 error，exit 0**。21 项=16 项可选 Nginx +5 项 PG 行锁。 |
| `.\.venv\Scripts\python.exe tools/backend_p1_prepare_postgres.py` | exit 0；固定 SHA256 匹配，便携 PG 运行时准备成功，不安装服务。 |
| `.\.venv\Scripts\python.exe tools/p72_local_postgres_tests.py` | **148 passed / 16 skipped / 0 failed / 0 error，exit 0**；真实 PG 17.11，含全部 5 项并发测试。 |
| 脚本内 `python -m alembic upgrade head` → `downgrade 20261016_0006` → `upgrade head` | 全部 exit 0，仅针对本轮新建空数据库；有审计数据时拒绝降级的回归同时通过。 |
| 脚本内 `python -m uvicorn app.main:app --host 127.0.0.1 --port <随机端口>` | 实际启动，通过 health(version=0.9.0, isolated_test=true) 和 ready(database=ok)；随后只停止本轮进程。 |
| `.\.venv\Scripts\python.exe -m compileall -q backend/server/app backend/server/tests tools/backend_p1_prepare_postgres.py tools/backend_p1_runtime_audit.py tools/p72_local_postgres_tests.py` | exit 0，导入/启动另由完整测试及实际 Uvicorn 验证。 |
| `git diff --check` | exit 0。路由唯一性、四字段/九字段白名单检查通过。 |
| `tools/backend_p1_runtime_audit.py` | 首次本地 GBK 解码失败；显式 UTF-8 后 exit 0，最终证据已生成。早先沙箱 SSH 网络拒绝后使用只读授权执行成功。 |
| Docker 镜像构建、公网认证写入、真实 DeepSeek 推理 | **未执行/未验证**：本地没有 Docker CLI；没有调用正式写接口或付费模型。不能以 compileall 或 ASGI 测试冒充镜像构建/线上联调。 |

完整结果：[SQLite JUnit](backend-p1-sqlite-tests.xml)、[PostgreSQL JUnit](backend-p1-postgres-tests.xml)、[PostgreSQL 日志及迁移/启动/清理证据](backend-p1-postgres-evidence.json)。14 条警告来自既有 Starlette/AnyIO 和 Alembic 配置弃用提示，无测试失败。

PG 实例使用 `.cache/p72-local-postgres-<本轮随机目录>`、随机 loopback 端口、独立测试库、随机凭据。测试创建 schema 前还检查 DB 名和 `SHOW data_directory`。结束后 `postgres_stopped=true`、`cluster_removed=true`。没有使用正式数据库、已有 Docker Volume 或长期测试库。凭据不进入本报告或证据。

## 8. 状态区分、剩余缺口与 P2 准备

| 状态 | 范围 |
|---|---|
| 已实现（既有） | 四动作正式业务执行、数据库任务/草稿、稳定操作 ID、事件和决策/回执；本次保留。 |
| 本轮已实现、未部署 | 冲突修复、网关超时恢复与结果落库锁/复查、严格 expiry、隔离测试与证据工具。 |
| 已部署、只读核实 | 基线镜像、0.9.0、0007、健康、四动作能力；不是本轮补丁在线运行证明。 |
| 本轮已验证 | 本地规则 P7 实际 HTTP 链、临时 SQLite/PG、并发、权限和恢复、迁移及 Uvicorn。 |
| 尚未验证 | 修复后镜像构建、正式 DeepSeek 解析/网络端到端、真实公网认证执行、Android/UI 恢复流程、可选 Nginx 套件。 |

不需要新增数据库迁移。本轮兼容部署前仍需备份数据库及 Compose/镜像信息；保持 0007 和既有 Volume，应用回滚只切回原镜像，不删除回执、不恢复覆盖正式数据。本地 0007→0006 演练仅验证空库防护，不能用于有审计记录的正式库回滚。正式部署、重启、迁移和切镜像不在本次授权范围内。

P2 可复用的接口已就绪：任务查询、草稿执行查询、operation 查询、能力查询、真实消费事件及只读 planning context；公开四字段/澄清九字段、确认 schema 和 receipt 协议未变。客户端应保存 operation_id，重试保持请求一致，按权威回执恢复，区分已提交和刷新失败。

P2 仍须处理：

1. 解决 Agent pricing.json 的计费策略冲突并验证真实 DeepSeek 链路；本轮未猜测两侧业务意图。
2. 对本地既有认证增强与线上差异做部署兼容评审，特别是超过 128 位旧密码；没有在本轮回退限流或扩大公开字段语义。
3. OPEN/DISCARD 需要完整 schema、事件/约束迁移、日期/终态/版本及并发验收；当前仍明确关闭，不凭残留 P7.2 报告开放。
4. 可信引用需单独审查 source/revision/TTL/成员/候选证明协议；预留路由继续 503。
5. 自动补货仍需完整数据覆盖、偏好和重新校验能力；保持 automatic_planning_commit=false，不能以编辑数量解除限制。
6. 历史 P7.2 报告冲突由相应证据所有者核实；本轮新证据独立保存，不替换历史成功/失败结论。

本地验收支持四动作后端基础执行链安全性；上线验收必须在后续明确授权的发布阶段完成。
