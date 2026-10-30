# V1-P8.6：AI 自主循环与当前契约适配

2026-10-30发布跟进：经用户追加授权，AI及必要后端适配已同步并替换正式运行版本，DeepSeek、新旧服务认证和公开入口检查通过。详见[正式版本替换记录](正式版本替换记录.md)、[运行AI OpenAPI](contracts/production-ai-openapi.json)和[运行后端 OpenAPI](contracts/production-backend-openapi.json)。数据库未迁移，Android和TLS配置未改；App联验、Release受信证书仍需分别确认。下文“未部署”指此前本地开发和归档阶段。

2026-10-30按用户要求，将此前未编号的自主循环开发与随后服务器契约适配统一定义为 **V1-P8.6**。AI接口文档版本为 **0.8.6**，维护标记为 **V1-P8.6**；线协议仍为 `inventory-autonomous-1`，业务后端0.9.0/P9、数据库迁移版本和旧请求命名空间均保持原约定。本次只整理本地文件，未部署或提交Git。

| 资料/实现 | 唯一维护位置 |
|---|---|
| 阶段说明、交接、评测、JSON契约 | 本目录与 `contracts/` |
| AI运行代码 | `agent/conversation/autonomous/`，共用原会话模块；不按版本复制代码 |
| 后端薄适配 | `backend/server/app/services/autonomous.py`及既有会话适配点 |
| 自动化测试 | 原AI、后端tests目录，保留可运行导入路径 |
| 初始实现原始报告 | [initial-20261029](../../../reports/p86-autonomous/initial-20261029) |
| 当前逐件契约适配原始报告 | [adaptation-20261030](../../../reports/p86-autonomous/adaptation-20261030) |
| 本次归档映射与校验 | [organization-20261030](../../../reports/p86-autonomous/organization-20261030) |

[文件整理记录](文件整理记录.md)说明移动映射、历史证据和Git暂存状态。旧 `docs/ai-autonomous` 只保留跳转说明。

归档后验证：AI全量1136通过/1跳过、后端相关28项通过，12份本地契约及文档链接校验通过。原始评测记录不覆盖；后续服务器发布见上方记录，App联合验收仍未进行。

更新：2026-10-30，Asia/Shanghai。取消新协议的固定两次模型调用上限，改为根据进展自主处理；保留用户确认和正式后端执行边界。已只读核对服务器，并将本地未提交实现适配到队友的 P8.5 会话档案与逐件库存契约。本轮未同步服务器、未替换正式版本、未改前端业务代码、未提交或推送 Git。

当前进度以[正式版本替换记录](正式版本替换记录.md)为准，线上新会话已为 `inventory-autonomous-1`，采用 `single-object-1` 库存语义。[此前核对与适配记录](2026-10-30-服务器核对与适配记录.md)保留发布前证据。前端源码已具备新版会话入口和90秒超时，手机实际安装包与联合场景仍需验证。

- [工作记录](工作记录.md)：实现范围、停止机制、验证和当前交付状态。
- [前后端交接说明](前后端交接说明.md)：独立工厂、协议开关、保存与恢复，以及前端待办。
- [评测记录](评测记录.md)：真实 DeepSeek 对比、自动化测试及验收限制。
- [AI OpenAPI JSON](contracts/ai-openapi.json)、[后端 OpenAPI JSON](contracts/backend-openapi.json)：当前本地实现契约，均不代表已部署。
- [内部请求](contracts/run-request.schema.json)、[内部响应](contracts/run-response.schema.json)、[模型决策](contracts/decision.schema.json)、[可信上下文](contracts/context.schema.json)。
- [公开消息](contracts/public-message.schema.json)、[公开响应](contracts/public-response.schema.json)、[历史页](contracts/conversation-page.schema.json)、[恢复](contracts/recovery.schema.json)。
- [零模型重验请求](contracts/revalidation-request.schema.json)／[结果](contracts/revalidation-response.schema.json)、[契约摘要](contracts/manifest.json)、[运行源码清单](runtime-source-manifest.json)。

新工厂为 `conversation.autonomous.app:create_app`，内部入口为 `POST /agent/dialogue/run`，协议为 `inventory-autonomous-1`。原 P8.5 工厂及三阶段接口继续保留原行为，不能只改后端协议字符串就启用新能力。
