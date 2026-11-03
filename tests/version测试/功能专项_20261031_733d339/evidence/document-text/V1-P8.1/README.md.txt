# V1-P8.1：现有 AI 链路修复

本阶段包含 AI 批次作用域、全部用完、单位契约、采购来源及降级提示修复，并复用现有数据结构补齐后端的摘要、归档、兼容诊断和只读反馈适配。

已按授权归档为 V1-P8.1，并完成服务器同步和正式 AI／后端镜像替换。两个服务均健康，DeepSeek 合成检查通过。发布采用原正式镜像为基底的有限文件叠加，保留其他负责人已有代码和配置，没有执行数据库迁移。详细证据及首次自动回退记录见[正式发布记录](正式发布记录.md)。

- [工作记录](工作记录.md)：实现范围、分工、自动化验证及未完成边界。
- [前后端交接说明](前后端交接说明.md)：字段语义、接口顺序、前端承接及后端核心设计待办。
- [AI OpenAPI JSON](contracts/ai-openapi.json)、[后端 OpenAPI JSON](contracts/backend-openapi.json)。
- [正式 AI OpenAPI JSON](production-ai-openapi.json)、[正式后端 OpenAPI JSON](production-backend-openapi.json)：实际运行导出，正式对接优先查看。
- [本地验证汇总](../../../reports/v1-local-chain-repair/verification-summary.json)。

兼容版本保持 AI `0.7.0`、后端 `0.9.0`、结果 `runtime.release=V1-P7`；新增 `maintenance_release=V1-P8.1` 标识本次维护版本。前端仍应读取接口能力，不能凭版本名称认定某项业务已执行。

商品归组、新表与迁移、完整事件账本、撤销和补货执行事务由后端负责人设计；前端单位展示、按钮导航和新接口承接仍需对应成员完成。人工审核规则没有启用，Jev 保持独立。发布成功也不等于整个 V1 联合验收完成。
