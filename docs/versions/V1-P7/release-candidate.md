# V1-P7 第五阶段候选与第六阶段发布手册

此文件是发布准备，**不是上线授权**。没有执行任何生产迁移、业务写入或生产容器切换。基准为 dev `04f930aabe087962aa4065bf33e7a4da1a5d443f`；第五阶段修复仍是本地 overlay，必须完成团队审查并固定新的提交、镜像 digest、APK SHA256 后才能发布。

## 候选变更与兼容契约

- Android `TargetPolicy`：Debug 写入要求服务名 magicvvu-backend、版本 0.9.0、isolated_test=true；Release 要求编译配置的正式 HTTPS 根地址、0.9.0、isolated_test=false。两者均验证 draft-execution-1 / business_backend。旧生产 0.8.0 不能执行写入。版本未来升级要更新并测试兼容表，不能仅放宽为任意版本。
- Release 没有正式地址时网络功能关闭。`mewstowReleaseApiUrl` 只接受 HTTPS；不得把 Debug tunnel 参数当成 Release 参数。TLS 使用系统证书与主机名验证，不安装信任全部证书逻辑。
- Release manifest 禁止明文 HTTP，不包含 Debug Harness Activity。当前 unsigned APK 只做静态检查；没有读取正式签名私钥。
- 消息在能力预检前先保存 request_id 与原 JSON；操作确认保存 operation_id 与不可变 JSON 后才发送。恢复只自动 GET，重新 POST 需要用户明确动作并复用原内容。
- 退出登录只解除活动身份绑定，保留原账号/家庭 outbox；凭据仍由 Keystore AES-GCM 保护。缓存不可读、作用域切换、版本冲突均停止自动执行。
- rules 增补精确位置库存问答、明确来源位置的 MOVE，以及“库存有什么”。保留原文、批次范围检查、多批次澄清。没有把不支持的“买两包纸巾”改写为另一指令。
- 网关在 commit 使 ORM 属性过期前保存 user_id / household_id / original_text，避免在等待 AI 内部回调时重新占用连接池。新增测试检查消息和澄清回调期间连接已经归还。不能通过增加连接池掩盖这个问题。
- OPEN、DISCARD、自动规划确认、公开可信引用继续不可执行。公开引用 503；规划依据不能删掉来制造可提交草稿。

## 生产变更前必须补齐

1. 第五阶段最终报告的 FAILED / BLOCKED 项全部获得明确处置。必须重新取回服务器候选测试、健康、迁移与源码 hash，不能把 SSH 中断期间未知的结果视为通过。
2. 完成授权物理设备验收。目前 emulator-5554 是 x86_64 模拟设备，伪装型号不能作为真机证据。
3. 提供正式 HTTPS 域名、TLS 证书与反向代理方案、受保护的配置注入方式、正式应用 ID/versionCode/签名发布流程。候选没有正式 URL，也没有正式签名。
4. 数据维护者解释 P1/P2 样本 manifest 的 CRLF 摘要与 Git LF blob 不一致问题。保留旧样本/manifest/断言，提供新的版本化数据及 provenance/双平台再现证据，或书面批准历史问题的发布豁免。禁止用 Git 导出时碰巧转为 CRLF 的全绿结果替代仓库字节验收。
5. 审查认证暴露面：手机号未验证只是登录标识；保持 AUTH_ALLOW_UNVERIFIED_SIGNUP=false，公网入口要有既有登录保护/限流和业务批准的身份策略。不要本轮顺便开放注册。
6. 审查容量：测试后端 192 MiB 下发生 OOM 137，特别是同时在同一容器执行种子/验证脚本会计入 cgroup。隔离环境已尝试 320 MiB；必须结合实际采样与主机总内存重新批准生产预算。禁止未经批准直接照搬或扩大生产配额。

## 生产发布前只读采集

由操作者通过 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes magicvvu` 登录，确认 admin 与授权范围。下列检查只读；输出存入受控发布记录。不要执行 `docker inspect` 全量输出、`compose config` 全量输出、`env`、`set -x` 或连接串回显。

```bash
id
sudo -n docker ps --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
sudo -n docker inspect magicvvu-starter-backend-1 --format '{{.Image}} {{.State.StartedAt}} {{.RestartCount}}'
curl --fail --max-time 5 http://127.0.0.1:8000/api/v1/health
sudo -n docker compose -p magicvvu-starter -f <已核实的正式-compose文件> config --services
```

另外仅投影容器 User、ReadonlyRootfs、CapDrop、端口与网络，配置输出只允许名称/存在性/格式/双方是否一致；读取数据库 `alembic_version` 使用已有授权方式，禁止输出密码。核实当前生产 0.8.0 / 0006，保存旧镜像 digest 与配置文件 hash/受控备份。发布镜像从仓库 `backend/server` 构建，不能假定生产 starter 根目录等于仓库根目录。

## 备份与恢复门禁

先核对准确生产数据库名/容器/角色。由受控运维会话将 `pg_dump -Fc` 的二进制输出写入受限备份位置，凭据只在既有受保护环境/容器中使用。备份文件不要放普通报告、Git 或测试镜像。记录时间、源迁移、SHA256、大小与责任人；验证 PostgreSQL 17 的工具版本。

`pg_restore --list` 只证明可解析，**不等于可恢复**。必须在全新、专用且无生产挂载的 PostgreSQL 17 实例创建恢复库，`pg_restore --exit-on-error`，验证核心表计数与摘要、迁移 0006、应用只读查询。恢复失败即 NO-GO。生产数据恢复验证需要独立的数据访问批准；第五阶段仅用合成库完成该演练，没有复制生产数据库。

第五阶段演练工具 `frontend/tools/phase5_rehearsal.py` 只允许全新 `magicvvu_p7_rc_<随机值>` 数据库，保留测试数据库、备份与恢复库。升级前/后七张旧表摘要相同；0.8 可读 0007；已生成正式回执后 downgrade 必须拒绝。`phase5_server_audit.py` 另在合成库启动 0.9/0.8 临时后端（无宿主端口）验证升级和应用回退的健康。

## 迁移 0007 审核

`20261017_0007_draft_execution.py` 仅新增 draft_operations、draft_decisions、business_events 及索引/约束，前序为 20261016_0006。不重写库存、采购或 AI 任务数据。

- operation 主键全局唯一、draft_id 唯一；decision 一草稿一决策，committed 必有 operation_id，cancelled 必无 operation_id。
- 外键 RESTRICT 保护任务、用户、家庭、库存与执行回执；采购项删除可将事件 shopping_item_id 置空，审计 JSON 保留。
- action、revision、Consumed/StockAdded/PlanAdded 正数量、StockMoved 数量为空均有数据库约束。
- 业务事务中 task → draft → membership → inventory/shared list 的锁顺序必须保留；事件、回执和决策在同一事务中提交。
- Alembic check 目前旧 inventory_items / shopping_list_items 存在环状外键排序 SAWarning；不是本次新增结构，但必须作为后续 Alembic/SQLAlchemy 升级兼容项保留，不能忽略成“无警告”。

## 仅在用户另行授权后执行的生产步骤

以下命令是模板；`<...>` 必须先替换为经审查的正式路径和镜像 digest。**第五阶段不得运行。**

1. 固定候选 Git 提交，保存源码与构建物 hash。使用离线已锁定依赖或受信构建流水线构建 Backend/AI，扫描镜像；生产运行时不 bind mount 开发源码。
2. 对外暂停新的确认入口，保留 GET 回执恢复，等待在途事务完成；不要删除任何 operation/outbox。检查备份已完成恢复验证。
3. 使用新后端镜像和既有受保护 DB 配置运行一次性 Alembic 容器，只执行 `alembic upgrade 20261017_0007`。不启动自动业务写入、不自动 downgrade。
4. 保持生产 db 原容器与卷不变。通过已核实正式 compose 基础文件加审查后的 override，切换 Backend 为候选 digest；监听仍仅 `127.0.0.1:8000`。仅切换后端/AI，不 `down -v`。
5. AI 从 `agent/Dockerfile.conversation` 构建，命令必须为 `python -m uvicorn conversation.app:create_app --factory --host 0.0.0.0 --port 8767`，实际 OpenAPI version=0.7.0。不能沿用旧 p1.app。
6. 后端 AI_SERVICE_URL 固定 `http://agent:8767`；AI BACKEND_BASE_URL 固定 `http://backend:8000`。AI_SERVICE_TOKEN 双方一致且至少 32 字符，BACKEND_TOOL_TOKEN 双方一致；通过现有私有机制注入，不重新生成或输出。AI 没有 DB 凭据、写接口或公网端口。
7. 首次生产候选可先 rules 并完成烟测；切换 DeepSeek 需要检查既有私有模型配置/预算/账本持久化与评测证据，不重复付费压力测试、不删除账本。模型引擎变量为 P3_ENGINE，不能猜测成 AI_ENGINE。
8. 健康检查：Backend 0.9.0 / isolated_test=false、迁移 0007、P7 0.7.0、internal network、容器非 root/read-only/cap drop；用户 Bearer 下 capabilities 匹配，OPEN/DISCARD/自动计划/公开引用仍关闭。
9. 在发布专用合成家庭登录，执行查询、ADD、MOVE、CONSUME、PLAN_ADD、取消、同键恢复、跨家庭拒绝；核对正式回执与真实 Consumed 事件、数量和版本一致。此生产烟测业务写入也必须包含在第六阶段明确授权中。
10. Android 命令示例：`gradlew :app:assembleRelease -PmewstowReleaseApiUrl=https://<已批准域名>`。正式签名由受保护发布流水线完成；再次检查 manifest/DEX/配置无调试入口和私密值，并在物理设备上以正式 HTTPS 验收。尚未部署兼容后端时不发布可写客户端。

## 回退

- 发布前保存旧后端/AI镜像 digest。失败先关闭新的确认入口并保留 GET 恢复，然后仅回退应用容器镜像和受控配置；**保留 0007 与全部审计记录**。第五阶段合成库已经演练旧后端读取新增 schema。
- 一旦 0007 存在业务回执，禁止删表降级。旧版不认识 Consumed 事件时应禁用新的 AI 执行入口，不能让旧 UI 宣称事件不存在。
- 恢复备份会丢失备份之后的已提交业务，因此不能自动回滚数据库。需停止新增写入、保全 WAL/最新全备和回执、制定逐笔对账与恢复点方案并取得单独授权。
- 第五阶段隔离环境可用原 `magicvvu/backend:draft-v0.9-test` 和 `magicvvu/agent:p7-test-db55fda` 的独立 override 回退，仅 `up -d --no-deps --no-build backend agent`；保留所有数据库卷、模型账本与历史证据。操作前再次核对 project，绝不能用于 magicvvu-starter。

本手册必须与第五阶段完整报告、原始 XML/日志和最终源文件 SHA256 清单一起审查。缺失证据不是通过。
