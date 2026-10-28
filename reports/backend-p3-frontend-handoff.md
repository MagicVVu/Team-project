# MagicVVu P3 Android 接口交接

2026-10-23，本地已实现并测试，未正式部署。以 [后端实际 OpenAPI](backend-p3-backend-openapi.json) 为准；[完整真实JSON](backend-p3-postgres-examples.json) 来自本次隔离测试合成用户，无真实用户库存或令牌。

## 1. 入口与身份

所有公开接口沿用 `Authorization: Bearer <当前登录令牌>`。先读 `GET /api/v1/agent/execution-capabilities`，仅在对应 actions.OPEN/actions.DISCARD=true 时展示可确认能力。服务端也强制检查。两个开关独立、默认false；正式目前都为false。automatic_planning_commit不变，仍false。

AI入口仍为四字段 `POST /api/v1/agent/messages`、九字段 `POST /api/v1/agent/clarifications/{task_id}`；P2 `POST /api/v1/agent/conversation-messages`、`POST /api/v1/agent/reference-messages` 保留。自然语言续接走P2绑定机制，不能自行从“它”猜批次或注入内部context。AI任务和草稿返回的inventory_written=false只说明AI未写库存；正式执行状态必须查询execution接口。

## 2. 原草稿字段及编辑规则

| 动作 | command_json 必需字段 | edits允许字段 | 数量来源 |
| --- | --- | --- | --- |
| OPEN | action=OPEN,name,batch_id,expected_version,opened_at | opened_at | 无数量，quantity_source=null |
| DISCARD partial | action=DISCARD,name,batch_id,expected_version,discard_mode=partial,quantity,unit | quantity,unit | user_input |
| DISCARD all | action=DISCARD,name,batch_id,expected_version,discard_mode=all,quantity,unit | 无 | current_batch：后端在锁内核实数据库数量 |

真实草稿样例：

### OPEN

```json
{
  "action": "OPEN",
  "name": "牛奶",
  "batch_id": "9110cb0c-a939-4cb0-9978-acd5323acc2c",
  "expected_version": 1,
  "opened_at": "2026-10-22"
}
```

### partial

```json
{
  "action": "DISCARD",
  "name": "牛奶",
  "batch_id": "68859cbd-e278-47a7-9990-7d88f6431b55",
  "expected_version": 1,
  "discard_mode": "partial",
  "quantity": "2",
  "unit": "盒"
}
```

### all

```json
{
  "action": "DISCARD",
  "name": "牛奶",
  "batch_id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
  "expected_version": 1,
  "discard_mode": "all",
  "quantity": "5",
  "unit": "盒"
}
```

action/name/batch_id/expected_version/discard_mode 受保护，切换动作、批次或模式必须重新理解并生成草稿。all的数量和单位也不能放入edits，即使值相同也拒绝。客户端不能把历史查询数量作为权威数据。

opened_at 推荐发送 `YYYY-MM-DD`；不得未来日期，无开封数量输入。服务也支持编辑“今天/昨天”，按原任务可信创建时刻和业务IANA时区解析，推荐先预览显示最终ISO日期。已开封的新操作返回ALREADY_OPENED，不提供在本次接口中改写历史开封日的能力。

数量按字符串Decimal处理，最多六位小数，不能用客户端浮点舍入修正。partial等于余量时也会归零并进入DISCARDED；partial剩余>0保持ACTIVE；all固定归零DISCARDED。Opened不改变数量或位置，只变开封日和版本。

## 3. 可编辑草稿的只读预览

1. `GET /api/v1/drafts/{draft_id}`：已有AI草稿及前瞻说明。
2. `GET /api/v1/drafts/{draft_id}/execution`：真实执行状态、两个revision、editable_fields、expires_at、operation_id和receipt。确认前核对该状态。
3. `POST /api/v1/drafts/{draft_id}/execution-preview`：P3新增**只读**计算，输入两个revision和edits，无operation_id；不修改草稿、不续TTL、不写库存，不是第二套执行API。

实际all预览请求：
```json
{
  "draft_revision": 1,
  "task_revision": 1,
  "edits": {}
}
```

实际预览响应字段摘录（完整StockResponse见JSON证据/OpenAPI）：

```json
{
  "draft_id": "c518093a-0dbb-4fc6-abf1-5d0794055721",
  "task_id": "5a92f974-c1b1-4fc7-8ea7-00e266d5edfa",
  "draft_revision": 1,
  "task_revision": 1,
  "command": {
    "discard_mode": "all",
    "quantity": "5.000000",
    "unit": "盒",
    "name": "牛奶",
    "batch_id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
    "expected_version": 1,
    "action": "DISCARD"
  },
  "before": {
    "id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
    "name": "牛奶",
    "quantity": "5.000000",
    "unit": "盒",
    "storage_location": "冰箱",
    "opened_at": null,
    "status": "ACTIVE",
    "version": 1
  },
  "after": {
    "id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
    "name": "牛奶",
    "quantity": "0.000000",
    "unit": "盒",
    "storage_location": "冰箱",
    "opened_at": null,
    "status": "DISCARDED",
    "version": 2
  },
  "event_type": "Discarded",
  "event_quantity": "5.000000",
  "quantity_source": "current_batch",
  "expires_at": "2026-10-23T11:00:06.680877+08:00",
  "prospective": true,
  "inventory_written": false
}
```

OPEN显示before.opened_at和after.opened_at、原/预计version，前后quantity相同；partial/all显示前后数量及终态。before/after是预计状态，预览不会预先写入审计历史；提交后的after会有真实history_json事件。预览与确认之间仍可能发生版本冲突。

## 4. 确认、取消、回执

正式写入继续只用 `POST /api/v1/drafts/{draft_id}/commit`。用户确认前生成并持久保存一个UUID operation_id，保存原draft_id、两个revision和完全相同的edits；同一次操作所有重试均复用这些值。预览不会保存edits，commit必须带同一份edits。

实际all提交请求：
```json
{
  "operation_id": "c973b74a-a9fc-4271-a141-0f144950da2c",
  "draft_revision": 1,
  "task_revision": 1,
  "edits": {}
}
```

实际all成功回执字段摘录（省略result及部分StockResponse字段，完整真实回执见JSON）：

```json
{
  "protocol_version": "draft-operation-receipt-1",
  "operation_id": "c973b74a-a9fc-4271-a141-0f144950da2c",
  "draft_id": "c518093a-0dbb-4fc6-abf1-5d0794055721",
  "task_id": "5a92f974-c1b1-4fc7-8ea7-00e266d5edfa",
  "draft_revision": 1,
  "task_revision": 1,
  "scope": {
    "user_id": "61326bcf-c905-4fbe-a3bd-e7fd1bb29e60",
    "household_id": "ddeab4ce-765d-4e5e-8c4d-a94305c6dfc8"
  },
  "status": "committed",
  "action": "DISCARD",
  "committed_at": "2026-10-23T02:45:06.767790+00:00",
  "trace_id": "op_c973b74aa9fc4271a1410f144950da2c",
  "batch_versions": {
    "7b3b6a39-2967-4f85-a545-4b6a14f491f8": 2
  },
  "event_ids": [
    "d7728fe8-5cb2-5cf4-8266-41b5e469667c"
  ],
  "inventory_written": true,
  "shopping_written": false,
  "execution": {
    "event_type": "Discarded",
    "quantity": "5.000000",
    "unit": "盒",
    "discard_mode": "all",
    "quantity_source": "current_batch",
    "before": {
      "id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
      "name": "牛奶",
      "quantity": "5.000000",
      "unit": "盒",
      "status": "ACTIVE",
      "version": 1,
      "opened_at": null
    },
    "after": {
      "id": "7b3b6a39-2967-4f85-a545-4b6a14f491f8",
      "name": "牛奶",
      "quantity": "0.000000",
      "unit": "盒",
      "status": "DISCARDED",
      "version": 2,
      "opened_at": null
    }
  }
}
```

回执protocol_version仍draft-operation-receipt-1。P3新增可选execution字段，包含before/after、event_type、quantity、unit、discard_mode、quantity_source；旧已存回执不回填、不重写，客户端必须允许execution缺省。result.inventory_item是实际提交后库存；batch_versions/event_ids/trace_id关联真实操作和事件。OPEN的quantity/discard_mode/quantity_source为null、event_type=Opened；两种DISCARD均event_type=Discarded，数量为实际扣减量。

`POST /api/v1/drafts/{draft_id}/cancel` 继续只接受task_revision、draft_revision。取消与确认竞争只有一个最终决策。`GET /api/v1/drafts/{draft_id}/execution` 的status=committed时receipt为真实账本，不要因原AI任务仍needs_confirmation再次生成操作。

## 5. 主要错误

错误的业务码位于 `detail.code`；认证/原网关错误仍可能是原有字符串或FastAPI校验数组，客户端保留通用分支。

| HTTP | code | 前端行为 |
| --- | --- | --- |
| 422 | INVALID_DRAFT_FIELDS / OPEN_DATE_IN_FUTURE | 更正允许编辑字段并重新预览；不得静默补日期。 |
| 422 | PROTECTED_OR_UNKNOWN_FIELD | 不修改目标/模式/all数量；重建草稿。 |
| 422 | UNIT_UNSUPPORTED / UNIT_MISMATCH / CONVERTED_QUANTITY_INVALID / INSUFFICIENT_STOCK | 展示数量或单位问题；不得截断舍入。 |
| 409 | INVENTORY_VERSION_CONFLICT / DISCARD_ALL_QUANTITY_CONFLICT | 拒绝旧草稿；重新读取、核对并生成草稿，不把旧expected_version改成新版本。 |
| 409 | DRAFT_REVISION_CONFLICT / DRAFT_SOURCE_CHANGED / DRAFT_NOT_PENDING | 重新获取原任务和草稿状态，不能硬改revision。 |
| 409 | DRAFT_EXPIRED / REFERENCE_EXPIRY_UNAVAILABLE | 重新发起并核对；引用期限和普通TTL均受检查。 |
| 409 | INVENTORY_NOT_ACTIVE / ALREADY_OPENED | 展示现有事实，不能再次丢弃终态或覆写开封日。 |
| 409 | OPERATION_ID_CONFLICT | 原ID对应另一请求，停止修改请求后重试；恢复原请求结果。 |
| 409 | DRAFT_ALREADY_DECIDED / DRAFT_ALREADY_COMMITTED | 查询execution确定最终决策。 |
| 409 | ACTION_NOT_EXECUTABLE | 当前开关关闭；刷新capabilities。已完成回执仍可恢复。 |
| 409 | EXECUTION_CONFLICT | 事务冲突；保留原ID查询，并按相同请求恢复。 |
| 401 / 404 | 当前身份无效 / DRAFT_NOT_FOUND / OPERATION_NOT_FOUND | 复核登录与家庭；404可能来自权限或查询时序，不是从未执行的证明。 |

## 6. 丢响应与刷新失败

提交超时或5xx时显示“结果待核实”，先以原operation_id请求 `GET /api/v1/operations/{operation_id}`，再查原draft的execution。必要时只重发原key/原body。单独一次404不能据此换新key重新扣库存。成功回执应本地保留；之后库存刷新失败只重试读取，不重新执行commit。会话失效/被移除家庭时先恢复合法身份与权限，不能绕过重新鉴权。

Android不得用普通数量调整冒充丢弃，不得删库存记录冒充all，不得改备注冒充开封。前端改造、真机断网测试和实际部署联调尚待Android/Agent/运维队友配合完成。
