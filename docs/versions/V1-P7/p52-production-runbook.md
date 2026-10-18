# V1-P7 P5.2 发布与回退操作手册（待授权，未执行生产步骤）

状态：NO-GO。配套报告 p52-final-acceptance.md。当前应用构建快照 843c6855920cbd04c1af071a6340a9f5a468d02103a340d0cf2b177ea0cb23e3，基础 dev 04f930aabe087962aa4065bf33e7a4da1a5d443f；overlay 尚待团队审核固定提交。不得直接把本文件当自动部署脚本。

## 1. 发布前必须补齐

- 数据负责人批准冻结样本新版本或签署有期限/范围的豁免，保留当前 2 个失败。
- 审阅完整 team-review.patch、源清单、验收脚本增补；通过团队流程建立最终提交和 CI 证明，不强推 dev。
- 配置经批准的正式 HTTPS origin、公信证书及续期监控；验证主机名、证书链、登录和业务契约。
- 由受保护流水线管理发行签名；不把私钥、口令写入源码/报告或聊天。unsigned Release 不能发行。
- 授权物理 Android 设备完成字体缩放、小屏、键盘、网络切换、前后台及进程恢复验收。
- 审阅当前 2vCPU/约1.6GiB ECS 的生产容量、历史 IO/SSH 事件、长期预算与告警。禁止在共享主机并行全量回归。
- 完成真实生产备份、独立恢复验证及负责人审核；取得用户对生产迁移、容器切换、专用家庭烟测写入的单独授权。

## 2. 目标与构建物

生产目录 /srv/magicvvu/magicvvu-starter 不等于仓库根目录；运行源码由 backend/server 构建，AI由 agent/Dockerfile.conversation 构建。实际 AI 入口：

```text
python -m uvicorn conversation.app:create_app --factory --host 0.0.0.0 --port 8767
```

服务器本地已构建、仅隔离运行：

```text
magicvvu/backend:p52-843c6855920c
magicvvu/backend@sha256:abd576f9b98a45f2484184b39324033976ee19a39654529b0861a13bd696c687
magicvvu/agent:p52-843c6855920c
magicvvu/agent@sha256:6f650a872f18fc368e1d93bffb96c2fb6d9b9928fc0b7e70a783cc7142bd42c8
```

尚未推送镜像仓库。生产前应以批准提交、受信基础镜像和锁定依赖在受控流水线构建/扫描/留存 SBOM，核对平台和最终 digest；不得只凭标签存在切换服务。

## 3. 状态采集与备份

授权后先严格校验 SSH 主机密钥，记录 id、uptime、free、df/inode、docker ps/stats、容器 ID/镜像 digest/健康/重启/OOM/网络/卷、生产配置文件 hash。只输出必要投影，禁止完整 inspect/env/compose config 输出。核对生产 Backend 0.8.0、isolated=false、PG 0006。

备份模板仅供审查：由受控运维会话使用容器内既有 POSTGRES_USER/POSTGRES_DB，不把密码放命令参数或日志。将 pg_dump -Fc 二进制流写到受限备份目录，记录 UTC、源迁移、PG17工具版本、大小、SHA256、保留期限和责任人。示意：

```bash
# PROD_DB、CONTROLLED_BACKUP 只能由负责人填写经核实的正式目标；本阶段未运行。
docker exec "$PROD_DB" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$CONTROLLED_BACKUP"
```

pg_restore --list 只证明可解析。必须在另外授权的独立 PG17 恢复实例执行 pg_restore --exit-on-error，核对旧七表计数/摘要、迁移0006、应用只读查询。恢复实例不得挂载生产卷；真实生产数据复制/访问也须明确授权。本轮仅使用合成数据完成恢复，不能代替真实备份验收。

## 4. 迁移和服务切换顺序

1. 冻结已审查提交和产物，记录旧 backend/agent image digest、配置 hash、账本备份与准确生产 Compose project/service。确认容量足以容纳过渡服务，禁止自动加大生产配额。
2. 暂停新确认入口并等待在途事务结束；保留 GET 回执恢复，不清空 outbox、operation 或预算账本。
3. 使用新后端镜像及既有受保护配置运行一次性 `alembic upgrade 20261017_0007`，不要在应用启动中隐式迁移。核对只新增三表、旧数据保留及迁移事务状态。
4. 明确仅切换生产 backend/agent，保留原 db 与卷。后端仍仅宿主回环127.0.0.1:8000；AI不发布公网端口。不要 down -v，不绑定开发源码目录。
5. AI_SERVICE_TOKEN双方一致且满足长度，BACKEND_TOOL_TOKEN双方一致；AI_SERVICE_URL=http://agent:8767、BACKEND_BASE_URL=http://backend:8000。仅在私有配置机制中使用现有值，不重新生成或复制到普通文件。AI不能取得数据库密码。
6. 初始可使用 `P3_ENGINE=rules`；DeepSeek切换另核对已有配置、预算/账本持久化及历史评测，不重复付费压力测试。保全旧P1缓存和账本，审核格式兼容/路径映射后再接入P7，不删除来绕过预算。
7. 健康核对 Backend0.9.0 / isolated=false、AI OpenAPI0.7.0 / V1-P7、PG0007、真实启动入口、只读根文件系统/非root/cap drop、服务间认证、内网工具回读。
8. 用户Bearer下发现 draft-execution-1 / business_backend；仅ADD、MOVE、CONSUME、手动PLAN_ADD开放。OPEN、DISCARD、自动规划确认、公开受信引用保持关闭。
9. 在专用生产合成家庭执行四动作、查询/澄清/取消、同键恢复和跨家庭拒绝，逐笔对账事件/回执/真实库存。生产烟测业务写入须包含在单独发布授权内。
10. Android按经批准正式origin构建Release，例如 `-PmewstowReleaseApiUrl=https://<已批准域名>`；系统TLS校验不得关闭。正式后端仍0.8时发行客户端写入继续关闭。签名后在物理设备验证最终包，才进入用户渠道审批。

## 5. 回退与数据保护

应用故障先停止新增确认并保全回执恢复，收集在途事务/operation_id；仅回退批准的旧应用镜像和受控配置，**保留0007三表与全部审计记录**。旧0.8在本轮合成0007库的真实读取和临时启动健康均通过；旧版本不认识新执行能力，需关闭新AI确认入口，不能伪称新消费事件不存在。

0007只新增 draft_operations、draft_decisions、business_events；存在任何回执/决策/事件时 downgrade 明确拒绝。禁止删表、清空ledger或重置迁移版本。恢复备份会丢失备份后提交，须保存WAL/最新备份、逐笔核对回执和库存，制定恢复点并另行授权，不能自动执行。

隔离环境如需回退：只限定 project=magicvvu-p7-execution-20261017，以旧 draft-v0.9-test 和 p7-rc-04f930a-r2 的已保存digest及独立override切换 backend/agent，保留db/缓存/历史结果卷。不得用于 magicvvu-starter。若重建导致IP变化，重新核验自建18083隧道目标，不能复用历史IP或覆盖生产隧道。

## 6. 本轮实际演练证据

合成库 magicvvu_p7_rc_28b5bb7b 及恢复库保留。0006备份实际恢复、0007升级后旧表摘要、alembic check、旧08读取通过。一次ADD后资源门禁暂停，恢复时未重复提交，降级保护正确拒绝。随后20次事务微基准只写该合成演练库。另一个128MiB旧08临时服务实际health=0.8.0/isolated=true，正常停止、无OOM、无端口发布。

证据见 rehearsal-attempt.log、rehearsal.json、rehearsal-resume.log、startup-rollback.json、transaction-performance.json。alembic check仍有旧inventory/shopping环形FK的SAWarning，需保留后续维护跟踪。
