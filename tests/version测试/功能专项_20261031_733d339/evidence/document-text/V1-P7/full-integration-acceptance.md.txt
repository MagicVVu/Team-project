# V1-P7 三端完整联合验收与生产发布准备报告

日期：2026-10-17。判定：**NO-GO，当前不能进入第六阶段正式发布。** 已完成候选修复、构建和相当部分验收；服务器后续 SSH 与已有测试隧道均超时，最终候选在服务器上的测试/部署状态及生产最终健康无法取回。另缺物理真机、正式 HTTPS/签名配置、冻结数据问题处置及候选提交审查。不能将这些未知项认定为通过。

本轮没有向生产发送文件修改、容器切换、数据库写入/迁移命令，没有推送 GitHub，没有付费模型调用，没有删除历史卷、账本、回执或 Android outbox。隔离环境发生过真实故障，下面保留失败记录，不合并不同批次结果制造全绿。

完整本地证据目录：`C:/Users/Cavia/AppData/Local/OpenAI/Codex-Account2/codex-home/visualizations/2026/10/17/01a1488c-0eac-7ca1-8090-0af8562bc511/phase5`。服务器新证据工作区：`/home/admin/magicvvu-p7-rc-20261017`。原 phase3、phase4 本地证据未覆盖。私有 fixture 文件不进入公共证据包。

## 1. 代码与交付一致性

开始和后续通过 GitHub API `GET /repos/MagicVVu/Team-project/branches/dev` 核实远程 HEAD 均为 `04f930aabe087962aa4065bf33e7a4da1a5d443f`，tree 为 `4bf037f32de3fcdd0df00f1a16112a8fb0d3a864`；本地初始 HEAD 相同，初始工作区干净。没有 reset、clean、pull 覆盖、强推或自动合并。

- 第三阶段 52 个后端文件的 Git blob SHA256 与当时交付清单一致，含 0007、草稿执行模型/服务/路由/测试。
- 第四阶段 20 个 overlay 文件进入该 dev；归一化换行后内容一致。17 个工作区字节差异、4 个 Git blob 字节差异均属 LF/CRLF，不能当成逻辑差异。旧 APK 实体 hash 与阶段四清单一致。
- 三份旧报告实际存在；阶段三、四 Markdown 所链接证据文件均存在。阶段二报告的裸文件名证据（model-results.json、model-budget.json 等）在本地未附带；服务器后续无法导出，**阶段二付费结论仅保留原报告与先前检查，未声称本轮重新验算了供应商用量/账本**。
- 本轮在该提交上新增未提交修复，最终候选是“基准 + overlay”，不是纯远程 dev。逐文件 hash/状态见 `candidate-source-manifest.json`、补丁见 `candidate.patch`、源码包见 `candidate-source-overlay.zip`。无待合并冲突；仍需团队审查并固定新提交后重新核对。
- 品牌图片、猫又资源和团队资源未替换；四栏、首页 AI、拉绳与主题保留。`git diff --check` 通过，原有 37 项 UI 在同一最终 APK 一次运行全通过。

证据：`initial-git.json`、`code-consistency.json`、`historical-evidence-audit.json`、`apk-manifest.json`、`android-original37.log`。

逐文件修改列表与 SHA256 另见 `changes.md` / `candidate-source-manifest.json`，实际执行命令见 `commands.md`。源码、公开证据分别保存为 candidate-source-overlay.zip、public-evidence.zip；私有 fixture、venv、完整副本和数据库 dump 均不在公开包中。

## 2. 实际运行环境与安全连接

实际 SSH 用户 admin。使用 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes magicvvu`，仅沿用已有 sudo Docker 权限；没有改动 SSH、sudo、ACL 或防火墙。

| 对象 | 本轮实际确认 | 当前限制 |
|---|---|---|
| 生产 | 后端 0.8.0、isolated_test=false；三个生产容器在末次可读检查健康，启动时间未因本轮重置 | SSH 中断后最终健康 UNKNOWN；未发出生产变更命令，不等于能证明远端始终无故障 |
| 第三阶段 | 后端 0.9.0、isolated_test=true；PG17/0007 基准；AI P7/rules；无宿主发布端口 | 候选后端最终切换/测试结果未取回 |
| AI 隔离候选 | r2 镜像 `magicvvu/agent:p7-rc-04f930a-r2` 已构建并切换隔离 agent，入口 conversation.app:create_app --factory | 最终服务器源码 hash/健康再次确认 BLOCKED；r2 digest 见构建日志记录及恢复后复核 |
| 后端隔离候选 | `magicvvu/backend:p7-rc-04f930a` 已构建，构建 config digest `sha256:51a557e874404ecf55e2f108662b24d6954612e49c75095d09a42d4022c798fe` | 仅构建成功可确认；远程回归后才切换的脚本结果 UNKNOWN，不声称已运行 |
| Android | 最终 Debug、测试 APK、unsigned Release 均构建成功 | 无正式 HTTPS 地址/签名；不能发布 |

重新读取过 backend Docker IP（当时 172.24.0.4）。旧 18082 监听无法验证目标，未覆盖或终止。确认 18083 空闲后创建独立仅回环隧道：

```text
ssh -N -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18083:172.24.0.4:8000 magicvvu
```

当时本地 PID 29920，Android 使用 `http://10.0.2.2:18083`。执行前 health 与登录后的 capabilities 均验证了 0.9.0 / isolated_test=true / draft-execution-1 / business_backend。**现在该隧道健康超时，不能复用历史 PID/IP 宣称连接有效；恢复后必须重新读取。** 没有增加公网监听或更改生产 127.0.0.1:8000。

配置只核对名称、存在性、内部 URL 格式与双方匹配。已验证 AI_SERVICE_TOKEN 长度与双方一致，BACKEND_TOOL_TOKEN 双方一致，AI_SERVICE_URL 指向 agent:8767，BACKEND_BASE_URL 指向 backend:8000。rules 未注入模型 Key。原始 server-audit 中 engine_rules=false 是检查了错误环境变量名的审计脚本问题，实际 health.engine=rules；保留原 JSON 并在 audit-corrections.json 更正，脚本已改读 P3_ENGINE。

证据：`containers-baseline.json`、`server-audit.json`、`audit-corrections.json`、`server-outage.json`、HTTP progress 首次验证与 runner 的目标门禁。

## 3. 发现的问题与实际修复

| 问题 | 修复 | 源码/验证状态 |
|---|---|---|
| 预检断网时新消息尚未保存 | AssistantStore 在能力发现前先保存 request_id、原文与完整请求 | 新 Android 测试通过；不会隐式换 ID |
| 退出登录删除 outbox | 只解除当前身份绑定，原作用域记录保留；重登可 GET 恢复 | 退出/重登专项通过；未清空旧 outbox |
| Debug 与未来生产目标混用 | 新 TargetPolicy 分离环境；CloudApi 所有写方法健康预检，业务写入另验证能力 | JVM 策略测试通过，Release fail closed；正式 TLS 现场验收未完成 |
| rules 不理解指定位置问答、带来源位置 MOVE、旧“库存有什么” | P7 增加窄范围字面语义，按真实库存筛选，保留原文与多批次选择 | 新增 7 项通过；两种主题完整流程在部分联合批次通过 |
| 并发 AI 消息占用连接，内部工具 5 秒超时 | commit 前保存原始 UUID/文本，等待 AI 时不读取已过期 ORM 属性；消息与澄清均处理 | 本地全量 80 通过，新测试检查回调期间 checkedout=0；最终服务器双用户并发消息复测 BLOCKED |
| 隔离后端 OOM | 证实 OOMKilled=true / Exit137，原限制 192 MiB；只将该测试容器调整为 320 MiB / swap512 MiB 并启动 | 操作成功；保存独立资源 override，最终采样尚在服务器，未完成容量验收 |
| 窗口、图片资源与 Locale Lint | 根视图实际高度/可释放监听、Compose 配置感知资源、Locale.ROOT、去重 label | 构建、Lint、完整旧 UI 通过；未改品牌资产 |
| 测试 runner 错把 OK(0 tests) 计通过 | 强制实际测试数 >0；保留一次错误方法名导致的 0 项记录 | 之后真实 37 项和 16 项批次均有逐项结果 |

OOM 的直接证据是测试后端 cgroup 上限；在容器中执行种子/验证 Python 也计入同一限制。后续 SSH 超时是否由主机资源、网络或其他原因造成尚未确认，不能直接归因为 OOM。远程测试客户端已中断；重新连接后需先核对是否仍有本轮验证容器/进程，以及候选后端是否已经切换，不能假定远程子进程全部已退出。

## 4. 自动化测试矩阵

| 项目 | 实际结果 | 证据与适用边界 |
|---|---|---|
| Debug APK / instrument APK / unsigned Release | PASS | gradle-final2.log、apk-manifest.json；相同最终 Android 代码 |
| Kotlin/JVM | 24 PASS | jvm/TEST-*.xml，含 TargetPolicy 3 项 |
| Debug / Release Lint | 0 Error / 27 Warning | 两份 lint XML；未禁用检查 |
| **原有完整 UI 37 项** | **37/37 PASS，一次运行 86 秒** | android-original37.log；拉绳/主题/导航/环形库存等，不拼接历史结果 |
| 联合批次一 | 15 PASS / 1 FAILED，179.216 秒 | android-final-integration.log；失败旧“库存有什么”断言，随后补规则修复 |
| 联合批次二 | 14 PASS / 2 FAILED，186.873 秒 | android-final-integration2.log；旧云端数据/登录通过，四动作专项和浅色旅程受工具超时/等待失败影响；保留失败 |
| Android 最终候选全量联合复测 | BLOCKED | 后端连接释放修复后未能重新跑服务器联合批次 |
| 后端初始服务器回归 | 79 PASS / 5 SKIP | backend-unit.xml；5 SKIP 是单独 PG 并发项 |
| 最终后端本地回归 | **80 PASS / 5 SKIP**，37.12 秒 | backend-final-local2.xml/log；含新增连接归还测试 |
| PG17 草稿专项初始候选 | **44/44 PASS** | backend-postgres.xml；每项新 schema，含并发、事务回滚、鉴权/回执恢复 |
| 最终后端服务器 PG 复测 | BLOCKED/UNKNOWN | 远程已启动，SSH 中断，结果不能回填成 PASS |
| AI 最终固定依赖、本地 Git LF 字节副本 | **662 PASS / 2 FAILED**，7.78 秒 | ai-final-pinned2.xml/log；664 项，P7 原有86+新增7全部通过，无付费调用 |
| AI 服务器中间候选 | 661 PASS / 2 FAILED | 最后增加“库存有什么”之前；最终服务器重跑未取回 |
| 真实进程死亡后的恢复 | BLOCKED，本轮未重跑 | 原阶段四证据保留，不冒充本轮新测试；Activity recreate 在本轮 UI 专项通过 |
| 物理设备 | DEVICE_TEST_BLOCKED | device-audit.json：仅 emulator-5554，ABI x86_64，虽型号显示 SM-S9210 仍非物理设备 |

AI 本地第一次误用后端 FastAPI 0.116.1 环境，产生 6 项 OpenAPI 差异及一项缺少打包目录；不能据此改契约。新建 AI 专用 venv 按 requirements.p2.runtime.txt 安装 0.135.1/Starlette0.52.1/Pydantic2.12.5，并补 Windows 所需已安装 tzdata2026.5；完整输入目录恢复后复测。一次缺少 tzdata 的 384 项失败同样保留为环境失败。最终没有修改契约导出或测试断言。

## 5. 端到端场景逐项结果

所有业务写入只用新建随机合成账号与家庭，不清空旧数据库。手机密码/登录 token 留在私有 fixture/进程内，公共请求记录不含它们。服务器业务回执才是 committed 依据，AI inventory_written=false 不覆盖正式回执。

| 场景 | 已取得证据 | 最终候选判定 |
|---|---|---|
| 1 库存问答 | 精确“冰箱里还有多少牛奶？”返回该位置真实 2 盒；HTTP 比较查询前后库存一致；无确认按钮 | 部分 PASS，最终统一复测待补 |
| 2 ADD | 真实 UI 编辑位置/名称、二次确认、回执和刷新；HTTP ADD 同键重放回执相同 | 部分 PASS |
| 3 MOVE | 真实 UI/HTTP 来源书房→储藏室；数量相同、version+1；批次候选专项通过 | 部分 PASS |
| 4 CONSUME | 真实 UI/HTTP 库存减1；查询 consumption-events 断言真实 Consumed 与 operation_id 一致 | 部分 PASS；最终直接 PG 行对账未完成 |
| 5 PLAN_ADD | 两包纸巾生成共享待采购项，is_checked=false，shopping_written=true / inventory_written=false | 部分 PASS |
| 6 取消 | cancel 成功，随后 commit409，库存比较不变 | PASS 于已验证基准，最终重测待补 |
| 7 网络异常 | 预检前断网、消息成功响应丢失、提交前超时、提交成功响应丢失、刷新失败均有 Android 测试通过记录；同键/原请求不重复执行 | 断点注入测试 PASS；未进行物理网络切换 |
| 8 生命周期 | 关闭/重开、Activity recreate、Store/凭据恢复通过；强停/实际重启本轮未完成 | PARTIAL / BLOCKED |
| 9 并发 | 初始 PG44 含同草稿/同键/版本竞争；Android 两用户相同版本一成功一冲突、一次事件断言通过；另发现并修复消息连接池问题 | 最终服务器并发回归 BLOCKED |
| 10 家庭隔离 | PG/后端测试覆盖全部新路由；Android 外家庭读执行404、commit404、切家庭不绑定旧草稿通过 | 最终 HTTP 矩阵中途停止，未声称逐路由最终现场全通过 |
| 11 不支持功能 | capabilities 关闭 OPEN/DISCARD/自动规划/引用；Android unsupported 无确认按钮；后端拒绝删除规划依据绕过 | PASS 于已有自动化；公开引用 HTTP 本轮脚本未走到该步 |
| 12 完整旅程 | 登录→家庭→首页AI→四动作→库存刷新→清单→退出，两主题均有本轮通过记录 | 最终统一候选重跑待补，不能拼接为全绿 |
| 13 可理解性 | 正式回执后才已执行；预览待确认、采购待购买、冲突重新核对、未知结果原键恢复、暂不支持均保留 | 源码/专项 PASS；物理设备字体/键盘/小屏验收 BLOCKED |
| 14 性能 | Android 实际20条规则业务流程、每阶段20样本；无付费压测 | 仅功能性能样本，未完成最终压力/长稳验收 |

HTTP 原始记录：`http-acceptance-progress.json`，19 次带请求/响应记录后在多批次工具超时处失败。不要把脚本叫作全量通过。`http-receipts.json` 保存四个真实事务回执（均来自隔离服务）：

| action | operation_id | 结果 |
|---|---|---|
| ADD | 56555799-6c68-46f0-bcf2-efeb33549a61 | committed；原键再次提交返回相同回执 |
| MOVE | a47c7fb4-78ed-4c1c-9c12-98b3838129aa | committed |
| CONSUME | c3a2a1e3-bda0-4041-9720-278a1ba195bf | committed + Consumed 查询匹配 |
| PLAN_ADD | 35cd3397-5671-4679-938d-09e12b77776a | committed，仅共享清单写入 |

这些是后端正式业务回执，不是生产数据库写入证据。**最终直接 PostgreSQL 逐行核对未能完成，不能将 HTTP 回执虚称为已完成 PG 对账。**

## 6. 性能

来自第一联合批次 Android 实际 AssistantStore，rules、模拟器、SSH 通道；各20条成功样本，P50为中位数，P95为 nearest-rank 第19条。包含网络/健康与能力预检的指标明确标注，没有将模型阶段二 P95 当成产品耗时。

| 指标 | N | P50 ms | P95 ms |
|---|---:|---:|---:|
| 消息 HTTP（含预检） | 20 | 363.53 | 1089.05 |
| 草稿读取 HTTP | 20 | 101.06 | 190.03 |
| 确认 HTTP（含预检） | 20 | 266.76 | 488.58 |
| 库存及清单刷新 | 20 | 357.02 | 639.55 |
| Android 消息→回执→刷新，不含用户思考/点击时间 | 20 | 1734.98 | 3001.71 |

原始样本 `android-performance.json` 与统计 `performance-summary-pre-fix.json`。第二批次也完成20条成功性能测试，但未将其覆盖已导出的第一批数据。服务器已输出“业务服务 execute+PG commit 20条、纯 rules extract 100条、无付费调用”的完成消息，数组仍在远端 transaction-performance.json / ai-performance.json，SSH 后续无法取回，故 **不提供无法复算的 P50/P95**。前述确认 HTTP 耗时不能称为纯数据库事务耗时。

## 7. 安全与 Lint

Release 静态检查：manifest usesCleartextTraffic=false、allowBackup=false；无 Debug Harness Activity；DEX 无 AssistantHarnessActivity、AssistantExecutionTest、10.0.2.2:18083、AI_SERVICE_TOKEN、BACKEND_TOOL_TOKEN、DEEPSEEK_API_KEY。BuildConfig.DEBUG=false / CLOUD_API_URL=""，未配置正式地址，故网络关闭。没有读取私钥或发布商店。普通 loopback 禁止列表属于策略代码，不是生产连接地址。

Token 不写入聊天/outbox/普通日志；CloudAccount.toString 脱敏。凭据保留既有 Keystore AES-GCM。缓存按服务器/用户/家庭分开；logout 不删历史请求；恢复不自动 POST；版本冲突不自动替换 expected_version。服务认证密钥未放 Android。所有执行路由经 Bearer 与家庭成员/草稿用户校验，输入 extra=forbid、受保护字段拒绝；回执持久化和事件同事务，幂等主键/唯一草稿约束与固定锁顺序保留。

33 项原始 Lint 已逐项分类于 `lint-warning-audit.md/json`：6 项修复（Locale1、label1、窗口1、图片资源3）；27项保留：ApplySharedPref2（同步持久化/生命周期风险，未来后台存储改造）、OldTargetApi1（兼容风险）、NewerVersionAvailable1（工具链维护）、ModifierParameter6（内部布局风格）、UnusedResources7（旧品牌/颜色保留）、UseKtx8（简化建议，不能破坏同步落盘语义）、UseTomlInstead2（依赖维护）。未通过压制规则降数字。还需真机、目标 Android 新版本、真实 TLS、生产身份/限流与容量验收，静态通过不等于这些现场测试完成。

一次自动审批拒绝了可能投影完整 compose environment 值的读取命令，命令未执行；已改为只输出 environment_names 的安全投影成功完成，未要求用户放宽权限，没有未解决的该项审批阻塞。

## 8. 冻结数据问题与证据可信度

| 数据集 | Git LF 实际 SHA256 | 原 manifest 期望 SHA256（CRLF） |
|---|---|---|
| P1 | fe68789aef995b6b1dc3f7a6beab7ba416fe18992e5cac70e73b20e93a7aa960 | f3f223bc0c3ba46749d4db916170c5e2c6d6408c7523d50ab7324179060796eb |
| P2 | 305801600139be80c25bb4609ca9ada93440b00144ac93caae39eaaafa4aee30 | d47647da867ca1838fb57d72832579d59e369c447f4a6b271684dc362e258bae |

Git archive 在此 Windows 配置下导出 CRLF，曾产生一个看似全绿的副本。该结果已判无效：本轮只在新候选副本恢复 `git show HEAD:...` 的原始四文件字节，最终仍保留2失败。没有改变仓库冻结样本、原 manifest 或断言。数据维护者需确定 provenance、历史字节约定与新版本迁移方案；不能在本轮悄悄“修 hash”。证据 `frozen-export-audit.json`、`ai-final-pinned2.xml`。

## 9. 数据迁移、备份和发布演练

已在全新合成库 `magicvvu_p7_rc_f8b946b1` 演练：0.8 镜像升级0006→合成旧业务/任务数据→pg_dump-Fc→恢复另一新库→核对七张旧表计数/行摘要→0.9升级0007→摘要相同→alembic check exit0→执行ADD正式回执→downgrade因存在审计数据拒绝→旧0.8仍可读取。临时0.9/0.8后端均在该合成库启动健康、无宿主端口，随后只停止/移除这两个临时容器，保留数据库/备份/原卷。

备份 SHA256：`b1f0f14e208d157fde1652de94a46ccd68944a345856a1bbb13a384cb457656c`；备份与恢复库仅合成数据。不是生产备份恢复证明。演练摘要在本地 server-audit.json 的 rehearsal 中；二进制备份不加入公共包。Alembic 环状旧外键排序 SAWarning 记录保留。

0007 仅新增三张审计/事件表，兼容旧0006结构；新表主外键、operation全局唯一、draft唯一、状态/动作/数量检查均审查。存在回执后不自动降级数据库；应用回退保留0007与全部历史，数据库恢复必须停写、保全最新数据/WAL、逐笔对账并独立授权。

可审查的完整部署前采集、备份恢复验证、0007升级、镜像切换、正式 P7 入口/私有配置、Android HTTPS、健康与合成家庭烟测、回退策略见同目录 `release-candidate.md`。本轮仅准备，第六阶段执行需用户另行授权。

## 10. 风险、缺失条件与最终判定

| 级别 | 问题 | 关闭条件 |
|---|---|---|
| 高 / 发布阻塞 | SSH/隧道中断，最终远端作业、候选版本及生产健康 UNKNOWN | 控制台排查；恢复只读连接，核对主机资源、Docker OOM/重启、项目/迁移/源码 hash/在途验证进程；不得直接重启生产 |
| 高 / 发布阻塞 | 并发工具读取修复仅最终本地通过，服务器完整候选尚未统一验收 | 最终候选 PG44、双用户并发消息/提交、HTTP及Android完整联合、直接DB事件/回执对账重跑通过 |
| 高 / 发布阻塞 | 隔离后端 OOM，容量结果未取回 | 获取24次资源采样，限额内串行/受控负载验证，批准主机和生产资源预算；不盲目改生产 |
| 高 / 发布阻塞 | 无物理真机和正式 HTTPS/签名链验收 | 授权设备完整流程、字体/键盘/小屏/网络切换，真实 TLS 与正式目标策略通过 |
| 中 / 发布阻塞或明确豁免 | 冻结摘要2失败；候选未提交 | 数据负责人版本化处置/书面豁免；团队审查、固定新commit/image/APK并核对dev无并行变动 |
| 中 | 本轮实际进程重启恢复、纯解析/纯事务性能原始数组、阶段二裸文件证据未取回 | 连接恢复后导出脱敏证据并验 hash；强停/重启本轮重测，不用历史替代 |
| 中 | 未验证手机号原型身份、限流与公开注册策略 | 发布负责人审核公网认证部署；保持未验证注册关闭，不放松家庭鉴权 |
| 低/中 | 27 Lint、旧环状外键/Alembic警告、target兼容 | 按逐项风险记录管理，未来工具链/系统版本验证；不压制检查 |

结论明确区分：**源码修复完成并有本地测试；隔离联合验收仅部分完成；生产未部署。当前不具备第六阶段正式发布条件。** 可以继续进行只读排障、非生产补验与发布评审准备；所有高风险门禁、真机/HTTPS、最终一致性和证据缺口补齐后再决定 GO。第五阶段在此停止，不自动上线。
