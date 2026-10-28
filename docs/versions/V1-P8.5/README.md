# V1-P8.5 会话记忆与自然理解

2026-10-28 接入汇总：P8.3～P8.5 的最终前后端实施请统一查看[三版本总对接方案](../../handoffs/V1-P8.3-P8.5-前后端统一对接方案.md)。本目录保留本阶段历史证据，重复接入要求以总方案为准。

2026-10-28。基于 P8.4 进行 AI 本地增强；旧入口、已发布运行版本、前后端源码和数据库不变。已有未提交修改保留。

- [提升方案与开源调研](提升方案.md)：先分析和规划，再进行实现。
- [工作记录](工作记录.md)：本轮实现、验证和边界。
- [前后端交接说明](前后端交接说明.md)：后端记忆供给、阶段保存、前端呈现和恢复要求。
- [评测记录](评测记录.md)：离线场景、真实 DeepSeek 与 P8.4 对照，未完成项单列。
- [AI OpenAPI JSON](contracts/ai-openapi.json)、[现有后端 OpenAPI JSON](contracts/backend-openapi.json)：后者只代表当前本地后端，尚未实现 P8.5 转发。
- [会话上下文 Schema](contracts/context.schema.json)、[历史片段 Schema](contracts/archive.schema.json)、[记忆增量 Schema](contracts/memory-delta.schema.json)。

P8.5 是独立选择的 `conversation.p85.app:create_app`，协议 `p85-dialogue-1`；默认 `conversation.app:create_app` 继续为 P8.4。所有新能力须经业务后端调用，新版 AI 源码存在不等于 App 已启用。

范围：单当前会话的近期记忆与相关旧话题、自然语义、原任务续接和事实表达。不新增长期个人偏好、向量数据库、第三方记忆托管、多 Agent、自动执行或运行用假库存服务。
