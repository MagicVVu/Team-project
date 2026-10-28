# P2 AI 成员配合事项：P7.3 内部续接适配器

本地已实现，尚未发布到当前 p74 镜像；正式 OpenAPI 核实该路由不存在。此文件交付本地代码和协议，不假设线上已经可调用。

## 修改与边界

- 新模块 `agent/conversation/reply_adapter.py`。
- `conversation.app.Profile.install_routes` 增加 adapter.install 调用。
- 不修改 conversation/replies.py、理解引擎、Manager、预算算法或模型提示词。
- 原 Dockerfile COPY conversation 目录已包含新增模块，不新增运行依赖或进程。
- 沿用现有服务 Bearer Token 和 X-User-Id/X-Household-Id scope 依赖；Scope 不匹配返回 403，缺认证 401。

## 内部协议

`POST /agent/reply-resolution`，仅可信后端通过内部 Docker 网络使用。完整可执行 schema：[backend-p2-agent-openapi.json](backend-p2-agent-openapi.json)。下列是输入结构说明，binding.task 必须是真实数据库公开 Task，不能发送空对象：

```text
{
  "binding": {
    "scope": {"user_id": "已认证用户ID", "household_id": "有效家庭ID"},
    "task": 完整公开Task,
    "household_timezone": "Asia/Shanghai"
  },
  "text": "就第二个吧",
  "trusted_now": "2026-10-23T02:00:00+00:00",
  "selected_batch_id": null
}
```

后端在请求前已校验数据库所有者、成员关系、状态、revision、TTL 和候选顺序；selected_batch_id 仅来自服务端已有明确选择。适配器直接调用现有纯函数，不查询业务数据库、不生成 BoundTask、不提取模型。

候选第二批的返回示例（两个批次的第二个 ID 为示例 UUID，revision=3）：

```json
{
  "protocol_version": "p7-reply-routing-1",
  "kind": "clarify",
  "answers": {"batch_id": "33333333-3333-4333-8333-333333333333"},
  "revision": 3,
  "error_code": null,
  "clear_reference": false,
  "model_calls": 0
}
```

另外三种结果沿用原 ReplyResolution 模型；字段补充仍只有既有九字段。日期字面量不在此层改写；最终日期按原澄清 context.created_at 语义处理。后端继续将 clarify 转给已有 `/agent/clarification`。

## 验证及发布待办

1. 审查新增 HTTP 包装及服务 scope，保持纯函数行为不变。
2. 按 Agent lock 环境运行完整测试；本轮正确环境已 772 项通过。Windows 还需 tzdata，Linux 运行镜像已有系统时区数据。
3. 与后端 P2 协调发布；后端 0008 迁移先在隔离副本审查验证，未获正式部署授权前不要操作生产。
4. 发布后先验证内部路由存在、认证和零提取行为，再决定是否开启后端 `MAGICVVU_TRUSTED_REFERENCE_MESSAGES=true`；默认和当前正式能力仍 false。
5. 后端遇到旧 Agent 404 返回 REPLY_ADAPTER_UNAVAILABLE，不会复制算法或通过模型 fallback。不要将仅健康版本 0.7.0 视为已包含此接口。
6. pricing.json 已按已部署公开文件恢复合法 JSON；原 P7.4 预算算法和费率均未改。元数据 policy 文案与取消日期拦截的说明可另行统一，不能据此擅自改回旧门禁。
7. 后续若要自动恢复首次付费理解的未知结果，需要 Agent 提供持久化 request_id 幂等结果/调用账本契约。当前只有原有解析接口，后端对未知首次理解准确返回 AI_OUTCOME_UNKNOWN，不盲目重复付费提取。

本轮没有实际调用 DeepSeek、上传镜像、部署、重启或通知其他成员；此文档是供团队审查接入的交付物。
