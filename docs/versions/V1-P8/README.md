# V1-P8：聊天助手优化

日期：2026-10-23。此目录重新用于本次聊天优化；此前同名的安全/DNS阶段记录及 P8.1 临时验证记录按用户要求移除。

本阶段完成五个方向的本地实现：连续对话、任务解释、草稿修改与取消、等待与恢复、独立聊天评测。2026-10-23 经用户追加授权，**正式 AI 已切换至 `magicvvu/agent:p8-0175b52f054c`＋DeepSeek，并通过发布验证**。只替换 AI，后端及数据库保持原样；完整聊天交互仍待后端接口和 Android 发布承接。前端和后端修改、文档、测试、评测保留本地，未提交或推送 Git。

| 交付 | 入口 |
|---|---|
| 本次改动、验证及限制 | [阶段工作记录](阶段工作记录.md) |
| 前后端接入与联合验证 | [前后端交接说明](前后端交接说明.md) |
| 独立评测说明 | [评测说明](评测说明.md) |
| AI 内部接口 | [ai-openapi.json](ai-openapi.json) |
| 后端公开接口 | [backend-openapi.json](backend-openapi.json) |
| 汇总证据 | [validation-summary.json](validation-summary.json) |
| 源码同步及正式运行不变的核验 | [candidate-sync.json](candidate-sync.json) |
| 后续正式 AI 切换、备份及验证 | [正式发布记录](正式发布记录.md)、[production-deployment.json](production-deployment.json)、[production-verification.json](production-verification.json) |

AI 的 P7 消息/结果协议、`0.7.0` 配置入口和 `p7-reply-routing-1` 保持兼容；当前健康检查包含 `chat_policy_version=p8-chat-1`。识别运行版本时结合镜像和此标记，不仅看兼容版本号。`candidate-sync.json` 保留的是最初只同步候选源码时的历史核验，正式切换状态见后续发布记录。

确认业务、库存写入、消费事件、版本、权限、幂等和正式回执继续由业务后端负责。AI 返回草稿或聊天回复均不能标为“已执行”。真机、生产数据库并发及产品完整流程验收单独进行。
