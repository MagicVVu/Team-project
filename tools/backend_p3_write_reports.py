"""Render P3 delivery documents from completed, passing acceptance evidence."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def read(name):
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def counts(name):
    suite = ET.parse(REPORTS / name).getroot().find("testsuite")
    result = {k: int(suite.attrib.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}
    assert result["failures"] == result["errors"] == 0, name
    result["passed"] = result["tests"] - result["skipped"]
    return result


def block(value):
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"


sqlite = counts("backend-p3-sqlite-tests.xml")
pg = counts("backend-p3-postgres-tests.xml")
agent = counts("backend-p3-agent-tests.xml")
runtime = read("backend-p3-runtime-evidence.json")
db = read("backend-p3-postgres-evidence.json")
examples = read("backend-p3-postgres-examples.json")
assert db["exit_code"] == 0 and db["postgres_stopped"] and db["cluster_removed"]
assert examples["populated_migration"]["p2_rows_preserved"]
assert examples["populated_migration"]["populated_downgrade_blocked"]
assert sqlite["tests"] == pg["tests"]

logs = ["PostgreSQL 17.11 disposable cluster; no production writes."]
for step in db["migration"]:
    logs += [f"\nTarget={step['target']} exit={step['exit_code']}", step["log"]]
(REPORTS / "backend-p3-migration-log.txt").write_text("\n".join(logs), encoding="utf-8")

report = f"""# MagicVVu 后端 P3 开封与丢弃验收报告

日期：2026-10-23。工作目录：`D:/project/Team_Project_Shared/Team-project`。

本地已实现 OPEN、DISCARD partial、DISCARD all，继续经过原草稿确认事务、操作账本及回执恢复。完整后端 SQLite **{sqlite['passed']} passed / {sqlite['skipped']} skipped**，PostgreSQL **{pg['passed']} passed / {pg['skipped']} skipped**，Agent **{agent['passed']} passed**；最终均无失败。尚未部署，正式 OPEN/DISCARD 仍关闭。

## 1. 基线与边界

`git rev-parse --show-toplevel`实际返回上述内层根目录，HEAD=`124abd3`（完善后端家庭功能）。保留 P1/P2 所有未提交成果；未执行 reset、clean、提交、推送或修改外层工作区。P3 开始时，P1/P2 源码、0008、测试与报告已经存在。最终 Git 工作区同时包含三个阶段的未提交成果，不能把全部 diff 当作 P3 新改动。

只读核查时间：`{runtime['checked_at_utc']}`。实际正式后端为 0.9.0 / `magicvvu/backend:households-20261022`，Agent 为 DeepSeek V1-P7 / `magicvvu/agent:p74-6630097c1f56`，容器 healthy；数据库版本 `20261017_0007`。正式 capabilities：ADD/MOVE/CONSUME/PLAN_ADD=true，OPEN/DISCARD=false，automatic_planning_commit=false，trusted_reference_messages=false。正式 Agent 没有 `/agent/reply-resolution`。详见 [只读证据](backend-p3-runtime-evidence.json)。P1/P2/P3 均未正式发布。

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
| `backend/server/tests/test_backend_p3_open_discard.py` | {pg['tests'] - 197} 个 P3 用例，包含 12 个 PostgreSQL 并发场景，以及真实 P7 HTTP 适配、事务、迁移与恢复。 |
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
| `.venv\\Scripts\\python.exe tools/backend_p1_runtime_audit.py --stage p3` | exit0；只读核实正式基线，没有执行部署或迁移。 |
| `.venv\\Scripts\\python.exe -m pytest backend/server/tests -q --tb=short --basetemp=.cache/p3-sqlite-deadline-final --junitxml=reports/backend-p3-sqlite-tests.xml` | **{sqlite['passed']} passed, {sqlite['skipped']} skipped, 0 failed/error**；[JUnit](backend-p3-sqlite-tests.xml)。 |
| `.venv\\Scripts\\python.exe tools/p72_local_postgres_tests.py --stage p3` | **{pg['passed']} passed, {pg['skipped']} skipped, 0 failed/error**；[JUnit](backend-p3-postgres-tests.xml)、[运行/启动/迁移证据](backend-p3-postgres-evidence.json)。 |
| `$env:PYTHONPATH='<仓库根>;<仓库根>/agent'` 后 `.cache\\p2-agent-venv\\Scripts\\python.exe -m pytest agent/tests -q --tb=short --basetemp=.cache/p3-agent-final --junitxml=reports/backend-p3-agent-tests.xml` | **{agent['passed']} passed, 0 failed/error**；[JUnit](backend-p3-agent-tests.xml)。 |
| `.venv\\Scripts\\python.exe tools/backend_p2_export_contract.py backend --stage p3` | exit0；[实际后端 OpenAPI](backend-p3-backend-openapi.json)，所有本地 $ref 可解析。 |
| `.cache\\p2-agent-venv\\Scripts\\python.exe tools/backend_p2_export_contract.py agent --stage p3` | exit0；[实际 Agent OpenAPI](backend-p3-agent-openapi.json)，所有本地 $ref 可解析。 |
| `git diff --check` | exit0。 |

后端共{pg['tests']}个用例。P3 增加{pg['tests'] - 197}个，SQLite运行{sqlite['passed'] - 174}个、12个并发用例只在PG运行。其余197个为既有 P1/P2 与原系统回归：SQLite174通过/23跳过，PG181通过/16跳过。SQLite最终35跳过=19个PG用例+16个可选Nginx用例；PG16跳过均为可选Nginx环境，未标成通过。Agent使用已有锁定依赖环境，Windows有tzdata，未改算法。

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
"""
(REPORTS / "backend-p3-open-discard-report.md").write_text(report, encoding="utf-8")

handoff = """# MagicVVu P3 Android 接口交接

2026-10-23，本地已实现并测试，未正式部署。以 [后端实际 OpenAPI](backend-p3-backend-openapi.json) 为准；[完整真实JSON](backend-p3-postgres-examples.json) 来自本次隔离测试合成用户，无真实用户库存或令牌。

## 1. 入口与身份

所有公开接口沿用 `Authorization: Bearer <当前登录令牌>`。先读 `GET /api/v1/agent/execution-capabilities`，仅在对应 actions.OPEN/actions.DISCARD=true 时展示可确认能力。服务端也强制检查。两个开关独立、默认false；正式目前都为false。automatic_planning_commit不变，仍false。

AI入口仍为四字段 `POST /api/v1/agent/messages`、九字段 `POST /api/v1/agent/clarifications/{task_id}`；P2 `POST /api/v1/agent/conversation-messages`、`POST /api/v1/agent/reference-messages` 保留。自然语言续接走P2绑定机制，不能自行从“它”猜批次或注入内部context。AI任务和草稿返回的inventory_written=false只说明AI未写库存；正式执行状态必须查询execution接口。

## 2. 原草稿字段及编辑规则

| 动作 | command_json 必需字段 | edits允许字段 | 数量来源 |
| --- | --- | --- | --- |
| OPEN | action=OPEN,name,batch_id,expected_version,opened_at | opened_at | 无数量，quantity_source=null |
| DISCARD partial | action=DISCARD,name,batch_id,expected_version,discard_mode=partial,quantity,unit | quantity,unit | user_input |
| DISCARD all | action=DISCARD,name,batch_id,expected_version,discard_mode=all,quantity,unit | 无 | current_batch：后端在锁内核实数据库数量 |

真实草稿样例：
"""
for name in ("OPEN", "partial", "all"):
    handoff += f"\n### {name}\n\n" + block(examples[name]["draft"])
handoff += """
action/name/batch_id/expected_version/discard_mode 受保护，切换动作、批次或模式必须重新理解并生成草稿。all的数量和单位也不能放入edits，即使值相同也拒绝。客户端不能把历史查询数量作为权威数据。

opened_at 推荐发送 `YYYY-MM-DD`；不得未来日期，无开封数量输入。服务也支持编辑“今天/昨天”，按原任务可信创建时刻和业务IANA时区解析，推荐先预览显示最终ISO日期。已开封的新操作返回ALREADY_OPENED，不提供在本次接口中改写历史开封日的能力。

数量按字符串Decimal处理，最多六位小数，不能用客户端浮点舍入修正。partial等于余量时也会归零并进入DISCARDED；partial剩余>0保持ACTIVE；all固定归零DISCARDED。Opened不改变数量或位置，只变开封日和版本。

## 3. 可编辑草稿的只读预览

1. `GET /api/v1/drafts/{draft_id}`：已有AI草稿及前瞻说明。
2. `GET /api/v1/drafts/{draft_id}/execution`：真实执行状态、两个revision、editable_fields、expires_at、operation_id和receipt。确认前核对该状态。
3. `POST /api/v1/drafts/{draft_id}/execution-preview`：P3新增**只读**计算，输入两个revision和edits，无operation_id；不修改草稿、不续TTL、不写库存，不是第二套执行API。

实际all预览请求：
""" + block(examples["all"]["preview_request"])
projection = examples["all"]["preview_response"]
display = {k: projection[k] for k in ("draft_id", "task_id", "draft_revision", "task_revision", "command")}
for phase in ("before", "after"):
    display[phase] = {k: projection[phase][k] for k in ("id", "name", "quantity", "unit", "storage_location", "opened_at", "status", "version")}
display.update({k: projection[k] for k in ("event_type", "event_quantity", "quantity_source", "expires_at", "prospective", "inventory_written")})
handoff += "\n实际预览响应字段摘录（完整StockResponse见JSON证据/OpenAPI）：\n\n" + block(display)
handoff += """
OPEN显示before.opened_at和after.opened_at、原/预计version，前后quantity相同；partial/all显示前后数量及终态。before/after是预计状态，预览不会预先写入审计历史；提交后的after会有真实history_json事件。预览与确认之间仍可能发生版本冲突。

## 4. 确认、取消、回执

正式写入继续只用 `POST /api/v1/drafts/{draft_id}/commit`。用户确认前生成并持久保存一个UUID operation_id，保存原draft_id、两个revision和完全相同的edits；同一次操作所有重试均复用这些值。预览不会保存edits，commit必须带同一份edits。

实际all提交请求：
""" + block(examples["all"]["commit_request"])
receipt = examples["all"]["receipt"]
receipt_display = {k: receipt[k] for k in receipt if k not in {"result", "execution"}}
details = receipt["execution"]
receipt_display["execution"] = {k: v for k, v in details.items() if k not in {"before", "after"}}
for phase in ("before", "after"):
    receipt_display["execution"][phase] = {k: details[phase][k] for k in ("id", "name", "quantity", "unit", "status", "version", "opened_at")}
handoff += "\n实际all成功回执字段摘录（省略result及部分StockResponse字段，完整真实回执见JSON）：\n\n" + block(receipt_display)
handoff += """
回执protocol_version仍draft-operation-receipt-1。P3新增可选execution字段，包含before/after、event_type、quantity、unit、discard_mode、quantity_source；旧已存回执不回填、不重写，客户端必须允许execution缺省。result.inventory_item是实际提交后库存；batch_versions/event_ids/trace_id关联真实操作和事件。OPEN的quantity/discard_mode/quantity_source为null、event_type=Opened；两种DISCARD均event_type=Discarded，数量为实际扣减量。

`POST /api/v1/drafts/{draft_id}/cancel` 继续只接受task_revision、draft_revision。取消与确认竞争只有一个最终决策。`GET /api/v1/drafts/{draft_id}/execution` 的status=committed时receipt为真实账本，不要因原AI任务仍needs_confirmation再次生成操作。

## 5. 主要错误

错误的业务码位于 `detail.code`；认证/原网关错误仍可能是原有字符串或FastAPI校验数组，客户端保留通用分支。

| HTTP | code | 前端行为 |
| --- | --- | --- |
| 422 | INVALID_DRAFT_FIELDS / OPEN_DATE_IN_FUTURE | 更正允许编辑字段并重新预览；不得静默补日期。 |
| 422 | PROTECTED_OR_UNKNOWN_FIELD | 不修改目标/模式/all数量；重建草稿。 |
| 422 | UNIT_UNSUPPORTED / UNIT_MISMATCH / CONVERTED_QUANTITY_INVALID / INSUFFICIENT_STOCK | 展示数量或单位问题；不得截断舍入。 |
| 409 | INVENTORY_VERSION_CONFLICT / DISCARD_ALL_QUANTITY_CONFLICT | 拒绝旧草稿；重新读取、核对并生成草稿，不把旧expected_version改成新版本。 |
| 409 | DRAFT_REVISION_CONFLICT / DRAFT_SOURCE_CHANGED / DRAFT_NOT_PENDING | 重新获取原任务和草稿状态，不能硬改revision。 |
| 409 | DRAFT_EXPIRED / REFERENCE_EXPIRY_UNAVAILABLE | 重新发起并核对；引用期限和普通TTL均受检查。 |
| 409 | INVENTORY_NOT_ACTIVE / ALREADY_OPENED | 展示现有事实，不能再次丢弃终态或覆写开封日。 |
| 409 | OPERATION_ID_CONFLICT | 原ID对应另一请求，停止修改请求后重试；恢复原请求结果。 |
| 409 | DRAFT_ALREADY_DECIDED / DRAFT_ALREADY_COMMITTED | 查询execution确定最终决策。 |
| 409 | ACTION_NOT_EXECUTABLE | 当前开关关闭；刷新capabilities。已完成回执仍可恢复。 |
| 409 | EXECUTION_CONFLICT | 事务冲突；保留原ID查询，并按相同请求恢复。 |
| 401 / 404 | 当前身份无效 / DRAFT_NOT_FOUND / OPERATION_NOT_FOUND | 复核登录与家庭；404可能来自权限或查询时序，不是从未执行的证明。 |

## 6. 丢响应与刷新失败

提交超时或5xx时显示“结果待核实”，先以原operation_id请求 `GET /api/v1/operations/{operation_id}`，再查原draft的execution。必要时只重发原key/原body。单独一次404不能据此换新key重新扣库存。成功回执应本地保留；之后库存刷新失败只重试读取，不重新执行commit。会话失效/被移除家庭时先恢复合法身份与权限，不能绕过重新鉴权。

Android不得用普通数量调整冒充丢弃，不得删库存记录冒充all，不得改备注冒充开封。前端改造、真机断网测试和实际部署联调尚待Android/Agent/运维队友配合完成。
"""
(REPORTS / "backend-p3-frontend-handoff.md").write_text(handoff, encoding="utf-8")

migration = """# MagicVVu P3 数据库迁移与安全回滚

日期：2026-10-23。只在隔离环境执行过；没有运行正式迁移、重启或切换镜像。

## 1. 依赖与变更范围

实际迁移链单一head：`20261017_0007 → 20261023_0008 → 20261023_0009`。正式只读核实仍为0007，发布P1/P2/P3代码时必须审查并依次应用0008、0009；不得恢复另一条历史0008或创建平行head。

0009文件：`backend/server/alembic/versions/20261023_0009_open_discard.py`。只替换三个命名CHECK：

| 表 / CHECK | 新规则 |
| --- | --- |
| draft_operations / ck_operation_action | 原四动作加OPEN、DISCARD。 |
| business_events / ck_business_event_type | 原四事件加既有P7/V1语义Opened、Discarded。 |
| business_events / ck_business_event_quantity | StockMoved、Opened必须NULL；其他事件包括Discarded必须>0且≤1,000,000,000。 |

PostgreSQL使用原生ALTER TABLE约束操作，不复制或回填业务行。未改库存列、精度、状态CHECK或opened_at，未删表/行、未重写历史JSON、未改P2会话表。SQLite空账本由Alembic batch完成；**有执行账本的SQLite明确拒绝迁移**，因为父表被RESTRICT引用，不能用关闭外键换取重建。拒绝发生在DDL前，保留原revision与数据。这是明确的本地SQLite迁移限制；正式发布目标为PostgreSQL。

不增加“所有历史DISCARDED数量必须为0”的回溯约束，以保留旧手动操作数据。P3新增all及partial扣零由同事务业务逻辑保证数量0/状态DISCARDED；数据库原数量非负及新事件约束仍开启。

## 2. 实际隔离验证

命令：`.venv\\Scripts\\python.exe tools/p72_local_postgres_tests.py --stage p3`。

本工具启动本次新建的PostgreSQL17.11临时目录、随机loopback端口和私有测试密码，无系统服务；测试fixture验证DB名为magicvvu_p7_execution_test和真实data_directory匹配后才写入。测试结束已停止并删除仅本次data目录。

空库流程：upgrade head → downgrade0008 → upgrade head → downgrade0007 → upgrade head → downgrade0006 → upgrade head；全部exit0。真实Uvicorn在迁移后启动，health和ready通过。完整执行日志在 [backend-p3-migration-log.txt](backend-p3-migration-log.txt)，运行及清理证据在 [backend-p3-postgres-evidence.json](backend-p3-postgres-evidence.json)。

带数据流程位于 `test_migration_preserves_ledger_and_p2_and_blocks_unsafe_downgrade`：在独有测试schema迁到0008，实际HTTP执行CONSUME产生旧operation/receipt/event/decision，加入P2绑定和会话行；0008→0009→0008→0009每步逐字段比较所有旧业务行不变，再通过原operation_id恢复原样回执。新OPEN执行后降级0008报RuntimeError，revision仍0009、行不变、PG约束均validated。真实结果保存在 [JSON样例的populated_migration](backend-p3-postgres-examples.json)，最终JUnit中该用例通过。

另用外键ON的SQLite0008账本验证：升级0009在DDL前明确拒绝，旧数据相等、revision仍0008、foreign_key_check为空。未将这个拒绝写成“SQLite带数据升级通过”。

## 3. 正式发布前的审查与备份方案（尚未执行）

1. 后端/DB负责人确认目标确实为获准的正式PostgreSQL实例、当前revision、单一head和P1/P2代码齐全；确认无并行确认写入窗口，评估ALTER锁等待。
2. 在另行获准的维护窗口暂停相关写入。使用受控连接配置运行pg_dump自定义格式全库备份，包含库存、任务、草稿、账本、事件及P2会话；密码通过受控环境或pgpass，不写入命令、报告或Git。备份放在现有Docker Volume之外的受控目录，保留校验和、时间和访问权限。
3. 用pg_restore --list核对归档，并在另一隔离PostgreSQL17实例真实恢复，检查revision、各业务表行数、约束、代表性旧operation_id回执；只有恢复演练成功才继续。正式全库恢复演练本阶段未执行。
4. 审查0008的会话表及降级保护、0009三个CHECK；在发布包的原有Alembic环境执行upgrade head。保持MAGICVVU_OPEN_EXECUTION=false和MAGICVVU_DISCARD_EXECUTION=false；先验证旧四动作、P2适配/鉴权和只读健康。
5. Android及Agent契约联调后，另行获准分动作启用能力并验收，不把测试fixture启用配置带入正式环境。没有新迁移前不可开启写入新事件。

上述为待审批方案，不是已执行的正式步骤；没有删除/重建任何既有Docker Volume或数据库。

## 4. 回滚限制

优先应用回滚：关闭两个能力开关，保留0009以及全部历史事实；已提交操作仍用旧operation_id恢复，旧代码应保持追加字段兼容。回滚到P1/P2版本前需评估其是否能读取新事件，不能把读不懂的新事件伪装成消费或删掉。

`downgrade0008`先检查所有OPEN/DISCARD operation及Opened/Discarded事件。只要存在任一种就报错，**不能删除审计记录来强行降级**。没有新事件时PG可恢复原CHECK，已有原四动作与P2数据保留，已在隔离带数据往返验证。SQLite只要有执行账本则拒绝约束重建。

0008已有P2会话记录时也会阻止危险降级；0007已有执行审计时禁止降级删账本。要回到更早模式，保留数据库结构并回滚应用，或由DB负责人在明确恢复目标/停写/审计批准后执行独立备份恢复流程；本阶段没有执行这样的恢复。

迁移失败时先停止后续发布并查询实际alembic_version和约束状态，不自动换镜像或删除表。PG DDL由迁移事务保护；仍需现场核实锁、连接与实际结果。HTTP超时不等于业务失败，与数据库迁移回滚是不同问题。
"""
(REPORTS / "backend-p3-migration-plan.md").write_text(migration, encoding="utf-8")
print(json.dumps({"sqlite": sqlite, "postgres": pg, "agent": agent, "reports_written": 3}, ensure_ascii=False))
