# P7 后端草稿执行与 Android 接入（第三阶段）

基准：`db55fda1262f55d46eba8fa0c2dc3b23aee75cab`。新后端开发版本 0.9.0，迁移 `20261017_0007`。仅供隔离开发验收，未部署生产。AI 继续使用 P7 0.7.0 rules，不重复付费模型测试。

## 状态与支持范围

| 动作 | 业务执行 | 语义与限制 |
| --- | --- | --- |
| ADD | 支持 | 创建独立批次；位置必填；服务端派生稳定库存 UUID |
| MOVE | 支持 | 锁定同家庭 ACTIVE 批次，校验原版本；只改位置和版本/审计信息 |
| PLAN_ADD | 支持手动明确数量 | 新增家庭共享待购物项，不购买、不入库；数量最多三位小数，单位须兼容原单位 |
| CONSUME | 支持 | 原子扣减数量、增加版本并写入正式 `Consumed` 事件；耗尽为 FINISHED |
| OPEN | 不支持 | `ACTION_NOT_EXECUTABLE`；不伪装成普通编辑 |
| DISCARD | 不支持 | `ACTION_NOT_EXECUTABLE`；不伪装成删除或消费 |

带 `planning_basis`、`quantity_source=planning_calculation` 或 SUGGEST_PURCHASE 来源的 PLAN_ADD 均拒绝：`PLANNING_REVALIDATION_UNAVAILABLE`。未交付规划事实模块，不能删除依据或退化为零待购后执行。

## 事务和持久化

旧 `ai_tasks`/`ai_drafts` 的模型、状态及公开协议保持原样，旧网关仍返回 `inventory_written=false`。这表示 AI 结果是预览，不代表独立业务执行器没有执行；新客户端必须读取独立执行状态。

新增三表：

- `draft_operations`：全局唯一 operation_id、每草稿至多一次成功操作、规范化命令、请求指纹和不可变成功回执。
- `draft_decisions`：每草稿唯一 committed/cancelled 决策，绑定草稿和任务修订。取消不删除 AI 原结果。
- `business_events`：StockAdded、StockMoved、PlanAdded、Consumed，关联操作、家庭、用户、资源及真实前后快照。只有 Consumed 计作本模块消费记录。

锁顺序：任务 → 草稿 → 家庭成员（共享锁）→ 库存或共享清单。库存版本比较、业务写入、事件、回执和决策只有一次提交。异常全部回滚；不持久化一个脱离业务事务的“成功”或“处理中”。进程退出会由 PostgreSQL 回滚未提交事务。

同 operation_id、同草稿和同请求体重试，返回原持久回执，即使任务后来过期或库存又发生变化，也不重做业务。换请求体、换草稿、换用户复用该键返回 409；换键重交已决定草稿也返回 409。指纹对 JSON 键排序，包含完整 edits；客户端应保存并原样恢复请求体，不能假定不同数量字符串等价。

一次成功后即使 HTTP 丢失也可 GET 恢复。GET operation 返回 404 不代表另一个请求一定未在处理中，继续使用原键和原体恢复，不能新建键重做。业务校验失败不会留下部分业务或成功回执。

默认有效期为任务最后结果时间、草稿时间加 900 秒及原任务有效期的最早值；GET 不续期。确认时不信任 AI preview。

## API

所有公开接口沿用用户登录 Bearer token，不能使用 AI 服务令牌替代。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/agent/execution-capabilities` | 后端声明动作和限制；不能用 AI health 启用按钮 |
| GET | `/api/v1/drafts/{draft_id}/execution` | 独立状态、双修订、可编辑字段、有效期、操作 ID 和回执 |
| POST | `/api/v1/drafts/{draft_id}/commit` | 用户确认并执行 |
| POST | `/api/v1/drafts/{draft_id}/cancel` | 持久取消；重复同修订取消幂等 |
| GET | `/api/v1/operations/{operation_id}` | 原提交用户且仍有家庭权限时恢复原回执 |
| GET | `/api/v1/households/{household_id}/consumption-events` | 同家庭分页读取正式 Consumed 事件 |
| POST | `/api/v1/agent/reference-messages` | 预留独立适配入口，目前认证后明确 503，不创建任务、不调用 AI |

GET execution 的 status 为 pending/committed/cancelled/expired/superseded/unavailable。只有 commit 成功或持久回执的 committed 才代表执行成功。

提交 CONSUME 示例（UUID、修订使用实际 GET 值；示例不包含凭据）：

```json
{
  "operation_id": "11111111-1111-4111-8111-111111111111",
  "draft_revision": 1,
  "task_revision": 2,
  "edits": {"quantity": "1", "unit": "盒"}
}
```

成功回执包含 protocol_version=draft-operation-receipt-1、operation_id、draft_id、task_id、双修订、scope、status=committed、action、committed_at、trace_id、真实 batch_versions/event_ids、inventory_written/shopping_written 和 result 下的 inventory_item 或 shopping_item。完整真实 JSON 示例由隔离 HTTP 验收脚本输出到 `http-acceptance.json`，其请求和回执不包含登录或服务令牌。

取消请求：

```json
{"draft_revision": 1, "task_revision": 2}
```

取消响应：

```json
{"draft_id": "22222222-2222-4222-8222-222222222222", "status": "cancelled"}
```

错误示例（HTTP 409）：

```json
{"detail": {"code": "INVENTORY_VERSION_CONFLICT"}}
```

401 为登录失效；404 隐藏他人草稿、任务、操作或跨家庭库存；422 为字段/单位/精度非法。409 包括版本冲突、过期、已取消/提交和能力缺失，读取最新任务及执行状态后让用户重新核对，禁止静默替换版本。

## 编辑白名单

- ADD：name、quantity、unit、location、purchased_at、label_expiry。
- MOVE：to_location。
- CONSUME、PLAN_ADD：quantity、unit；兼容质量和体积换算，盒/包等不能互换；CONSUME 按库存单位记录真实扣减。

库存数量最多六位小数，采购最多三位，位置最多 100 字。拒绝超限，不舍入或截断。action、batch_id、expected_version、家庭、用户、来源任务和规划依据不允许客户端修改；顶层未知字段也拒绝。改变动作或目标需新任务。

## Android 调用顺序

第三阶段未发布宿主机端口，Android 不能直接使用 Docker 的 backend DNS。第四阶段需为专用测试后端建立仅本地/SSH 可达的访问通道，不能把正式 0.8 地址当作已具备新接口；本阶段不提前修改端口或公网访问配置。

1. 沿用旧四字段消息，保存稳定 request_id、原文及完整请求；澄清仍使用原 task_id、revision 和允许字段。
2. 得到 draft_id 后，读取旧草稿详情和新 execution；不要从 preview、聊天文案或旧任务状态推断已执行。
3. 按白名单展示表单，保存最终 edits、双修订和新生成一次的 operation_id，然后等待用户明确确认。
4. POST commit；请求中不提交 AI 原始指令、preview、作用域或版本覆盖值。
5. 成功后以回执更新状态，再刷新库存/共享清单。刷新失败保留已提交成功，不重新提交。
6. 超时先 GET operations 或 GET draft execution；需要重试只能用原键原体。应用重启后同样恢复，不重新生成 operation_id。
7. 注销/换家庭隔离活动绑定；其它账号或失去家庭权限后不能恢复该操作。

## 内部回执

`GET /internal/v1/operations/{operation_id}` 使用已有 BACKEND_TOOL_TOKEN、可信 X-User-Id/X-Household-Id，并重新校验活跃用户、家庭成员和操作归属。库存动作返回 data 包裹的 P6 `v1-operation-receipt-1`，真实事件 ID 和批次版本来自成功事务。

PLAN_ADD 没有库存版本，不能满足 P6 库存反馈的非空 batch_versions，返回 `INVENTORY_RECEIPT_NOT_APPLICABLE`。公开采购回执仍可恢复；不编造库存批次或版本。

消费读取声明 `planning_history_complete=false`。本阶段未补造旧调整记录的消费语义，未交付稳定商品映射、历史覆盖/纠错、规划快照或预测完整性。

## 受信引用适配设计与未完成边界

公开旧消息不增加 reference。预留的新入口仅接受 source_task_id/source_revision/batch_id 等选择信息，拒绝客户端提交完整 ObjectReference，且本轮始终返回 503，capabilities.trusted_reference_messages=false。

未来启用前必须由后端按登录用户及家庭加载来源任务和最新修订，只从真实 facts/candidates 允许建立 batch_id 引用；验证来源结果时效、批次可访问性/版本/终态；签发至多 900 秒且不延长缓存寿命的服务器时间。需要新增持久请求绑定，把原文、request_id、来源修订、引用内容及有效期统一指纹化。相同键不能重新签发或换引用。现有四字段指纹不能证明这些绑定。

没有上述持久适配及并发/过期测试前不得启用引用续问。P7 内部引用协议在第二阶段通过，不能据此声称公开网关适配已完成。

## 迁移和回退

0007 仅新增表及约束，不修改旧表、旧任务或库存。先在全新第三阶段 PostgreSQL 测试库迁移，正式数据库不执行任何迁移。旧 0.8 代码仍能读取原表。

应用回退保留 0007，不删除事件、回执或决策，不回放库存写入。只有三个新表完全为空时才允许 downgrade 到 0006；已有审计数据时迁移主动拒绝降级。测试恢复使用独立备份或每用例新 schema，禁止覆盖生产/第二阶段数据库或删除其数据卷。

第三阶段容器项目及工作区：`magicvvu-p7-execution-20261017`、`/home/admin/magicvvu-p7-execution-20261017`。数据库 `magicvvu_p7_execution_test` 与前阶段完全独立，无宿主机发布端口，AI 只有 rules、无供应商密钥且网络无公网出口。

## 测试与冻结摘要问题

后端回归：`python -m pytest -q tests`。PostgreSQL 执行套件：`DRAFT_EXECUTION_PG_TEST=yes` 且 DB_NAME 必须严格等于 `magicvvu_p7_execution_test`；每用例创建并销毁专属随机 schema，不清空共享库。真实 HTTP 验收入口为 `tests/check_draft_postgres_http.py`，在第三阶段 backend 容器内执行，所有夹具为合成家庭。

P1/P2 原冻结数据摘要失败保持独立记录：仓库 LF 字节与 manifest 记录的 CRLF 哈希不一致。未重写数据、manifest 或断言。建议后续由数据维护者明确字节规范和 provenance：统一 .gitattributes，人工核对固定样本和原 SHA-256，生成有来源链的新 manifest/数据集版本并跨平台验证；不要在测试中自动忽略校验或静默规范化已有冻结数据。
