# MagicVVu Backend v0.6 — P1 AI 双向对接与只读消息网关

**版本**：v0.6.0　**迁移**：`20261014_0004 -> 20261014_0005`

**输入基线**：已在阿里云上线验收的 v0.5（`magicvvu/backend:ai-read-v0.5`），以及用户提供的队友最新 `agent(1).zip` 中实际 `agent/p1` 服务。完整保留 v0.5 代码、六张业务表、登录、家庭成员及共享购物清单规则。

## 本版本实现范围（不修改库存）

- 新增 `agent` 容器：独立 P1 服务，默认 `P1_ENGINE=rules`，不使用 DeepSeek 付费 API；256 MB 内存限制，CPU 0.65；只在 Docker 内部 `ai_net` 暴露 8767，不映射公网端口。
- `backend` 与 `agent` 之间使用独立 `AI_SERVICE_TOKEN`；`agent` 到 `backend` 查询库存使用沿用 v0.5 的 `BACKEND_TOOL_TOKEN`。用户手机号登录令牌 **只用于 App 到 backend**。
- `backend` 保留已运行 PostgreSQL 的默认网络/卷，仅新增 `ai_net`；`agent` 没有加入数据库默认网络。
- 新增 Alembic `0005`：只新增 `ai_tasks`、`ai_drafts` 两张表；原有业务表不动。
- 新增经家庭鉴权的 `POST /api/v1/agent/messages`、`POST /api/v1/agent/clarifications/{task_id}`、`GET /api/v1/agent/tasks/{task_id}`、`GET /api/v1/drafts/{draft_id}`。草稿只读，**没有 `confirm`/`undo`/库存写入接口**。
- 服务器保存原文、最近 P1 响应、最新澄清 context、修订号、15 分钟过期时间和待确认草稿。App 提交补字段时**只发送 `revision` 和 `answers`**，不允许回传/替换完整 context。
- 同用户、同家庭、同 `request_id` + 同内容返回之前结果，不重复调用模型；不同内容返回 409。并发重复请求被拒绝；处理中的服务器意外退出需等待 30 秒任务租约到期才能重试。
- AI 结果 `needs_confirmation` 始终附带 `inventory_written=false`、`prospective=true`；无任何代码路径会根据草稿更新 `inventory_items`。

## 接口示例

### `POST /api/v1/agent/messages`

`Authorization: Bearer <用户登录令牌>`，JSON：

```json
{"household_id":"真实家庭 UUID","text":"库存有什么","request_id":"android-unique-001","household_timezone":"Asia/Shanghai"}
```

返回包含：`task_id`、`status`、`revision`、`draft_id`（如有）、`result`、`inventory_written: false`。
`result` 中保留 AI 返回的 `reply`、`facts`、`candidates`、`draft` 和 `preview` 等，但 `clarification` 会被替换为仅含 `revision`、`allowed_fields`、`expires_at` 的公开摘要；原始上下文只保存在后端数据库。重复同一 `request_id` 和正文不会再次调用 AI。

### `POST /api/v1/agent/clarifications/{task_id}`

```json
{"revision":1,"answers":{"opened_at":"昨天"}}
```

需满足原任务用户、家庭成员、修订号、过期时间及 `allowed_fields` 限制。由后端从 PostgreSQL 装配完整 `context` 调用 P1 `/agent/clarification`；**不允许 App 发送 `context`**。

### `GET /api/v1/agent/tasks/{task_id}`

获取自己且仍有家庭成员资格的任务，不泄漏其他家庭数据。

### `GET /api/v1/drafts/{draft_id}`

读取草稿/拟议前后对照；`inventory_written=false`。本版本不提供草稿编辑/确认事务。

## Docker 配置

`deploy/.env` **不包含在升级包中**。需要已有：
- `MAGICVVU_DB_ADMIN_PASSWORD`（原有，不更改）
- `MAGICVVU_BACKEND_TOOL_TOKEN`（v0.5 已生成，不更改）
- 新增 `MAGICVVU_AI_SERVICE_TOKEN`（独立高熵密钥，至少 32 字符）
- `MAGICVVU_P1_ENGINE=rules`（明确禁用付费模型）

`agent_cache` 是一个新 Docker 命名卷，承载 AI SQLite 费用账本；**它不是队友电脑上的原有历史账本**。切换至 `deepseek` 前必须核实并衔接已有账本、模型实际名称和最新费率（原定 20 元上限且定价仅允许七天有效），并由用户明确批准。默认不传模型密钥，完全不调用付费接口。非规则模式不包含在本次验收范围。

## 安全与资源说明

- 服务器资源测量：系统约 1.6GiB RAM、`available` ~1.0GiB、2GiB 未使用 Swap，磁盘 31 GiB 剩余；允许低并发的初步测试，但没有真实负载压力测试。
- `backend`/`db` 仍分别有 384MB 内存上限，`agent` 256MB；不应因加容器就开放 8767、8000 或 5432 公网端口。
- v0.4 手机号注册仍默认关闭，尚未验证手机号所有权；不可对外开放自助注册。未配置 HTTPS 时不要让真实外网 Android 直接携带密码/登录令牌访问 HTTP。
- 后端 `/internal/v1/*` 只能通过服务器本地或 Docker 网络访问；后续反向代理必须显式禁止公网转发这个路径。
- 当 AI 上游故障时后端返回 503，不伪造库存事实。短暂 `processing` 状态可在租约到期后按原请求 ID 恢复，不能凭新键绕过实际业务确认。

## 自动化测试（隔离环境）

- `backend/tests`：12 项通过（包括 0005 SQLite 迁移、原有回归、P1 实际协议、同键幂等、澄清和草稿）。
- `agent/tests`：队友交付的 82 项全部通过；没有重新运行付费模型评测。
- 不包含真实 PostgreSQL Docker 构建验收；服务器升级需要按以下阶段执行。

## 服务器分阶段升级指引

**阶段 1 — 只上传、核对、备份，不重启**

在 Windows PowerShell 上传：

```powershell
scp "$env:USERPROFILE\Downloads\magicvvu-backend-v0.6-ai-gateway.tar.gz" magicvvu:~/
```

在服务器执行：

```bash
set +e
umask 077
cd /srv/magicvvu/magicvvu-starter
ls -lh ~/magicvvu-backend-v0.6-ai-gateway.tar.gz
tar -tzf ~/magicvvu-backend-v0.6-ai-gateway.tar.gz > /dev/null
echo "PACKAGE CHECK EXIT CODE: $?"
# 备份目录名字留在屏幕上，后续务必保存该路径
BACKUP="/srv/magicvvu/backups/v06_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
cp -a backend "$BACKUP/"
cp -a deploy/compose.yaml "$BACKUP/"
cp -a deploy/.env "$BACKUP/database-env.backup"
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T db \
 sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
 > "$BACKUP/postgres_before_v06.dump"
echo "DB BACKUP EXIT CODE: $?"
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T db pg_restore -l < "$BACKUP/postgres_before_v06.dump" > /dev/null
echo "ARCHIVE CHECK EXIT CODE: $?"
ls -lh "$BACKUP/postgres_before_v06.dump"
echo "BACKUP DIRECTORY: $BACKUP"
```

**阶段 2 — 只替换源码、设置密钥、构建镜像**

备份成功后再解压：

```bash
cd /srv/magicvvu/magicvvu-starter
tar -xzf ~/magicvvu-backend-v0.6-ai-gateway.tar.gz -C .
echo "EXTRACT EXIT CODE: $?"
```

通过服务器 `python3` 生成独立密钥（不输出、不泄漏）：

```bash
python3 - <<'PY'
import secrets
from pathlib import Path
p = Path('deploy/.env')
s = p.read_text()
keys = [line for line in s.splitlines() if line.startswith('MAGICVVU_AI_SERVICE_TOKEN=')]
if len(keys) > 1:
    raise SystemExit('Duplicate AI service tokens: review deploy/.env locally')
if not keys:
    with p.open('a') as f:
        if s and not s.endswith('\n'):
            f.write('\n')
        f.write('MAGICVVU_AI_SERVICE_TOKEN=' + secrets.token_urlsafe(48) + '\n')
elif len(keys[0].split('=',1)[1]) < 32:
    raise SystemExit('Existing AI service token too short; STOP')
if not any(line.startswith('MAGICVVU_P1_ENGINE=') for line in p.read_text().splitlines()):
    with p.open('a') as f:
        f.write('MAGICVVU_P1_ENGINE=rules\n')
p.chmod(0o600)
print('AI SERVICE TOKEN CONFIGURED; P1 rule-mode requested. Value not printed.')
PY
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
echo "CONFIG EXIT CODE: $?"
timeout 600s sudo docker compose --env-file deploy/.env -f deploy/compose.yaml build backend agent
echo "BUILD EXIT CODE: $?"
```

**注意：如果 `MAGICVVU_P1_ENGINE` 已存在，检查它是否为 `rules`，不能直接切 DeepSeek。不要执行不带 `--quiet` 的 `compose config`（会打印解析后的密钥）。**

**阶段 3 — 数据库迁移 `0004 -> 0005`，先不重启**

```bash
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps backend alembic upgrade head
echo "MIGRATION EXIT CODE: $?"
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps backend alembic current
```

预期 `20261014_0005 (head)`。异常则停止，不使用 `alembic stamp`/`downgrade`/`down -v`。

**阶段 4 — 启动 backend，随后 agent**

```bash
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --no-deps backend
echo "BACKEND DEPLOY EXIT CODE: $?"
# backend healthy 后：
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --no-deps agent
echo "AGENT DEPLOY EXIT CODE: $?"
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml ps
curl -i --max-time 10 http://127.0.0.1:8000/api/v1/health
curl -i --max-time 10 http://127.0.0.1:8000/api/v1/ready
# 无 token 的内部库存请求必须得到 401：
curl -i --max-time 10 http://127.0.0.1:8000/internal/v1/inventory/search
```

**阶段 5 — 不写数据库的 AI 双向连通测试**

```bash
sudo docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T backend python -m app.ai_agent_smoke
echo "AI CONNECTIVITY EXIT CODE: $?"
sudo docker stats --no-stream
```

`P1 HEALTH PASSED`、`P1 -> BACKEND READ AUTH PASSED` 与退出码 0 为预期。该测试使用随机不存在的用户/家庭 UUID，**刻意要求 AI 无权读取库存**。要证明“真实家庭成员查到自己的真实库存”，还需要下阶段用已登录测试用户及已存在家庭执行正向端到端验收。

**本版本故障处理：** 保留备份文件。镜像切换失败时可以按备份恢复旧代码/Compose 并部署旧 backend 镜像；`0005` 两张表无需直接降级即可让旧版 backend 忽略。不要盲目把数据库降级或删除数据卷。
