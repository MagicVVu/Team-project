# V1-P8.2：家庭库存助手会话记忆

本阶段已定义为 **V1-P8.2**，完成服务器源码同步及正式 AI／配套后端镜像替换，两个服务健康，DeepSeek 合成上下文检查通过。发布基于原正式镜像，仅叠加本阶段文件；其他负责人代码、运行配置与数据库保持原样，没有执行迁移。前端承接和完整页面联合验收仍待完成。

- [工作记录](工作记录.md)：实现、验证结果与未验收边界。
- [前后端交接说明](前后端交接说明.md)：接口顺序、字段、恢复和前端承接。
- [正式发布记录](正式发布记录.md)：实际镜像、备份、核验及回滚边界。
- **[正式 AI OpenAPI](production-ai-openapi.json)、[正式后端 OpenAPI](production-backend-openapi.json)**：实际运行导出，正式接入优先查看。
- [AI OpenAPI JSON](contracts/ai-openapi.json)、[后端 OpenAPI JSON](contracts/backend-openapi.json)。两份均为本地源码导出，不能据此认定服务器已经提供新接口。
- [受信上下文 Schema](contracts/memory-context.schema.json)、[AI 请求 Schema](contracts/ai-turn-request.schema.json)、[AI 响应 Schema](contracts/ai-turn-response.schema.json)。
- [公开消息 Schema](contracts/public-message.schema.json)、[重置 Schema](contracts/public-reset.schema.json)、[消息响应 Schema](contracts/public-response.schema.json)、[历史分页 Schema](contracts/public-history.schema.json)、[恢复 Schema](contracts/public-recovery.schema.json)。
- [离线150条评测](../../../reports/session-memory/offline-all.json)、[真实 DeepSeek 合成场景回归](../../../reports/session-memory/provider-all.json)、[首轮模型问题记录](../../../reports/session-memory/provider-initial.json)。

能力边界：当前用户在当前家庭的一段会话、最近30天可读取历史、最近10轮上下文及有来源的任务摘要。库存和执行事实重新读取；聊天记忆不执行库存写入。长期偏好、历史会话列表、通用问答和多 Agent 不在本阶段。
