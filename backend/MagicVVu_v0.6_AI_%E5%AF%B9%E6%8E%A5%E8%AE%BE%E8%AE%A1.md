# MagicVVu v0.6 · AI P1 双向联调设计

## 组件边界

```text
Android App -- Bearer USER_TOKEN --> FastAPI backend:8000
                                       |              ^
                                       | AI_SERVICE   | BACKEND_TOOL
                                       v              | (read only)
                                 agent P1:8767 --------+
                                       
FastAPI backend -- SQLAlchemy --> PostgreSQL db:5432
```

- `agent` 只有 `ai_net`，不参与 PostgreSQL 所在的 `default` 网络。
- Android 仅使用 v0.4 用户身份 token，不接触 `AI_SERVICE_TOKEN`、`BACKEND_TOOL_TOKEN` 或 DeepSeek API Key。
- 业务后端验证家庭成员，AI 从后端 `/internal/v1/inventory/*` 读取库存事实。AI **不能写入**。
- P1 现有接口 `/agent/message` 与 `/agent/clarification` 保持不变，Backend 仅增加 `/api/v1/agent/*` 网关。

## 数据库 Alembic 0005

新增 `ai_tasks`（按 `user_id + household_id + request_id` 唯一，保存正文摘要、原文、时区、状态、上下文、修订、到期时间、30 秒处理租约）与 `ai_drafts`（每任务最多一条，`pending`/`superseded`，草稿与 preview JSON，revision）。原有用户、库存、共享购物清单不改动。

## 状态映射

| P1 status | 网关动作 | 是否写库存 |
|---|---|---|
| answered | 保存回答、facts，可随时查询任务 | 否 |
| needs_clarification | 保存 P1 最新 context，App 只看可补字段/候选 | 否 |
| needs_confirmation | 保存 `ai_drafts` 和 `preview.prospective=true` | 否 |
| unsupported | 返回操作边界，无草稿 | 否 |
| error | 保存/返回错误和重试标志，不生成库存事件 | 否 |

`HTTP 200` 但 P1 `status=error` 时仍属于 AI 业务失败，不能当作库存操作成功。平台出错 503 不产生库存写入。`request_id` 相同而内容不同拒绝 409；重复完全相同消息返回上次保存结果，避免付费重复调用。澄清使用 task 修订号和服务端数据库 context，不允许跨家庭、跨用户修改任务。

## 后续 v0.7 明确不在本包范围

- 草稿编辑、`POST /api/v1/drafts/{id}/confirm`
- 库存事件账本与撤销
- 原子更新数量、批次版本、防止重复写入
- `PLAN_ADD` 购买意图写入每家庭唯一共享清单
- 并发真实 PostgreSQL 事务与手机端完整业务验收

v0.6 可以返回 `needs_confirmation`，但**不会提供确认操作**，这是明确的安全边界，不能误报“AI 已可修改库存”。

## 已运行的本地检验

- Backend 隔离测试：12 passed，涵盖 v0.4/v0.5 回归、0005 SQLite 迁移、身份权限、请求幂等、澄清和草稿持久化、实际 P1 `AgentResult` 形状。
- AI 交付代码：82 passed。未连接阿里云数据库、未运行 DeepSeek 付费评测、未运行 Docker Engine 构建（当前测试环境没有 Docker Engine）。
