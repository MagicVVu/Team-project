# V1-P8.3：当前后端规划契约适配

2026-10-28 接入汇总：P8.3～P8.5 的最终前后端实施请统一查看[三版本总对接方案](../../handoffs/V1-P8.3-P8.5-前后端统一对接方案.md)。本目录保留本阶段历史证据，重复接入要求以总方案为准。

2026-10-26，Asia/Shanghai。本阶段归入 V1-P8.3；V1-P9 目录仅保留 Jev 独立模块阶段记录。

本阶段在本地开发 AI 适配、测试和契约，不同步服务器，不替换正式镜像，不提交或推送 Git。正式后端已发布的 `V1-P9` 名称、0011 迁移及历史证据保持真实原名，不因文档归档位置变化改写生产历史。

## 交付入口

- [工作记录](工作记录.md)：归档、实现、验证与未完成事项。
- [前后端交接说明](前后端交接说明.md)：调用、字段、状态及责任边界，正文列出 JSON 契约。
- [AI OpenAPI JSON](contracts/ai-openapi.json)：本地 P8.3 AI 接口总入口。
- [后端 OpenAPI JSON](backend-openapi.json)：后端负责人提供的接口快照，原文件内容保留。
- [验证记录](../../../reports/p83-planning/validation-summary.json)：本轮测试及适用范围。

## 后端原始交接材料

以下 7 个文件从 V1-P9 原样迁入，文件名中的 `p9` 指后端当时的开发与发布标识。原文的“AI 待适配”是交付时状态；本阶段实际完成情况以工作记录和交接说明为准。

| 文件 | 用途 |
|---|---|
| [backend-ai-p9-baseline.md](backend-ai-p9-baseline.md) | 后端开发前基线 |
| [backend-ai-p9-contract.md](backend-ai-p9-contract.md) | 商品、来源、账本及重验契约 |
| [backend-ai-p9-handoff.md](backend-ai-p9-handoff.md) | 后端交给 AI 的适配清单 |
| [backend-ai-p9-implementation.md](backend-ai-p9-implementation.md) | 后端实现及责任边界 |
| [backend-ai-p9-test-report.md](backend-ai-p9-test-report.md) | 后端原始测试证据 |
| [backend-ai-p9-production-release.md](backend-ai-p9-production-release.md) | 既有后端生产发布历史 |
| [backend-openapi.json](backend-openapi.json) | 后端接口定义 |

`reports/backend-ai-p9`、后端镜像标签及迁移文件仍保留历史名称；没有迁移、重跑或覆盖生产验收证据。关联的文档链接、导出目标和测试文件路径已更新。Jev 原记录及实现不修改。

## 能力边界

AI 已能保留并校验规划来源、读取显式商品聚合、输出未知待购状态、区分消费与库存更正、携带精确的新 basis，并在收到重验请求后重新读取和生成只读建议。

当前后端尚未提供商品整体已审定可用量、完整记录覆盖及商品级偏好策略，AI 明确输出这些缺口，不继承某一批次的证明。规则审核、采购专用反馈协议、自动建议事务提交、Android 新字段承接和正式联合验收分别由对应成员继续推进；本阶段不把它们标为已完成。
