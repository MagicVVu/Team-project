# 后端与 P8 AI 接入说明

2026-10-24。本次完善现有后端，新增规划事实录入、持久化和 AI 读取接入。会话续接、可信引用、草稿文字修改/取消、执行预览和 OPEN/DISCARD 复用仓库已有实现。

后续已按用户授权完成正式部署：后端运行 `magicvvu/backend:p8-771374b-20261024`，数据库 0010，P8 预检通过。见 [正式部署记录](deployment-20261024.md)。下文和原 `validation.json` 记录功能实现及部署前的隔离验证，不将其历史 `production_deployed=false` 视为当前状态。

## 接口与能力

完整候选契约见 [backend-openapi.json](backend-openapi.json)。原消息四字段、澄清九字段、确认和操作回执接口继续使用。App 先读取 `GET /api/v1/agent/execution-capabilities`，按 `conversation_protocol`、`chat_controls`、`execution_preview`、动作开关选择入口；`planning_facts_protocol=backend-planning-facts-1` 表示可录入以下资料。

| 用途 | 接口 |
|---|---|
| 同一任务自然语言补充 | `POST /api/v1/agent/conversation-messages` |
| 可信批次引用 | `POST /api/v1/agent/reference-messages` |
| 修改/取消待确认草稿 | `POST /api/v1/agent/tasks/{task_id}/chat-control` |
| 执行前重新校验 | `POST /api/v1/drafts/{draft_id}/execution-preview` |
| 正式确认、取消 | `POST /api/v1/drafts/{draft_id}/commit`、`/cancel` |
| 恢复执行结果 | `GET /api/v1/operations/{operation_id}` |
| 读取、编辑规划事实 | `GET/PATCH /api/v1/households/{household_id}/inventory-items/{item_id}/planning-facts` |
| AI 读取一致快照 | `GET /internal/v1/planning/context` |

## 新增事实接口

使用用户 Bearer 身份及当前家庭权限。先 GET 获取 `inventory_version`、`facts_version`（未录入为 0）；再 PATCH。数量以 JSON 字符串发送。

```json
{
  "operation_id": "11111111-1111-4111-8111-111111111111",
  "expected_inventory_version": 3,
  "expected_facts_version": 0,
  "source": "家庭成员根据盘点和日常登记核对",
  "preferences": {
    "minimum_stock": "8",
    "coverage_days": 14,
    "lead_days": 2,
    "order_unit": "盒",
    "pack_size": "1"
  },
  "stock_verification": {"quantity": "5", "unit": "盒"},
  "coverage": [{
    "day": "2026-10-22",
    "records_complete": true,
    "stockout": false,
    "unexplained_adjustment": false
  }],
  "risk_facts": {
    "category": "food",
    "label_date_type": "use_by",
    "label_context_valid": true,
    "storage_condition": "refrigerated",
    "label_storage_condition": "refrigerated",
    "is_opened": false
  }
}
```

例中的版本、数量、日期和标签适用性必须来自实际核对。标签有效要求库存已有标签日期；开封日期继续由 OPEN 业务处理。`pack_size` 表示一个订货单位包含多少当前库存单位。未设置的偏好保持 null；不填默认预测周期。

- PATCH 只修改显式提供的区块。`preferences`、`stock_verification`、`risk_facts` 区块内部为完整替换；区块传 null 可清除。`coverage` 按日期合并，撤销某天时明确传 `records_complete=false`，不能用空列表冒充完整记录。
- 每次最多提交 366 天，总计最多保存 3660 天；只接受已经结束的家庭业务日期。`stockout`、`unexplained_adjustment` 都必须明确填写。
- 操作者、核对时间、库存绑定、证据摘要均由服务器记录。请求不能伪造这些字段。
- 盘点数量必须与当前库存数量及单位一致。不同返回 `STOCK_COUNT_MISMATCH`，需先通过现有库存接口核对并修正库存，再重新盘点。
- 资料与库存分别有版本。冲突返回 `INVENTORY_VERSION_CONFLICT` 或 `PLANNING_FACTS_VERSION_CONFLICT`；读取最新值后由用户重新核对。相同 operation_id 与相同请求返回原回执；更换内容返回 `OPERATION_ID_CONFLICT`。重放也重新检查当前权限。
- 资料写入返回 `inventory_written=false`，不会创建消费/丢弃事件、修改数量或替用户提交草稿。回执历史与 GET 当前资料区分使用。

## AI 如何使用

规划读取在同一 PostgreSQL 只读一致快照中读取库存、事件、待购和新增资料。快照标识包含资料版本，字段变动后 AI 的旧规划选择不会继续引用旧依据。

- 库存版本改变，旧盘点证明失效；AI 还会按核对时间执行自己的新鲜度检查。
- 名称、单位、原最低库存改变，相关补货偏好失效；标签、位置、类别或开封事实改变，旧风险资料失效。
- 某天的事件或已记录调整发生变化、业务时区变化，对应完整性声明失效。返回 `invalidated_sections`；失效日按记录不完整处理。没有声明的日期仍是未知，不能由“没有消费事件”推断零消费。
- 风险字段同时进入 AI 库存读取和规划快照，使用现有 P2/P8 扩展 Batch 契约。部署需使用当前 P8 AI；历史纯 P1 读取器不支持新增风险字段。
- 正式消费事件、至少 14 个连续完整日及足够消费次数满足 AI 自身条件后，可以给出预测。数据不足仍返回原因。补货建议还受共享待购完整性、有效盘点和风险判定限制。
- `automatic_planning_commit` 继续为 false；自动计算建议尚不具备完整提交前业务重算，不应直接转成用户明确数量的采购确认。人工审核风险规则当前仍由 AI/业务侧维护。

日期按服务端 `MAGICVVU_HOUSEHOLD_TIMEZONE`（默认 Asia/Shanghai）解释，能力接口返回该值。旧消息 DTO 保留 `household_timezone`，新建任务提供不同值会返回 `HOUSEHOLD_TIMEZONE_MISMATCH`；既有任务/回执可继续恢复。切换时区会使已记录覆盖声明需要重新核对。

## 迁移与发布

新迁移 `20261023_0010` 从 0009 追加两张表：`inventory_planning_facts` 与 `planning_fact_writes`。从线上 0007 升级会依次执行 0008（会话）、0009（开封/丢弃）和 0010。不会回填虚构消费、覆盖天数或盘点证明。存在资料/回执时禁止破坏性降级；应保留新 schema，仅回退应用。

候选构建上下文仍为 `backend/server`，应用版本保留 0.9.0 以匹配 Android 当前兼容表；用能力协议区分功能。部署配置样例见 [p8.env.example](../../backend/server/p8.env.example)。上线须沿用当前认证/家庭功能、数据库卷、内部服务令牌、AI 供应商配置与累计预算账本。

发布步骤：备份并验证恢复 → 在隔离环境升级到 0010 并检查 `alembic check` → 构建并验证候选 → 维护窗口迁移正式数据库、更新后端 → 开启已验收的引用/OPEN/DISCARD 开关 → 运行 `python -m app.p8_preflight` → 最新 App 联验。预检只检查固定路由、P8 AI 契约、内部认证和数据库结构，不调用模型或写业务数据。

## 验证

新增用例覆盖权限、严格输入、版本冲突、同请求重放、区块清除、历史变化失效、真实 AI HTTP 读取与统计、预测/补货计算、迁移保留数据与拒绝证据丢失、PostgreSQL 同键/不同键并发。

可复跑：

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend/server/tests --basetemp=.cache/backend-alignment-tests
.\.venv\Scripts\python.exe tools/p72_local_postgres_tests.py --stage p8
.\.venv\Scripts\python.exe tools/export_backend_ai_contract.py
```

最终结果见本目录的验收文件；测试使用合成数据，设备 UI 和正式环境发布需要单独验收。

最终 PostgreSQL 回归：369 通过、0 失败，16 项实际 Nginx 网关用例因未配置 `P8_NGINX_EXE` 跳过；所有 PostgreSQL 并发用例均执行。SQLite 完整回归为 345 通过、37 跳过，另有新增预检 3 项通过。两种数据库的用例重叠，不将通过数量相加。

首轮 PostgreSQL 出现一项旧测试跨午夜失败：UTC 的记录日期与 Asia/Shanghai 的开封日期直接比较。已将断言统一到家庭时区，保留 `postgres-initial-*` 证据，最终整套回归通过。新增生产代码未因此改动日期或事件语义。SQLite 对应案例也已单独复跑通过。
