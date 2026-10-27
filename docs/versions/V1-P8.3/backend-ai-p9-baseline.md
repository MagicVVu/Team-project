# V1-P9 后端与 AI 基线

核查日期：2026-10-26（Asia/Shanghai）。原始脱敏证据：[production-baseline.json](../../../reports/backend-ai-p9/production-baseline.json)。可复核脚本：`tools/p9_baseline.py`。

## 实际线上状态

| 项目 | 实测 |
| --- | --- |
| SSH | `ssh magicvvu`，用户 admin，主机 iZ7xvftxzwe1mwbso1ovyyZ |
| 部署目录 | `/srv/magicvvu/magicvvu-starter` 存在；不是 Git checkout |
| Compose | `deploy/compose.yaml` 存在，需现有 sudo 只读权限 |
| 后端 | `magicvvu/backend:p82-05fa3203a7cb`，healthy，V1-P8.2 |
| AI | `magicvvu/agent:p82-05fa3203a7cb`，healthy，V1-P8.2，DeepSeek |
| DB | PostgreSQL 17，healthy，Alembic `20261023_0010` |
| 现有入口 | `0.0.0.0:8000 → 容器8443`；HTTP仅 `127.0.0.1:8001 → 容器8000` |
| 人工规则 | `active_human_rule_count=0`，保持未知，不改健康声明 |
| P8 只读预检 | 13/13 通过，未调用模型、未写业务数据 |
| 日志采样 | 最近30分钟最多300行/容器；AI73行，无Traceback/FATAL；另两个容器无采样行，不能推断没有历史错误 |

线上镜像保留旧 OCI revision 标签，不能把旧标签当作实际源码 HEAD。只读提取后端 `/app/app`、Alembic 与本地更新后源码逐个 Python 文件比较，归一化换行后 **无差异**。运行代码对应 `backend/server/app`，不是仓库根目录的 `app`。

## Git 与工作保护

实际开发仓库是本地 `Team-project/`，与外层工作目录的 Git 状态分开。初始本地 `dev=32b043c`，只存在未跟踪的原报告 `reports/backend-ai-audit-20261025.md`，已原样保留。外层仓库存在大量原有删除/冲突状态，本任务没有处理或暂存这些文件。

fetch 后 `origin/dev=90594f8`；本地安全快进至该提交（其中 `394ce45` 为 P8.2），随后按本次用户要求创建 `codex/backend-ai-p9`。未覆盖队友文件，未改 AI 源码，未推送。服务器部署目录没有 `.git`，所以服务器 Git 分支、未提交修改及 upstream 差距应记为“不适用/不可从该目录验证”，不能编造一个线上分支。

## 当前能力与确认缺口

六类操作 ADD/MOVE/CONSUME/PLAN_ADD/OPEN/DISCARD、可信引用、手工来源保存、全部消费保护、会话恢复、执行反馈和规划资料接口均已存在，不重新实现。

检查到的 P9 扩展点：

- ShoppingItemUpdate 缺少来源字段；新增采购与 PLAN_ADD 已能保存来源。
- 原来的 `pending_complete=false` 已能表达未知来源；不能称其为“错误当零”的既有后端实现。需补三态解释并拒绝不能换算的来源数量。
- 现有库存仅有稳定批次 UUID；没有商品表或跨批次显式身份。
- BusinessEvent 已持久记录草稿执行，不能另造一套重复草稿执行账本。普通 CRUD 依赖30条 history_json，需扩展现有账本。
- related_event_id 尚未支持；风险规则为零，商品匹配也未闭环。
- 自动采购确认有明确关闭保护，属于未开放能力，非通信故障。

## 阶段 A 验证

本地 P8.2、合成家庭的完整后端回归：392 PASS、37 SKIP、2 FAIL，证据 `reports/backend-ai-p9/baseline-backend.xml`。失败项为 P8.1/P8.2 历史 OpenAPI 快照与当前 Pydantic Decimal schema 输出差异。它们不是线上业务失败；原始失败证据保留。P9 契约导出测试将检查 P9 候选文件，历史版本文件不重写。

首次受限运行还遇到默认临时目录权限及本机测试套接字阻塞；改用工作区专用临时目录和允许本机通信的隔离执行后得到上述真实结果，未放宽业务认证。

专用家庭的完整业务流程在本地隔离数据库和项目原有 RuleEngine 中执行；本轮未创建生产测试家庭，未在生产调用付费模型或写会话/库存。线上端到端写入验收须单独授权，不能由只读预检代替。
