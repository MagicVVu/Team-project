# V1-P8.7：中英文家庭库存助手

日期：2026-11-01。基线：`8f44a6a`（包含当前逐件库存和 JEV 更新）。本阶段经用户追加授权命名为 **V1-P8.7**，AI 版本 **0.8.7**；已同步服务器并替换 AI 与必要后端语言适配，见[正式发布记录](正式发布记录.md)。

本阶段文档、工作记录和契约已全部归入本目录；评测数据继续保存在 `reports/ai-english/`。P8.6 自主循环和 P9 JEV 保持原阶段归属。

English 设置控制新一轮的系统回复语言；用户仍可混合输入。已有名字、位置、消息原文和历史回复保留原样。切换语言不会清空任务或触发付费请求。

- [正式发布记录](正式发布记录.md)：服务器运行版本、验证与回滚边界。
- [服务器 AI OpenAPI](contracts/production-ai-openapi.json)、[服务器后端 OpenAPI](contracts/production-backend-openapi.json)。
- [工作记录](工作记录.md)：实际修改、验证和保留边界。
- [统一接入说明](前后端交接说明.md)：接口、恢复、语言切换、部署顺序及验收。
- [评测记录](评测记录.md)：首轮开发／保留集、修复后复测及验证限制。
- [AI OpenAPI JSON](contracts/ai-openapi.json)：当前自主循环入口及兼容入口。
- [后端 OpenAPI JSON](contracts/backend-openapi.json)：App 公开会话、读取和执行接口。
- [公开消息 Schema](contracts/public-message.schema.json)、[公开响应 Schema](contracts/public-response.schema.json)。
- [可信上下文 Schema](contracts/context.schema.json)、[AI run 请求](contracts/run-request.schema.json)、[AI run 响应](contracts/run-response.schema.json)。
- [分页历史 Schema](contracts/conversation-page.schema.json)、[恢复 Schema](contracts/recovery.schema.json)。
- [零模型重新核对请求](contracts/revalidation-request.schema.json)、[重新核对响应](contracts/revalidation-response.schema.json)。
- [契约文件校验清单](contracts/manifest.json)、[AI 运行源码哈希](runtime-source-manifest.json)。

`ai-openapi.json`、`backend-openapi.json` 及 Schema 是本地源码导出；`production-*-openapi.json` 是本次运行容器的独立快照，两者分开保存。旧版本契约和评测未覆盖。文档、测试和评测保留本地仓库，服务器只保存运行代码、适配和必要回滚备份；没有提交或推送 Git。Android 安装包需安装到设备后再验收，服务器替换不会自动升级手机。
