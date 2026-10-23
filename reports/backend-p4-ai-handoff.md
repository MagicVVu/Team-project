# MagicVVu P4 AI 接口交接

2026-10-23，本地已实现并验证，未部署。唯一正式读取：`GET /internal/v1/planning/context`。旧报告路径`/internal/v1/ai/planning-context`仅为同一服务的隐藏兼容入口。Agent RemoteReader 已请求正式路径，本轮无需改Agent算法或工具路径。协议`v1-planning-context-1`，契约：[后端OpenAPI](backend-p4-backend-openapi.json)、[V1 Schema](../docs/versions/V1-P6/planning-context.schema.json)。

## 请求与认证

```http
GET /internal/v1/planning/context?name=牛奶
Authorization: Bearer <BACKEND_TOOL_TOKEN，仅服务端配置>
X-User-Id: <可信用户UUID>
X-Household-Id: <可信当前家庭UUID>
```

可不填选择条件查询全家庭，name/item_key最多一个；item_key是批次UUID，不能把相似名称当product_id。内部服务令牌与AI_SERVICE_TOKEN分开；后端重新检查active/member，跨家庭404，错误/缺令牌401。Android不持有令牌，不直接访问。POST405。

## 实际响应

以下是本轮真实双进程HTTP+隔离PG业务执行的响应摘取，UUID来自合成测试用户。完整返回及事件operation_id来源见[HTTP证据](backend-p4-http-evidence.json)。

```json
{
  "data": {
    "protocol_version": "v1-planning-context-1",
    "scope": {
      "user_id": "440fa599-294e-4496-8ff9-da3d570e46d5",
      "household_id": "9d515232-b477-40f3-b046-fce5d3c59752"
    },
    "snapshot_id": "88d95f471e586c6219e45021975729ec42c9db6a2cd7ed39139d66ba012150d7",
    "as_of": "2026-10-23T04:29:09.843543Z",
    "event_watermark": "353dd8f70f758d5d24afca85239f2a42546dd58982219941a3d98ecc966e0a14",
    "shopping_version": 742838345576866293,
    "items_complete": true,
    "history_complete": true,
    "pending_complete": true,
    "next_cursor": null,
    "items": [
      {
        "item_key": "5f7984b2-7617-4a46-9c9a-cd75e2234297",
        "name": "牛奶",
        "unit": "盒",
        "version": 2,
        "category": "unknown",
        "batches": [
          {
            "id": "5f7984b2-7617-4a46-9c9a-cd75e2234297",
            "household_id": "9d515232-b477-40f3-b046-fce5d3c59752",
            "name": "牛奶",
            "quantity": "4.000000",
            "unit": "盒",
            "location": "冰箱",
            "purchased_at": null,
            "label_expiry": null,
            "opened_at": null,
            "status": "ACTIVE",
            "version": 2,
            "category": "unknown",
            "product_id": null,
            "label_date_type": "unknown",
            "label_context_valid": null,
            "storage_condition": null,
            "label_storage_condition": null,
            "is_opened": null
          }
        ],
        "events": [
          {
            "id": "ffc0d154-e63a-5f55-baf0-096592184985",
            "item_key": "5f7984b2-7617-4a46-9c9a-cd75e2234297",
            "kind": "Consumed",
            "quantity": "1.000000",
            "unit": "盒",
            "occurred_at": "2026-10-23T04:29:09.782751Z",
            "recorded_at": "2026-10-23T04:29:09.782751Z",
            "committed": true,
            "related_event_id": null
          }
        ],
        "coverage": [],
        "recording_completeness_source": null,
        "preferences": {
          "version": 2,
          "minimum_stock": null,
          "coverage_days": null,
          "lead_days": null,
          "order_unit": null,
          "pack_size": null
        },
        "usable_quantity_verified": false,
        "stock_verification": null
      }
    ],
    "pending": []
  },
  "provenance": {
    "schema_version": "backend-planning-provenance-1",
    "recording_completeness": "unknown",
    "automatic_planning_commit": false
  }
}
```

示例provenance仅摘录；实际包含items/events/shopping来源。data严格兼容现有V1，不能把外层provenance整体塞进PlanningSnapshot。事件原operation_id、家庭、actor、数据库NULL数量及关系支持状态在`provenance.events[event_id]`，V1 Event仍只保留已有字段。缺省不增加新预测规则。

## 一致性、完整性、新鲜度

as_of来自快照首SELECT数据库时间，库存/账本/共享采购同事务：PG只读Repeatable Read，SQLite显式BEGIN。no-store。snapshot_id绑定全家庭内容/来源，独立于时刻与筛选，同内容ID稳定；每次重新读数据库提供as_of，ID不能替代新鲜度校验。event_watermark是可见账本内容SHA256；shopping_version是60位内容散列整数，均非递增提交序号。已有Agent只作快照一致性比较，不允许据此绕过确认重验。超限409 PLANNING_INCOMPLETE、DB失败503 PLANNING_CONTEXT_UNAVAILABLE、存储事实无法表示409 PLANNING_CONTRACT_INVALID；没有成功的部分数据响应。RemoteReader遇HTTP错误沿用现有TOOL_UNAVAILABLE映射，保持现有错误契约，后端错误detail供日志定位。

items_complete/history_complete=true证明完整读取已有行，**不证明现实所有消费已记录**。coverage=[]和recording_completeness_source=null是核心事实；请继续返回RECORDING_COMPLETENESS_UNKNOWN和NO_COMPLETE_COVERAGE_DAYS。stock_verification=null/usable_quantity_verified=false必须保留STOCK_VERIFICATION_REQUIRED/USABLE_STOCK_REQUIRES_REVIEW；普通更新时间不得替代盘点。

Reader继续拒绝超过300秒/未来超过1秒的快照、不完整items/有cursor；库存核实168小时门槛保留。本轮未扩展任何覆盖/核实来源，不能通过合成fixture或忽略校验使生产输出预测。

## 数量与建议限制

只计Consumed，Discarded/Opened/Moved/Added/普通调整不算消费；Opened/Moved在V1数量0仅适配无数量事实，来源为NULL。operation_id唯一，不能重复累计；不能解析旧history展示文字当事件。原撤销/纠正算法仍支持测试，但当前业务DB没有对应事件写入，不生成假关系。

每个item_key仅对应一个真实批次，无可信跨批次商品ID。所有数量Decimal；单位不兼容时沿用EVENT_UNIT_CONFLICT/INVALID_UNIT，不能猜包装量。pending仅有明确同家庭source_inventory_item_id才能关联；无关联待购使pending_complete=false，不当作0。实际已购状态purchased保留但不扣待购量，外层来源保留全部采购明细。

最低库存旧0=null，新显式业务请求0有结构化来源可返回0；历史最多30条，证据丢失后0降级null。旧正值来自真实minimum_quantity，精确actor/time未知。偏好版本保守复用库存版本。coverage_days/lead_days/order_unit/pack_size未设置均null，不生成默认值。分类仅精确已有枚举，product_id=null，标签类型unknown、储存事实null；规则审核仍需AI/业务同事，后端未造规则。

`automatic_planning_commit=false`。即使建议生成PLAN_ADD草稿，原后端对planning_basis/planning_calculation/SUGGEST_PURCHASE仍拒绝PLANNING_REVALIDATION_UNAVAILABLE；AI不能写采购清单或库存。

AI同事需：同步正式路径/内部token/家庭身份；在UI解释传输完整与记录完整的区别；继续原降级和新鲜度门槛；审核规则与缺失事实的业务来源；未来商品目录/覆盖/盘点契约变更需要版本化联合评审，不自行增加算法默认值。真实DeepSeek及正式服务未验证。本轮Agent全量772通过；真实内网HTTP由两个本机Uvicorn进程验证，非模型联测。
