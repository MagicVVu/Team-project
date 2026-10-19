# P7.1 后端交付后的只读复核

阶段归属更新：本次后端交付与权限复核现统一纳入 [V1-P7.2 阶段行为记录](../V1-P7.2/README.md)。本文件保留旧名称、路径和各次检查的时间状态，供追溯；正式迁移结果以 P7.2 记录为准。

日期：2026-10-19（Asia/Shanghai）。依据用户提供的《P7.1接入记录.md》，并以 `magicvvu_ai` 实际 SSH 连接和 HTTP/Docker 只读检查交叉核对。文档中的部署和 docker exec 命令仅作为交接说明，本次没有执行。

**21:36 后续复核：权限已更新，以下最初的权限限制和未核验事项须结合本次结果阅读。** 新 SSH 会话确认 `magicvvu_ai` 已加入 docker 组，并获得免密 sudo；通过 sudo 已读取 P7.1 交付目录的 README、两份预检源码和 Compose 片段。先审阅脚本确认只读，再运行宿主配置检查，并以 `docker exec -i ... python -B -` 从标准输入执行交付的容器内预检，无源码复制、服务启动或数据库迁移。

执行隔离环境的 11 项连线配置及 11 项容器内预检全部通过，包括 AI 认证、P7/OpenAPI、执行接口、数据库 ready、`20261017_0007` 和 `draft_operations`、`draft_decisions`、`business_events` 三表。这部分现在已有独立实测证据，不再仅依赖后端说明。正式环境的 P7 入口、引擎、版本、路由、迁移和执行表检查仍未通过，符合其继续运行 0.8.0／P1 的现状。

读取权限阻塞已解除；`admin` 直连仍被公钥认证拒绝，但使用现有 AI 账号及新 sudo 权限即可完成此次检查。后端本地 87/5 测试、真实模型及页面正向业务链路未在本轮重跑；DeepSeek 与新版执行环境的合并验收仍待安排。未写业务数据、未调用模型、未改配置或切换服务。见 [完整预检报告与交付源码哈希](evidence/backend-full-preflight-20261019.json)。下文保留最初只读核对记录，供对照权限变化。

结论：后端和部署检查已交付，现有 0.9.0／P7 隔离环境具备继续联调的基础；正式环境尚未切换，不能宣称正式接入完成。

## 权限和实际环境

`magicvvu_ai` 新增 `sudo -n /usr/local/sbin/docker-readonly` 权限，已通过其 ps、inspect 读取容器状态。该包装器允许指定的 Docker 只读命令，不允许 exec、重启或部署；本次未尝试绕过限制。AI 工作区仍可读写，`/home/admin/magicvvu-p71-backend-20261019` 不能由此账号直接读取。

| 环境 | Backend | AI | 实测判断 |
|---|---|---|---|
| `magicvvu-p7-execution-20261017` | 0.9.0，isolated_test=true | P7 0.7.0，rules | 双方 healthy；新版执行接口可见，适合继续隔离联调 |
| `magicvvu-p7-test-20261017` 的 model 服务 | 0.8.0，isolated_test=true | P7 0.7.0，deepseek，已配置密钥与 deepseek-flash | 模型配置可见，后端仍缺新版执行接口；本次未调用供应商验证 |
| `magicvvu-starter` | 0.8.0，isolated_test=false | P1，rules | 正式服务健康，尚未接入 P7；本机 8000 端口属于此环境 |

三组实际配对容器的 `AI_SERVICE_TOKEN`、`BACKEND_TOOL_TOKEN` 均非空且双方一致；`AI_SERVICE_URL`、`BACKEND_BASE_URL` 指向同一网络的对应服务。只输出匹配布尔值，未保存令牌值。

主机 AI 工作区 `.env.runtime` 仍未单独配置两项内部令牌，但运行容器已具备，不构成容器接入阻塞，不需要重新输入或生成令牌。只有单独启动主机进程时，才须补齐该进程的环境。

## 接口与保护边界

0.9.0 隔离环境实际 OpenAPI 已包含：

- `GET /api/v1/agent/execution-capabilities`。
- `POST /api/v1/drafts/{draft_id}/commit`、`POST /api/v1/drafts/{draft_id}/cancel`。
- `GET /api/v1/drafts/{draft_id}/execution`、`GET /api/v1/operations/{operation_id}`。
- `GET /internal/v1/operations/{operation_id}`、`GET /api/v1/households/{household_id}/consumption-events`。
- 原有消息、澄清、任务恢复、草稿和内部库存读取接口。

新增公开能力、执行状态、操作恢复 GET 在未登录时返回 401；库存工具缺令牌返回 401，使用匹配的服务令牌与刻意无效的用户/家庭 UUID 返回 404。说明接口存在并保留访问控制，不等于登录后的正向执行、有效家庭隔离或并发幂等已在本轮通过。

依据后端交付记录，已有执行能力为 ADD、MOVE、CONSUME、手动 PLAN_ADD；OPEN、DISCARD、自动规划确认和受信跨提问引用仍不可用。`reference-messages` 路由虽存在，不能据此视为适配层已实现。三套被查后端均未暴露 `/internal/v1/planning/context`，缺规划数据仍应按 AI 原契约明确不可用。

补充检查确认执行隔离环境的 `/api/v1/ready` 返回 200、database=ok；Backend/AI 为只读根文件系统；AI 显式选择 P7 工厂和引擎，无公开端口、无被检查的数据库配置变量，具有可写缓存卷。这些结果与后端接入记录一致。

## 证据来源和待验证事项

后端记录列出的新预检模块、宿主检查脚本、P7 Compose override 及 87 通过／5 跳过，属于后端提供的交付证据。当前本地仓库未发现这三份新源码，本次也没有读取 admin 目录或执行容器脚本，因此未独立复核其源码、测试结果、迁移 0007 与三张执行表；数据库 ready 不能替代这些检查。

下一步按现有分工推进：

1. 后端保留已有数据库网关和执行层，补齐本地仓库中的预检/部署交付源码；沿用原令牌，不重建秘密。
2. 由部署负责人按已交付 override 在明确的隔离环境安排“0.9.0＋P7＋DeepSeek”组合，核对实际镜像及 P7.1 源码版本，保留缓存与累计预算账本。本次没有构建或切换。
3. 使用合法登录的专用测试家庭完成真实模型、公开网关、批次选择、草稿核对、确认回执及刷新，以及中断恢复、同键重试和并发检查。正向调用会保存任务/执行业务，本次只读复核不包含这些步骤。
4. OPEN、DISCARD 和规划数据/受信引用未实现部分继续保留接口与不可用提示。正式升级仍按生产 runbook 完成备份恢复、迁移和发布验收；历史冻结样本摘要门禁仍保留。

本次未修改运行代码、服务器配置、权限或正式服务，未写库存、创建任务或调用付费模型，未提交或推送 Git。原始脱敏检查见 [复核证据](evidence/backend-recheck-20261019.json)；P7.1 原始交付与测试结果保持不变。
