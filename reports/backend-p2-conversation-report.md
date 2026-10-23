# MagicVVu 后端 P2：多轮续接与可信库存引用验收报告

日期：2026-10-23，Asia/Shanghai。工作工程：`D:/project/Team_Project_Shared/Team-project`。本轮只做本地实现、隔离验证和正式服务只读核查。**尚未部署，不代表 Android 联合验收完成。**

## 1. P1 基线及遗留问题复核

`git rev-parse --show-toplevel` 确认为内层 Team-project；未 reset、清理、暂存或提交外层仓库。P1 的未提交修复和测试均保留。重点复查了 nonce/lease、结果保存锁、成员权限复查、幂等 operation_id、真实 Consumed 事件和单事务执行，没有重建任务网关。

参考实际文件：`reports/backend-p1-integration-report.md`、`docs/versions/V1-P7.3/frontend-backend-handoff.md`、`docs/versions/V1-P7.3/implementation-record.md`、现有 Agent/P1 源码与测试。任务所写 `agent/v1/conversation/replies.py` 实际位于 **`agent/conversation/replies.py`**。`frontend-backend-action-handoff-20261022.md` 在本仓库文件扫描中未找到，未假定其内容；本次交接以可核验源码、P7.3 契约和本轮测试为准。

P1 交付时 SQLite 143 / PostgreSQL 148 通过；P2 的完整后端回归包括这些测试。四类业务动作的执行服务及模型与线上仍一致，本轮未修改 ADD/MOVE/CONSUME/PLAN_ADD 的业务语义。

正式服务只读复核命令：

```powershell
.\.venv\Scripts\python.exe tools/backend_p1_runtime_audit.py --stage p2
```

结果 exit 0，见 [运行基线证据](backend-p2-runtime-evidence.json)：

| 项目 | 当前正式状态 |
|---|---|
| 后端 | 0.9.0，`magicvvu/backend:households-20261022`，healthy |
| AI | `magicvvu/agent:p74-6630097c1f56`，healthy，engine=deepseek，release=V1-P7 |
| 数据库 | PostgreSQL 17 镜像，healthy，Alembic=`20261017_0007` |
| Agent 新内部续接路由 | **未部署**；实际容器 OpenAPI 不含 `/agent/reply-resolution` |
| 正式可信引用能力 | false；OPEN/DISCARD 与自动规划确认仍关闭 |

本地认证三文件与线上差异仍为 P1 已记录的登录限流、等成本校验、no-store 和登录密码 max_length=128（线上无该长度上限）。注册 8–16 位字母数字组合规则一致。**P2 未修改认证规则**，超过 128 位历史登录密码的发布兼容性仍须独立评审。

## 2. P2 修改清单

| 文件 | 本轮改动 |
|---|---|
| `agent/conversation/reply_adapter.py` | 新增内部认证 HTTP 适配器，直接调用既有 `resolve_reply()`；不复制规则、不调用模型、不读库存或存状态。 |
| `agent/conversation/app.py` | 在既有 P7 Profile 安装上述路由；仅增加安装调用，没有修改理解/续接算法。 |
| `agent/eval/pricing.json` | 消除无效 JSON 冲突，逐字段恢复为本轮只读取得的已发布配置；未猜测或更改费率，详见第 12 节。 |
| `backend/server/app/conversation_models.py` | 用户会话游标 ConversationBinding、请求回执 ConversationTurn；不替代 AITask/AIDraft。 |
| `backend/server/app/conversation_schemas.py` | 五字段自然语言适配输入、四结果 Resolution、公开响应 DTO，拒绝额外可信上下文字段。 |
| `backend/server/app/services/conversation.py` | 数据库绑定、请求去重、跨容器续接适配、引用签发/失效、原网关调用、原子回执和并发恢复。 |
| `backend/server/app/routers/conversation.py` | 新增主聊天框适配入口；使用现有身份和数据库依赖。 |
| `backend/server/app/routers/agent_gateway.py` | 抽出可复用的 run_message/run_clarification；save_result 支持同事务保存请求回执；无新 clarification context 的完成结果推进 revision；验证引用来源回显和草稿目标。P1 nonce/行锁/超时恢复继续保留。 |
| `backend/server/app/routers/draft_execution.py` | 正式接通原 reference-messages 路由及响应 DTO；可信引用开关默认 false；执行业务服务未改。 |
| `backend/server/app/models.py`、`app/main.py` | 注册新增模型和公开路由。 |
| `backend/server/alembic/versions/20261023_0008_conversation.py` | 追加迁移，只建两张会话辅助表；有记录时拒绝破坏性 downgrade。 |
| `backend/server/tests/test_backend_p2_conversation.py` | 33 项 P2 场景，含两项真实 PostgreSQL 并发参数；复用 P1 的真实认证、数据库、P7 HTTP 服务和 RemoteReader。 |
| `tools/p72_local_postgres_tests.py` | 增加 `--stage p2`，隔离证据命名，演练 0008/0007/0006 往返；保留启动、停止、目录验证及清理保护。 |
| `tools/backend_p1_runtime_audit.py` | 增加 stage 参数和线上 Agent 路由只读核查，P2 证据独立命名。 |
| `tools/backend_p2_export_contract.py` | 不连接数据库或模型，导出双方实际 OpenAPI 并校验所有本地 `$ref`。 |

P1 仍有未提交文件，因此普通 git diff 同时包含 P1 与 P2。没有回退 P1 修改，没有修改 Android，也没有另建 AI 服务或业务执行框架。

## 3. AI P7.3 续接适配方式

已核实原函数签名：

```python
resolve_reply(binding, text, scope, now, *, selected_batch_id=None)
```

BoundTask 要求 scope、完整公开 Task 和 household_timezone。函数只验证调用方传入绑定内部一致性，不能证明数据库权限，原先也没有 HTTP 接口。后端镜像仅打包 backend/server，不能假定可直接 import Agent 文件。

因此在**现有 Agent 进程**增加 `POST /agent/reply-resolution`：沿用同一服务 Bearer Token 和 X-User-Id/X-Household-Id 身份头，接收后端构造的 binding、原文、可信时间和已选批次，直接返回 ReplyResolution。没有改变 P7.3 自然语言解析算法或旧的 `/agent/message`、`/agent/clarification`。

后端只调用这个已经实际实现的路径；非 200、网络异常或不合法结果映射 `503 REPLY_ADAPTER_UNAVAILABLE`。**不会在缺路由时回退成新消息并触发模型**。线上目前缺路由，所以本地完成不等于线上可用。Agent 队友需要一起审查并发布新增适配文件和两行路由安装；其完整请求/响应见 [内部 OpenAPI](backend-p2-agent-openapi.json) 和 [AI 配合事项](backend-p2-ai-adapter-handoff.md)。

现有 Agent Dockerfile 已 COPY conversation 目录，新模块随现有构建进入镜像，无需共享后端源码、添加包或改模型。镜像实际构建本轮未执行。

## 4. 自然语言续接路由

新增 `POST /api/v1/agent/conversation-messages`，请求只包含家庭、原文、请求 ID，以及可成对提供的 task_id/revision。公开普通消息四字段和原澄清九字段不变；Android 不提交 BoundTask。

| 结果 | 实际处理 |
|---|---|
| clarify | 校验原任务及完整快照，按当前候选顺序解析出的 answers 再校验 allowed_fields；调用原 run_clarification，同一 AITask，原文另存在 ConversationTurn。 |
| needs_input | 保存路由结果/请求回执；不调用提取、不新建任务、不推进 task revision，保留当前引用，不默认选第一批。 |
| new_task | 使用原 run_message 建独立 AITask；新话题立即清活动绑定/引用；合法指代可携带经复核的已有引用读取当前事实。旧 Task/草稿/回执保留。 |
| clear_reference | 清数据库活动游标和引用，保留历史业务数据；不调用模型，不取消旧草稿或撤销操作。 |

为防止快速连发沿用同一修订，澄清生成最终无 context 的结果时将 task revision 推进一版；仍需澄清时继续使用 AI 返回的 context revision。路由 needs_input 和重复 request_id 均不会额外增加修订。Draft revision 与 Task revision 不是同一个数字，确认页继续 GET draft/execution 取两者。

日期回复原样交给原澄清链。P7.3 的辅助检查使用后端提供的带时区时间，最终相对日期仍锚定 AI 已持久化 context.created_at 和原任务 IANA 时区，遵守现有契约。新任务时区由服务端设置，不由新接口的手机请求指定。OPEN 草稿日期可验证，正式 OPEN 执行仍关闭。

## 5. 可信任务绑定

服务端从当前已认证身份、会话和数据库读取所有者、家庭及成员关系、任务状态、最新 revision、allowed_fields、同一修订候选顺序、有效期和原时区，然后构造纯函数需要的公开快照。未把 AI 私有续接 context 返回给 Android。

ConversationBinding 每用户一个活动游标，固定到登录 session_id 和家庭；多窗口/设备不自动合并。切换家庭或登录会话不能携带旧选择器进入新操作。新请求必须带当前 task_id/revision，避免把最后一条历史消息当作可信任务。

候选选择前检查当前 Task 快照未改变，并核对候选批次仍存在且版本一致；变化时返回明确冲突，要求重新核对。引用读取则按身份重新查当前批次，不把历史位置或版本作为当前事实。

结果保存回调在同一数据库事务内再次检查游标 nonce、当前成员关系、登录会话是否撤销/过期及账号是否有效。P1 的 task nonce/lease 和 task→draft→membership→业务行的确认保护继续存在。内部纯解析请求不回调数据库工具，真正的 Agent 消息/澄清调用前释放数据库连接。

## 6. 服务端引用存储与迁移

采用数据库引用存储，不采用客户端可签发的 ObjectReference。响应 reference 只是证据视图；客户端回传的 scope、时间、版本或 reference 均不会成为可信输入。

引用包含来源 Task/最新 revision、已选 batch_id、用户/家庭 scope、服务端 issued_at/expires_at；来源必须是唯一回答或用户明确选择的真实候选/预览对象。batch_id 在当前家庭中再次核实 ACTIVE 且数量大于零。

- TTL 上限 15 分钟，受原任务 expires_at 进一步限制；打开窗口、重放或连续指代查询均不重新签发期限。
- 同一源任务补字段时只推进来源 revision，原 issued_at/expires_at 不变；不能将引用移植到不同新任务。
- 退出/移除成员、跨家庭、登录会话变化、来源修订不符、删除批次、终态或过期均拒绝使用。
- “开始新任务”后不能用独立引用入口重新挂回已清除的旧引用。
- 库存位置/版本变化不使只读身份引用伪造事实；每次经 RemoteReader 读当前数据，最终业务确认仍比较当前 expected_version。
- 确认写入继续走原 commit；引用入口和续接入口都没有库存写入路径。

新迁移为 `20261023_0008`，父节点 `20261017_0007`：

| 表 | 用途 |
|---|---|
| ai_conversation_bindings | 当前用户/登录会话/家庭游标、活动任务和引用、处理 nonce/lease。 |
| ai_conversation_turns | 原始输入、请求指纹、来源快照/修订、路由结果和原子响应回执。唯一键为用户＋家庭＋request_id。 |

这两表记录会话和 HTTP 请求回执；所有实际 AI 任务仍只在 ai_tasks，所有业务草稿仍在 ai_drafts，正式执行仍在原操作账本。

隔离库已演练：空库→head(0008)→0007→head→0006→head；SQLite 另验证已有 P1 草稿保留，存在会话记录时 downgrade 被拒绝。没有在正式库执行迁移。

发布准备：先备份正式数据库和原镜像/Compose 信息，审查新迁移，在隔离恢复副本验证后再按明确授权发布。迁移是追加表，旧应用可以忽略；有记录的 0008 不允许物理降级，应用回滚保留表和证据。不得删除 Volume、恢复覆盖正式数据或为回滚清空回执。

## 7. API、OpenAPI 与样例

| API | 状态/兼容性 |
|---|---|
| POST /api/v1/agent/conversation-messages | 新增 Bearer 认证公开适配入口，原文＋当前可信任务选择器。 |
| POST /api/v1/agent/reference-messages | 原预留入口接通真实实现，默认 feature gate 仍 false/503；输入保留原 DTO，响应为新 ConversationResponse。 |
| POST /api/v1/agent/messages | 原四字段不变，原客户端继续工作。 |
| POST /api/v1/agent/clarifications/{task_id} | 原 revision/answers 和九字段白名单不变，结构化客户端继续工作。 |
| GET /api/v1/agent/execution-capabilities | 四动作不变，trusted_reference_messages 默认 false；仅在独立部署验证后由配置明确启用。 |
| POST /agent/reply-resolution | Agent 内部服务认证，仅后端可调用，不供 Android。 |

具体 JSON、字段含义、去重域、错误码、恢复与新旧客户端方案均在 [前端交接](backend-p2-frontend-handoff.md)。导出命令实际通过：

```powershell
.\.venv\Scripts\python.exe tools/backend_p2_export_contract.py backend
.\.cache\p2-agent-venv\Scripts\python.exe tools/backend_p2_export_contract.py agent
```

产物：[后端 OpenAPI](backend-p2-backend-openapi.json)、[内部 Agent OpenAPI](backend-p2-agent-openapi.json)。两个命令均 exit 0，全部本地 `$ref` 可解析；自动化验证无重复路由、公开 DTO 拒绝内部字段。线上 docs 默认关闭，不因此开启正式文档页面。

## 8. 认证、TTL、revision、幂等与并发证据

所有用例均调用实际 P7 工厂、原数据库网关、RemoteReader 及执行链。测试仅在 HTTP transport 层连接本地双方 ASGI，没有新建 Mock 服务；异常测试在 transport/响应生成处注入网络故障。

| 必测行为 | 实际测试及断言 |
|---|---|
| 第二个/就第二个吧 | `test_ordinal_real_chain_and_exact_replay` 两项，选当前修订第二个真实 ID；同 task_id，成功后推进 revision；正式确认可执行。 |
| 两盒/仍缺字段 | `test_amount_missing_fields_and_allowed_fields`，只补允许数量单位，仍缺位置时继续 needs_clarification，无库存/草稿写入。 |
| 昨天可信日期 | `test_yesterday_uses_server_context_date_not_client_clock`，与数据库 context.created_at/时区核算日期一致，伪造 trusted_now 被 422，OPEN 确认仍拒绝。 |
| 歧义不默认第一批 | `test_ambiguity_never_defaults_first_candidate`，“这个”“第四个”均 needs_input，无提取、无额外任务。 |
| 唯一引用/真实位置 | `test_reference_rereads_location_preserves_original_and_ttl`，查询后位置、版本改变，指代返回新值；原文空格保留，引用期限不变。 |
| TTL/删除/终态/来源修订/成员撤销 | `test_reference_invalidations` 五项，分别返回明确失效原因，不产生正式写入。 |
| 引用入口真实接通/默认关闭 | `test_reserved_reference_endpoint_now_real_but_feature_gated`，显式测试配置下真实 HTTP 成功；默认/关闭状态 503 和能力 false。 |
| 错对象/跨家庭/错用户/错 revision | `test_reference_untrusted_selectors` 四项，404/409/422 拒绝。 |
| 新任务/清引用/切家庭 | `test_clear_new_topic_and_household_switch_invalidate_old_binding`，清游标不删历史，旧来源不可重挂到新话题或新家庭。 |
| 重复键/额外内部字段 | `test_request_conflict_and_private_context_rejected`，不同文本相同键 409，binding/版本/候选/时钟注入 422。 |
| 候选列表/版本变化 | `test_candidates_changed_since_question_rejected`，原候选版本变化后拒绝序号续接，不生成错误草稿。 |
| 快速“第二个”再“两盒” | `test_fast_candidate_then_amount_requires_new_revision`，旧 revision 拒绝；新 revision 继续原消费任务；引用 revision 随任务更新但 TTL 不变，后续指代查询仍可用。 |
| 澄清超时恢复 | `test_clarification_response_loss_retries_same_turn_without_extraction`，真实澄清执行后丢响应，原 request_id/原体恢复同任务，不再次提取。 |
| 新任务未知计费结果 | `test_new_task_unknown_outcome_never_reextracts_on_retry`，首次提取后丢响应，重复请求 AI_OUTCOME_UNKNOWN，返回原 task_id 查询；提取计数保持 1，不自动再次付费。 |
| 回执与任务原子保存 | `test_atomic_turn_receipt_survives_public_response_failure`，事务提交后 JSON 响应生成失败，原键恢复同一结果，无重复修订。 |
| 注销/新登录及请求期间注销 | 两项 logout 测试，旧 token 401，新 session 不接旧绑定，等待适配器时撤销会话也不能保存回复。 |
| 过期任务/旧 worker | `test_expired_task_and_old_turn_cannot_advance_state`，过期补充 needs_input，旧 nonce 无法改变会话或任务修订。P1 旧 worker 防覆盖测试仍通过。 |
| 内部适配器缺失/认证 | missing-adapter 测试 503 且无模型回退；内部路由缺 Token 401、错 scope 403。 |
| 同 revision/重复 request_id 并发 | `test_concurrent_same_revision_is_recoverable` 两项，在真实 PostgreSQL 中验证同键/异键竞争，返回 200 或可恢复 409，只有一个原任务和草稿，修订不重复推进。 |
| P1 四动作/幂等/回执恢复 | 全量保留并运行 P1 后端测试及其五项 PG 并发参数；不改变正式执行服务。 |

## 9. 零模型调用证据

不是以没有配置 Key 或跳过请求作为零调用证明。使用现有 P7 工厂、设置 P3_ENGINE=deepseek，同时注入**可计数的项目 RuleEngine 提取器**；首次确需理解的新任务使 extract 计数增加，后续结构化续接/引用/重置经过真实逻辑而不增加。

独立证据：[SQLite 计数](backend-p2-sqlite-model-calls.json)、[PostgreSQL 计数](backend-p2-postgres-model-calls.json)，含实际内部 HTTP 路径记录。固定链路的累计提取次数：

| 阶段 | 累计 extract 调用 |
|---|---:|
| 初始 | 0 |
| 首次有名称库存查询 | 1 |
| 可信“它在哪里”重读 | 1 |
| 开始新任务/清引用 | 1 |
| 新增牛奶的新理解请求 | 2 |
| 补“两盒” | 2 |

两个候选续接表达、日期补充、歧义、金额和响应丢失恢复也分别断言计数不增加。真实模型付费服务未调用；这些证明的是实际执行路径不进入 extract，不是声称已观测正式 DeepSeek 账单。Agent 原有计费策略测试另外通过，含一次 provider transport 测试调用和预算落账，实际公网 API 未访问。

## 10. 实际命令、SQLite/PG/Agent 结果及失败记录

工作目录均为内层工程。Python 3.12.8；后端用 P1 `.venv` 及既有 requirements，Agent 全量测试另外使用其 lock 文件指定环境。依赖证据见 [后端环境](backend-p2-environment.json)。

| 命令/检查 | 实际结果 |
|---|---|
| P1 核心 `pytest test_v09_execution.py test_v06_agent_gateway.py` | 50 passed / 5 skipped，原链路保留。 |
| P2 首轮 `pytest test_backend_p2_conversation.py` | 22 passed / 2 skipped；新增边界后继续完整验证，没有把跳过 PG 标记为通过。 |
| `.\.venv\Scripts\python.exe -m pytest backend/server/tests -q --tb=short --basetemp=.cache/p2-final-sqlite --junitxml=reports/backend-p2-sqlite-tests.xml` | **174 passed / 23 skipped / 0 failed / 0 error，exit 0**。23 项=16 项可选 Nginx＋7 项 PostgreSQL 行锁测试。 |
| `.\.venv\Scripts\python.exe tools/p72_local_postgres_tests.py --stage p2` | **181 passed / 16 skipped / 0 failed / 0 error，exit 0**。真实 PG 17.11，7 项并发参数均运行；16 项可选 Nginx 因无本地二进制跳过。 |
| 脚本中 Alembic upgrade/downgrade | 全新临时库 head(0008)→0007→head→0006→head，全部 exit 0；另有已存在会话记录时禁止降级的自动化断言。 |
| 脚本中实际 Uvicorn 启动 | 迁移后的隔离数据库上 health=0.9.0/isolated_test=true，ready.database=ok；随后仅停止本轮进程。 |
| Agent 全量首次（后端依赖、从 agent 子目录运行） | 750 passed / 22 failed：16 项旧测试缺仓库根导入路径；6 项历史 OpenAPI 快照与后端环境的 FastAPI/Pydantic 版本不一致。保留 [首次失败 XML](backend-p2-agent-initial-tests.xml)。未据此修改 AI 算法或覆盖历史 Schema。 |
| Agent lock 环境首次 | 325 passed / 447 failed：Windows 独立环境缺 IANA tzdata，导致 Asia/Shanghai 校验失败；保留 [时区环境失败 XML](backend-p2-agent-missing-tzdata-tests.xml)。 |
| Agent 正确环境最终：`$env:PYTHONPATH='<仓库根>;<仓库根>/agent'; .\.cache\p2-agent-venv\Scripts\python.exe -m pytest agent/tests -q --tb=short --basetemp=.cache/p2-agent-final --junitxml=reports/backend-p2-agent-tests.xml` | **772 passed / 0 failed，exit 0**。环境按 `agent/requirements.lock.txt` 安装，Windows 额外安装已有后端使用的 tzdata==2026.5；不修改项目算法。 |
| 后期针对性测试一次失败 | 增加后续指代查询后，测试仍断言总任务数为 1；实际应为原消费任务＋独立查询共 2。修正测试计数，没有回退正确的新任务行为；最终完整测试通过。 |
| OpenAPI 导出/所有本地引用/路由唯一性 | 双方导出 exit 0，测试通过；新公开 DTO 拒绝内部上下文，旧四字段/九字段检查继续通过。 |
| `python -m compileall -q backend/server/app backend/server/alembic backend/server/tests agent/conversation ...` | exit 0；真正导入/启动由 HTTP 集成和 Uvicorn 验证。 |
| `git diff --check` | exit 0。 |
| Docker build、公网付费模型/Android 联合验收 | **未执行/未验证**，本地无 Docker CLI；没有用 compileall 冒充镜像构建。 |

完整机器证据：[SQLite JUnit](backend-p2-sqlite-tests.xml)、[PostgreSQL JUnit](backend-p2-postgres-tests.xml)、[PG 迁移/启动/输出/清理](backend-p2-postgres-evidence.json)、[Agent JUnit](backend-p2-agent-tests.xml)。旧 Starlette/AnyIO 与 Alembic 弃用警告仍存在，未引入新测试框架。

PG 使用本轮随机本地目录和端口、独立测试库及随机凭据；写入前核对 DB 名和 SHOW data_directory。结束后 postgres_stopped=true、cluster_removed=true，不安装服务、不访问正式数据库、不使用现有 Docker Volume。凭据未写入报告/证据。

## 11. 已实现、已验证、已部署与未完成

| 维度 | 本轮状态 |
|---|---|
| 本地代码 | 自然语言续接适配、数据库绑定、服务端可信引用、去重/并发/原子回执、追加迁移完成。 |
| 本地确定性集成 | SQLite/PG 完整后端、Agent 全量离线、七项 PG 并发、迁移、实际 Uvicorn 启动及 OpenAPI 检查通过。 |
| 正式部署 | **未部署 P1/P2 补丁，未重启/迁移/切镜像**；仍为基线镜像/0007，缺新内部 HTTP 路由，引用能力 false。 |
| Android | 没有改前端，已交准确接口文档；真实 APK 弱网、进程重建与页面交互尚未联合验收。 |
| 真实 DeepSeek | 本地有效配置已恢复，确定性链不依赖真实付费调用；本轮未进行真实模型对话或公网端到端验收。 |

当前明确限制：

- 原 Agent 没有付费提取结果的持久化幂等恢复接口。新任务消息响应未知时，本适配器保存原 task_id 并停止自动提取，返回 AI_OUTCOME_UNKNOWN；可以查原任务，不能凭超时/404 换键盲目再付费。这是保守的准确 unknown 状态，不宣称能凭空恢复丢失的模型结果。
- 同一用户一个活动会话游标，跨设备冲突显式处理；不实现完整聊天线程/多窗口合并系统。
- 新旧主聊天入口不应混用维护同一个活动会话；旧客户端继续走原结构化表单，新客户端统一使用新适配入口。
- 真正自由措辞仍受 P7.3 原规则边界约束。“昨天”等合法字段补充可确定性处理；任意长句不保证零次提取或必然识别，不复制新算法来猜测。

## 12. DeepSeek 与 pricing.json 处理状态

依据已核实，不再保留 P1 的无效 JSON 阻塞：

1. `git show 9d0a678` 显示原始 P7.4 提交“取消费率日期拦截”，同时提供 `test_pricing_policy.py`，现有 budget.py 已采用此实现。
2. 本轮从正在运行的 p74 镜像只读取得公开 pricing.json，另存 [已发布配置证据](backend-p2-published-pricing.json)，没有读取 Key 或内部令牌。
3. 本地 pricing.json 恢复为该已发布 JSON，保留 model、核验元数据和原费率，未改预算上限或任何计费算法，未另查或推测新的市场价格。
4. 注意已发布 policy 的文字仍写有“7 天后人工刷新”，而 P7.4 执行代码不把该日期当运行时过期门禁。本轮保留已发布元数据，不把文字差异变成私自恢复七天拦截；后续文案统一由 AI 成员审查。
5. Agent 的旧日期/模型不匹配/累计预算/usage 记账等既有测试在最终 772 项中通过。实际付费 Key、供应商可用性、账单和正式服务自然对话本轮未验证。

历史 `reports/p72/` 中相互矛盾的报告/证据冲突仍不改写；不能把本轮测试倒填为历史成功记录。

## 13. Android 队友所需改动

详见 [backend-p2-frontend-handoff.md](backend-p2-frontend-handoff.md)：主输入框提交原文＋当前 task_id/revision；后端已续接时不重复调用澄清接口；保留完整 Task 和完整请求体；候选顺序与 revision 一起保存；用响应 task.revision 发下一条；区分路由结果与正式执行回执。

家庭/账号切换清本机引用，恢复时不续 TTL；请求未知保持原键/体；AI_OUTCOME_UNKNOWN 不自动换键；草稿确认继续保存稳定 operation_id。引用 true 只能来自已经实际部署验证的能力配置，不能根据版本号或本报告自行开启。

## 14. P3 OPEN/DISCARD 准备

日期续接、明确批次选择、可信引用、新任务恢复及现有确认接口已准备好；AI 可产生 OPEN/DISCARD 草稿，但 P2 **不开放正式执行**。

P3 应从本次 `20261023_0008` 继续追加后继迁移（不要恢复历史另一条 0008 覆盖当前链），补充 OPEN/DISCARD schema、操作/事件数据库约束、开封日期/终态、丢弃模式和数量精度、版本校验、真实 Opened/Discarded 事件及并发幂等测试，再在独立授权发布阶段启用。自动 PLAN_ADD 确认仍为 false，不能把本次对话续接当作自动补货重验能力。

本轮无正式部署、正式业务写入、Volume 删除、Android 改动或秘密输出。后续部署和最终联合验收需要单独明确授权。
