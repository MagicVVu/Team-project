# V1-P7：家庭库存 AI 助手接入准备

日期：2026-10-17。AI 入口 `conversation.app:create_app`，版本 **0.7.0**，策略 `p7-limited-context-1`，提示 `p7-extract-1`。

本阶段只修改 AI、测试、评测、运行构建文件及文档。Android、正式后端和数据库任务网关未修改，没有新增 Mock 服务、演示页面或聊天数据库。

| 交付维度 | 状态 |
|---|---|
| AI 实现 | 已实现受信引用、当前库存重读、原任务澄清和确定性回复解析 |
| 前端承接 | 待实现；现有窗口仍主要展示文字回复 |
| 后端可执行 | 已有新增、位置编辑和清单新增接口；独立草稿确认、消费事件、开封和丢弃等仍需协作 |
| 联合验收 | 待执行，不能以夹具测试或代码同步代替 |

文档入口：

- [实施范围与分工](development-plan.md)
- [AI 接口与引用契约](ai-contract.md)，[AI OpenAPI](ai-openapi.json)
- [前端接入交接](frontend-handoff.md)
- [后端协作交接](backend-handoff.md)
- [验收场景与验证记录](acceptance.md)
- [交付与验证结果](delivery-and-validation.md)
- [实现状态](implementation-status.json)

运行代码按模块同步到 `~/workspace/agent/conversation` 等对应目录。文档、契约导出、测试和评测只保留本地 Git 工作区，不上传服务器。同步不等于线上切换；本轮不提交或推送 Git。
