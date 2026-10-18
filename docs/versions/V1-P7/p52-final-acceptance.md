# V1-P7-P5.2 最终候选联合验收与发布门禁报告

日期：2026-10-18（Asia/Shanghai）。候选构建快照：`843c6855920cbd04c1af071a6340a9f5a468d02103a340d0cf2b177ea0cb23e3`。基础提交与收尾远程 dev 均为 `04f930aabe087962aa4065bf33e7a4da1a5d443f`。

**判定：NO-GO，尚不能进入第六阶段正式发布。** 四项业务与关键技术验收已通过；AI 冻结摘要处置、正式 HTTPS/签名/真机、生产容量及真实备份审核、团队候选审查和用户发布授权仍缺失。没有生产部署或 GitHub 推送。

## 1. 范围、代码与证据来源

已阅读 P5 的 full-integration-acceptance.md、release-candidate.md、candidate.patch/manifest、P5.1 恢复报告与实际服务器证据。P5.1 基础恢复门禁通过，但旧源码挂载及旧后端镜像不能作为最终候选；本轮已修正测试路径并切换**仅第三阶段隔离 backend/agent**。

授权登录身份仍为 admin。未写入生产目录，未重启生产服务，未执行生产迁移/业务写入，未修改 SSH、ACL、sudo、防火墙或生产配额；没有付费模型调用。magicvvu_ai 读取限制未改动。

`candidate-source-manifest.json` 列出 923 个快照文件及 SHA256；Git 未改文件使用原 blob 字节，overlay 使用工作区实际字节。初始 overlay 已备份，队友代码未 reset/clean/覆盖。`candidate-attempt1.patch`、初始状态与失败日志保留。最终应用快照不是已提交的新 Git commit。

构建后又修正了一个**不进入 APK/运行镜像**的 HTTP 验收脚本：原脚本错误地要求 OPEN 的 AI 任务本身必须 unsupported，实际兼容网关允许保留预览；修正为读取独立 execution=unavailable、实际 commit 返回 ACTION_NOT_EXECUTABLE 且库存不变。`acceptance-harness-overlay.json` 明确记录这一个快照后差异；`http-acceptance-final.py` 是真正执行的版本。完整审阅 diff 以 team-review.patch 为准，不能误称 dev 已含本轮所有修复。

**固定的是可复核的应用构建输入与产物，正式 RC 冻结/放行未签署。** 构建快照、验收脚本修正及新报告的审阅状态在 final-candidate-manifest.json 分开记录；如团队要求单一提交，应将补丁审阅归并后建立新提交和 CI 证明，不应把 overlay 直接推送共享 dev。

运行代码证明：runtime-final.json 中 backend 41 个文件、AI 79 个文件与冻结快照逐字节匹配；无缺失。Android 又从独立 source/frontend 快照直接构建，三个 APK 与已跑完整回归的 APK SHA256 全部相同（snapshot-apk-reproducibility.json）。旧 checkout 换行不再是构建来源歧义。

本轮实现：AssistantPullLayer 增加落地完成的无障碍状态，过渡期间不接收点击；AssistantExecutionUiTest 等待真实落地/按钮启用并保留失败诊断。新增 p52_snapshot、p52_remote、p52_sample、p52_db_snapshot 工具。继承并审查 TargetPolicy、AssistantStore、P7 位置查询与 gateway 释放连接修复。完整文件表见 review-changes.md。

## 2. 实际运行环境与候选产物

| 环境 | Backend / AI / PostgreSQL | 迁移与状态 |
|---|---|---|
| 生产 magicvvu-starter | 0.8.0 / 原 P1 / 17.11 | 0006；3 个 healthy，ID/镜像/启动时间/重启次数均未变 |
| 第二阶段隔离 | 原 5 容器 | 0006；均 healthy，8 个受保护生产及第二阶段容器均未变 |
| 第三阶段隔离最终候选 | 0.9.0 / V1-P7 0.7.0 rules / 17.11 | 0007；3 个 healthy，isolated_test=true |

证据：server-before.json、server-after.json、protected-services-comparison.json、configuration-final.json。数据库版本采用显式 READ ONLY 事务实际查询，不以文档代替。测试 DB 与生产为不同容器/卷；保留既有执行库、AI 缓存、预算账本和历史回执。

| 镜像 | 本机实际 digest |
|---|---|
| `magicvvu/backend:p52-843c6855920c` | `magicvvu/backend@sha256:abd576f9b98a45f2484184b39324033976ee19a39654529b0861a13bd696c687` |
| `magicvvu/agent:p52-843c6855920c` | `magicvvu/agent@sha256:6f650a872f18fc368e1d93bffb96c2fb6d9b9928fc0b7e70a783cc7142bd42c8` |

这些是服务器本地构建与实际运行的镜像，未推送镜像仓库。digest 与 Image ID 原始投影保存在 images.json；以 runtime-final.json 的运行容器 Image 为准，不能仅凭标签存在认定部署。AI 入口为 conversation.app:create_app --factory，实际 OpenAPI version=0.7.0。

| APK | SHA256 |
|---|---|
| `app-debug.apk` | `32514e6a6465fb3e5bcc26b91834a12a72cd5f732e92b6837dea1825f78cc2b6` |
| `app-debug-androidTest.apk` | `abf049e8d45b1b9297a52f7e851943bbc6d2cc4a303f11586d11cab4be452908` |
| `app-release-unsigned.apk` | `87743db25d1a3040f5ee19e7967e5d8e1b03be14718d59536262567432eb4582` |

unsigned Release 是静态候选产物，不是签名发行包。所有 APK 存在 artifacts/，没有上传用户渠道。

## 3. 自动化与业务验收矩阵

| 项目 | 最终结果 | 原始证据 |
|---|---|---|
| 后端完整回归 | 80 PASS、5 SQLite SKIP（共85） | backend-final.xml / .log |
| draft_execution PG17 专项 | 44 PASS、0 SKIP、0 FAIL | postgres.xml / .log / postgres-status.json |
| 五项 PG 专用并发 | 全部真实执行通过，未计入 SQLite 通过数 | pg-skips-resolved.json |
| 消息/澄清释放连接 | 单元断言 await 回调时 checkedout=0；实际双用户工具回调通过 | test_v06_agent_gateway、backend-final.xml、http-acceptance.json |
| Android JVM | 24 PASS | jvm/、jvm-summary.json |
| Debug / test APK / unsigned Release | 快照构建成功、APK可复现 | gradle-final.log、gradle-snapshot.log、snapshot-apk-reproducibility.json |
| Android 原有完整 UI | 同一最终 APK 单次37/37 PASS | android-final-original37.log |
| Android AI/HTTP/Compose 联合 | 同一最终 APK 单次16/16 PASS，0 ignored | android-final-integration16.log |
| 真实进程强停恢复 | prepare → force-stop → 新PID恢复，2方法通过 | android-process-restart.log、runner源码 |
| AI 全量非付费回归 | 662 PASS、2 FAILED，未豁免 | ai-final.xml / .log |
| HTTP 完整业务链路 | 12组检查通过；75条脱敏HTTP记录+2条并发聚合记录 | http-acceptance.json |
| 两用户受控并发消息 | 10对 / 20请求，全部 answered | dual-user-performance.json |
| Android 直接 PG 对账 | 41操作=41事件，4取消无写入 | android-final-db-before/after.json、android-db-reconciliation.json |
| HTTP 直接 PG 对账 | 6操作=6事件，1取消无写入 | http-db-before/after.json、http-db-reconciliation.json |
| 0007迁移 / 合成备份恢复 / 旧08读取 / 降级保护 | 通过；资源门禁中断后从原停止点恢复，无重复提交 | rehearsal-attempt.log、rehearsal-resumed.json、rehearsal-resume.log |
| 旧08应用启动回退 | 128MiB单独隔离容器实际health=0.8.0，正常停止，无OOM/公网端口 | startup-rollback.json |
| 物理真机 | DEVICE_TEST_BLOCKED，仅MuMu Android12/API32 | devices-final.txt、emulator-final.json |
| 正式HTTPS/TLS/签名 | BLOCKED；未配置经批准的正式origin、未验证信任链、无发行签名 | https-prerequisites.json、release-static.json |

不得将80+44相加宣称124个独立后端用例：PG44与SQLite子集重叠。五个曾跳过项为 same_key、different_keys、different_drafts、same_key_two_drafts、cancel_race，均在最终新 schema 执行通过。PG测试依赖镜像只提供依赖；真正源码只读挂载 /home/admin/magicvvu-p7-p52-final-20261018/source 到 /repo，WORKDIR=/repo/backend/server，PYTHONPATH 指向该目录。postgres-binding.json 记录实际容器配置；未复用旧 /home/admin/...execution/backend 挂载。

### 四动作与限制

| 动作/场景 | 源码与隔离验收 | 生产 |
|---|---|---|
| ADD | 确认后新增库存；生成草稿前后库存不变；位置必填 | 未部署 |
| MOVE | 指定批次位置与版本变化，数量不变；同名批次须澄清 | 未部署 |
| CONSUME | 确认后真实扣减，Consumed/回执/decision同事务；重试与并发不重复 | 未部署 |
| 手动PLAN_ADD | 生成未购买共享采购项，不入库 | 未部署 |
| OPEN / DISCARD | 保留AI预览；execution不可执行；实际提交409，无假成功 | 未部署 |
| 自动规划确认 | planning_basis不能被移除，后端拒绝；PG用例通过；本轮未取得真实自动规划草稿的Android端到端提交证据 | 关闭 |
| 公开受信引用 | 认证后503，未伪造客户端受信引用 | 关闭 |

查询、消息同键恢复、候选第二批次、取消、用户/家庭隔离、库存expected_version冲突、同草稿同operation_id并发、不同用户竞争、丢失响应后GET恢复均已验证。断网/响应丢失通过真实HTTP边界注入异常，Wi-Fi物理切换仍待真机；没有将其写成真实无线网络验收。

浅/深主题完整旅程包含登录→家庭→首页AI→查询→库存拉绳→ADD/MOVE/CONSUME/采购→库存搜索→清单→退出。原四栏导航、猫又品牌与落地回弹37项全通过；品牌资源文件未改。截图 light-committed-receipt.png、dark-unsupported.png 已人工查看，成功回执与历史预览分开，无支持假象。

### 本轮失败与修复，不隐藏历史结果

1. PG第一轮44项断言跑完，但输出目录新建权限使XML落盘失败。保留 postgres-attempt1-evidence-permission-error.log；只修改新P5.2证据目录所有者，再完整44项重跑成功。未把第一轮当正式通过。
2. Android首轮15/16，浅色完整旅程在重新展开幕布发送ADD时超时。诊断显示文字留在输入框、任务数未增加、busy=false且无后端错误；截图引入等待后通过，支持界面过渡竞态定位。新增落地状态/输入门禁后去除截图延时复测成功，再统一37和16全量通过。保留首轮、诊断及修复后全部日志。
3. HTTP首轮在OPEN上错误断言AI status必须unsupported而失败；兼容网关实际生成预览，独立执行器正确关闭。修正工具为验证execution与真实拒绝，库存无变化；用新家庭完整重跑通过。没有改网关、家庭鉴权或业务能力来制造成功。
4. 最终部署容器IP变化，隧道目标门禁主动阻止继续。仅关闭并重建本轮自建18083隧道；原生产8000和历史隧道未动。
5. 最终迁移演练在业务ADD已提交后触发300MiB主机余量门禁，未进入降级步骤。确认无旧作业后，只在原合成库恢复降级保护/旧版读取，未重建或重复提交。额外重复启动一份0.9的320MiB总预算门禁未满足；已有最终0.9实际启动与完整业务证据，另以128MiB旧08容器验证回退。全部中断记录保留。

## 4. HTTP 与 PostgreSQL 逐笔对账

Android家庭：`41`个operation_id唯一，draft唯一；各自恰有一个decision和business_event，用户/家庭/事件ID与持久receipt一致。动作分布 {'ADD': 4, 'MOVE': 4, 'CONSUME': 29, 'PLAN_ADD': 4}。纸巾 `200.000000→171.000000`，Consumed合计29；取消4条不关联成功operation。
HTTP独立家庭：动作分布 {'ADD': 1, 'MOVE': 1, 'CONSUME': 3, 'PLAN_ADD': 1}；纸巾 `200.000000→197.000000`，3个Consumed各扣1。采购项1条、quantity=2、is_checked=false；取消1条无写入。OPEN/DISCARD均没有成功operation。
对账器检查：operation/draft唯一，事件/decision一一对应，receipt scope/event_ids一致，MOVE数量不变且版本+1，CONSUME前后数量差=事件quantity且版本+1，采购项数量/状态与事件匹配，所有纸巾扣减之和=最终实际库存差。完整逐笔operation_id与真实前后JSON见两个 reconciliation.json；不是只凭HTTP committed判断。

HTTP原始JSON级证据不包含Authorization或登录口令，认证请求体不归档。HTTP和Android使用各自新合成家庭，旧阶段数据库记录/卷/预算账本未清理。

## 5. 延迟、资源与容量

以下单位ms。P50=中位数，P95=nearest-rank；保留最大值，不删除冷启动或慢样本。

| 测量边界 | N | P50 | P95 | 最大 |
|---|---:|---:|---:|---:|
| Android消息HTTP，含目标预检 | 20 | 498.960 | 769.856 | 781.520 |
| Android草稿读取HTTP | 20 | 153.135 | 205.146 | 254.694 |
| Android确认HTTP，含预检 | 20 | 352.142 | 533.594 | 613.728 |
| Android库存和清单刷新 | 20 | 447.678 | 577.252 | 686.051 |
| Android消息→回执→刷新（无人工停留） | 20 | 2372.808 | 2862.905 | 3038.650 |
| SSH回环双用户消息（并发2） | 20 | 459.769 | 1102.527 | 1128.543 |
| 独立helper execute+PG commit | 20 | 17.801 | 56.952 | 59.281 |
| 独立helper纯RuleEngine.extract | 100 | 0.062 | 0.139 | 47.635 |
| 完整Compose旅程测试方法边界 | 2 | 19883.500 | 20580.000 | 20580.000 |

事务微基准使用新合成演练库，排除建任务/草稿和加载用户耗时；纯解析不含工具/网络/数据库。Android20次是实际模拟器→SSH→Backend→AI→内部工具→PG的自动操作，未包含人的打字/思考。完整Compose旅程仅浅/深两次，N=2不足以承诺产品SLA，不能把其P95当稳定生产分位数。AI纯解析首次47.635ms保留在最大值，未冒用第二阶段DeepSeek模型P95。

资源预算：既有隔离backend320MiB、memswap总512MiB，AI160MiB、PG192MiB均保持原设置。PG验证容器192MiB/0.5CPU；种子/对账/事务helper160MiB/0.5CPU；parser96MiB/0.5CPU；旧08回退128MiB/0.5CPU。所有全量AI、后端unit和Android构建在本地；服务器作业串行。种子、pytest及对账从未注入被测backend容器。短暂运行源码哈希/健康只读探针发生在负载采样前。

最终72次5秒采样：backend采样最大125.660MiB、cgroup生命周期峰值128.793MiB；AI采样最大70.070MiB；主机可用最低287.840MiB。双用户窗口24次2秒采样：backend最大124.367MiB，AI最大70.805MiB；backend两秒CPU口径最大46.356%单核、AI38.513%；host可用最低300.109MiB。两窗口memory.events的oom/oom_kill/max均0、Swap用量0。服务重启计数0；最终11容器healthy。

72样本窗口含完整联合验收及其收尾；24样本窗口含受控双用户调用及空闲尾部。它们是采样值，非无遗漏瞬时业务峰值；cgroup lifetime peak另列。helpers虽在独立容器，仍共享ECS资源，故不把宿主CPU归因全部归给用户业务。旧24次受辅助进程污染的P5采样仅作为P5.1历史证据，不并入本轮新样本。

当前2vCPU/约1.6GiB主机能完成本轮受控rules并发；多次容量门禁说明余量有限。P5.1曾有主机级IO压力及SSH限流，本轮未复现不等于已证明生产峰值容量。仍需阿里云历史IO/CPU/内存告警核查、长期资源预算与负责人审批；不能据本轮就提高生产限制或认定可长期并行跑全量回归。

## 6. 安全、兼容与Lint

Bearer鉴权、家庭成员/归属、双修订、expected_version、edits白名单、稳定request_id/operation_id、持久回执恢复及锁顺序已由源码审查、unit/PG/HTTP/Android交叉验证。版本冲突不自动替换版本后确认，404不生成新操作ID，注销只解除活动账号绑定；outbox按服务地址/用户/家庭隔离，未清空历史。

configuration-final.json：两种服务令牌已配置且双方一致，AI_SERVICE_URL/BACKEND_BASE_URL固定内网，AI无DB密码，第三阶段为rules且无模型Key。没有将密钥打印、写入源码/日志/报告。最终空闲PG连接2条、无遗留idle-in-transaction；单元checkedout=0与20次双用户实际工具调用补充证明连接释放。

Debug仅允许HTTP回环开发通道并要求0.9.0/isolated=true/正确能力；Release要求经配置HTTPS origin、系统TLS验证、isolated=false、同协议版本与用户Bearer；旧0.8及未配置origin均拒绝写入。未删除目标身份检查，未关闭证书校验。Release manifest cleartext=false、allowBackup=false、无Harness；DEX未含测试URL/服务Token/模型Key字段。凭据仍用AndroidKeyStore AES/GCM，未放聊天缓存。

Lint本轮Debug 0 Error/27 Warning，Release 0 Error/26 Warning。逐项位置和处理见 lint-current-classification.md，未关闭检查：ApplySharedPref 2项为同步持久化性能/生命周期风险，保留先落盘后发送语义；OldTargetApi 1项兼容性风险；ModifierParameter6、UnusedResources7、UseKtx8共21项为原有可接受维护/布局建议；UseTomlInstead2与Debug NewerVersionAvailable1为未来维护。P5已修复的6项仍保留修复，品牌资源未删。

正式HTTPS未完成：ECS nginx/caddy/apache2检查均inactive、未发现sites-enabled/conf.d域名/TLS公开指令，Release origin为空。这不证明组织不存在域名，只表示本轮没有可验证的已批准正式入口。unsigned Release无签名流程证明；adb仅MuMu虚拟设备，不能当物理真机。

## 7. 冻结数据问题

AI664项中两个真实失败完整保留。frozen-audit.json 从Git原始blob得到P1 LF sha256 fe68789aef995b6b1dc3f7a6beab7ba416fe18992e5cac70e73b20e93a7aa960，P2 LF sha256 305801600139be80c25bb4609ca9ada93440b00144ac93caae39eaaafa4aee30。仅在内存将LF转CRLF，分别精确匹配旧manifest的f3f223bc…/d47647da…。core.autocrlf=true，无专用attributes；manifest source=ai_constructed、human_reviewed=false。

没有修改历史样本、manifest或断言。frozen-data-proposal.md 提供新独立版本目录、明确字节/EOL策略、内容摘要与来源/审阅人provenance、双平台验证，或限期签署豁免的方案。数据负责人尚未批准：**WAIVER_REQUIRED / RELEASE_BLOCKER**。这两项不能改成PASS。

## 8. 发布与回退准备（本轮不执行生产命令）

release-candidate.md 保留正式操作手册；p52-production-runbook.md补充本轮digest、实际演练、准入及回退步骤。0007仅新增draft_operations/draft_decisions/business_events及约束/索引，兼容0006，不重写旧库存/任务。

最终合成库 `magicvvu_p7_rc_28b5bb7b` 及恢复库均保留；备份sha256 `27698c54a0845c094d557f1e97ed8cb0c36acb04417a16b4d4a8c8b13649b978`。升级前后七张旧表摘要一致，pg_restore实际恢复成功，alembic check退出0，旧0.8真实读取新增schema，旧0.8临时服务在该库health成功且正常停止。备份是合成数据，不能据此宣称生产备份已验证。
演练首次提交1条ADD，资源门禁恢复后未重复执行；后续事务性能单独再产生20条合成ADD，其数据库是同一个专用演练库。rehearsal.json里的“2条库存/1条operation”是恢复验证当时的快照，不是微基准之后当前总量。

Alembic check保留旧 inventory_items/shopping_list_items 环形外键排序SAWarning，属于后续SQLAlchemy/Alembic升级风险。本轮未为了通过改变旧约束。

正式发布需先完成受控生产备份及独立恢复验证、记录旧image/config hash，再一次性升级0007、按digest仅切换backend/agent、HTTPS与Android配置、专用家庭冒烟及逐笔对账。须用户另行授权生产迁移和业务写入。存在正式回执后不允许drop/downgrade三表；应用回退保留0007与审计账本，数据库恢复可能丢失备份后业务，必须保全WAL/最新备份和回执、另行批准恢复点。

本轮隔离回退可使用保留的旧 draft-v0.9-test / p7-rc-04f930a-r2 镜像，限定project=magicvvu-p7-execution-20261017，保留卷；这只是操作手册，不会在报告完成后自动执行。当前隔离服务继续运行最终候选供审阅。

## 9. 风险、阻塞与第六阶段条件

| 等级 | 项目 | 状态/所需条件 |
|---|---|---|
| 高/发布阻塞 | AI冻结样本摘要与provenance | 数据负责人批准新版本或正式限期豁免；保留原失败 |
| 高/发布阻塞 | 正式HTTPS/发行签名/物理真机 | 提供经批准origin及公信证书验证环境、安全签名流程、授权物理设备；完成真机字体/键盘/小屏/网络切换/后台恢复 |
| 高/发布阻塞 | 生产容量与备份 | 审核ECS历史IO/SSH事件、长期预算及真实备份恢复；本轮受控结果不能替代 |
| 中/审阅门禁 | 候选overlay尚未进入团队提交；验收harness有快照后修正 | 审阅team-review.patch与清单，在授权流程固定提交/CI；未自动push |
| 中 | 既有环形FK与OldTargetApi | 保留迁移/系统兼容跟踪，不能静默忽略 |
| 中 | 自动规划、公开引用未交付 | 功能继续关闭；本轮没有真实自动规划Android完整提交证据 |
| 低 | 同步SharedPreferences、UI原始错误码/六位小数显示 | 后续性能/可读性改进，不改本轮持久化安全语义 |

**进入第六阶段还需要：** 数据处置签署；正式HTTPS与证书、签名流程及真机验收；生产容量/备份/回退方案负责人审核；团队固定最终候选提交并确认验收harness增补；用户明确批准正式发布。当前没有新的重复扣减、越权或库存事件不一致证据，但不足以解除上述发布门禁。

## 10. 证据完整性与停止状态

完整测试日志/XML、HTTP原始脱敏JSON、直接PG前后快照/逐笔对账、性能数组、资源采样、运行源码哈希、镜像/APK清单、修复前后日志、审阅补丁和runbook均在同名附件目录。public-evidence.zip仅含可分享脱敏副本，public-evidence-manifest.json可校验SHA256；不包含fixture-private、密码、Token、数据库dump、Keystore、源码缓存或outbox。私有合成测试凭据仅作本机运行资料保留，不进入交付证据包/Git。

收尾：11个既有生产/测试服务healthy；生产及第二阶段8个容器的ID/镜像/启动时间/重启数不变，第三阶段db原ID/卷保留。仅本轮隔离backend/agent替换为候选；PG验证和回退临时容器均已退出，历史失败容器/日志保留。未见pytest/迁移/资源采样在途作业；保留正常服务、用户SSH会话及仅本机18083开发隧道。无自动下一阶段、生产变更或发布。
