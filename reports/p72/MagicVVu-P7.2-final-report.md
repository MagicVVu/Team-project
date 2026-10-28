# MagicVVu P7.2 总报告

日期：2026-10-20（Asia/Shanghai）。整体状态：**PARTIAL**。本轮完成并验证了候选代码，**没有完成正式部署、真机验收或服务器测试环境清理**。

## 交付结果

| 项目 | 实现/自动化 | 正式部署/手机 |
|---|---|---|
| T01 Release正式HTTPS配置与候选包 | DONE（构建）；整体PARTIAL | NOT_VERIFIED；待团队签名/手机 |
| T02 自然语言续接、独立字段保存、任务绑定 | DONE；联合手机PARTIAL | NOT_VERIFIED |
| T03 受信引用、固定15分钟、幂等、实时重读 | DONE（后端及P7链路）；整体PARTIAL | NOT_VERIFIED |
| T04 OPEN执行/事件/回执/幂等 | DONE（含真实PG并发）；整体PARTIAL | NOT_VERIFIED |
| T05 DISCARD partial/all/终态/审计 | DONE（含真实PG并发）；整体PARTIAL | NOT_VERIFIED |
| T06 真实规划只读快照、消费结构化展示 | PARTIAL；仅真实批次粒度 | NOT_VERIFIED |
| T07 沿用预测算法/数据不足降级 | PARTIAL；缺可信观察/盘点来源 | NOT_VERIFIED |
| T08 自动建议确认执行 | BLOCKED；保持关闭 | NOT_STARTED |
| P7 正式部署 | BLOCKED（SSH/HTTPS/备份/真机前置条件） | 实际部署0服务、0正式迁移 |
| P8 清理长期测试环境 | BLOCKED（安全前置条件未满足） | 实际删除0资源 |

## 已提交代码

功能提交：`3aa98be`，基于用户授权更新后的`55ed275`。本轮源文件清单和SHA256见[evidence/candidate-source-sha256.json](evidence/candidate-source-sha256.json)。提交包含：

- Android：ClarificationReplies、AgentClient、AgentExecutionPolicy、AssistantModels、AssistantStore、CloudAssistant及新单测。
- Backend：execution_schemas/models、agent_gateway、draft_execution路由/服务、shopping_schemas；新增planning_context、0008增量迁移、引用/动作/规划测试；保留新基线单位修复。
- AI：仅原句“它在什么地方”的确定性模板及对应测试；未重写算法。
- tools：便携PG准备、临时真实PG验收、匿名HTTPS复查。

阶段报告与机器证据另作docs提交；提交历史以Git为准。工作区发生外部reset/pull后，已按用户明确答复迁移并重新测试；没有恢复外部清除的P8安全补丁。未强推、未改main。

## 验证与产物

- **120项后端测试全部通过，真实PostgreSQL17.11**。覆盖事务回滚、跨家庭、旧修订/版本、幂等、并发、日期/单位/精度、OPEN/DISCARD及P7引用。0008完成head→0007→head演练。临时数据库已停止并自动销毁。实际日志：[P6-postgres-local.json](evidence/P6-postgres-local.json)。
- **688项AI测试通过**，采用锁定依赖及Windows tzdata；P3/V1算法阈值未改。
- **26项Android JVM测试通过，Release构建成功**；未运行最终手机端到端。共享汇总含实际日志：[verification-summary.json](evidence/verification-summary.json)。
- 契约：[Backend OpenAPI](evidence/backend-openapi.json)、[OPEN/DISCARD/Reference字段schema](evidence/p72-business-fields.schema.json)。
- APK：`frontend/app/build/outputs/apk/release/app-release-unsigned.apk`，SHA256 `9c0b535cadb6180ff88c3699e0f083dcf420740ba718c54a00943c119b29e0bf`。**未签名**，按团队受保护流程签名后安装；APK未进Git。

真实DeepSeek调用、正式账号登录/家庭选择、手机进程重建/恢复、移动网络均NOT_VERIFIED。ASGI链路使用隔离合成库存及真实业务执行，不冒充正式用户数据；原句引用测试在库存移动后返回新位置，模型调用计数0。

## 正式能力与资源

候选源码支持OPEN、DISCARD和trusted_reference_messages；**本轮没有部署，不能说正式已开放**。automatic_planning_commit=false、manual_plan_only=true；现有ADD/MOVE/CONSUME/手动PLAN_ADD保留。

首次只读观察：正式backend/agent/db healthy，0.9.0、isolated_test=false、database ready；Funnel443→127.0.0.1:8000。随后SSH及最新HTTPS复查失败，当前可用性不能确认，详见[P0](P0-environment-audit.md)、[P7](P7-production-deployment.md)。未改正式容器、数据库、用户/库存、卷、Funnel、DNS、密钥、ACL或AI只读账号。

服务器首次有16个容器（11运行），含正式3、长期测试8、已停止5；9网络/11卷。本轮全部保留，**没有减少长期测试服务**，没有空间节省声明。删除白名单为空，详见[P8](P8-server-test-cleanup.md)。

## 未完成事项和接手动作

1. 恢复运维SSH与正式HTTPS连通，重新确认实时服务/依赖。检查P8公网安全待办是否已另行处理；本轮不宣称已加固。
2. 取得最新正式备份，并在独立实例实际恢复；记录现有镜像/路由和回滚配置。当前无法保证回滚，禁止生产迁移或删除卷。
3. 团队签名候选APK，以受控账号/家庭按[P1](P1-android-production-integration.md)完成手机验收，记录原task_id/operation_id与脱敏结果。
4. T06/T07/T08需要持久产品-批次-待购映射、采购偏好/周期版本、完整观察声明和实物盘点来源；已有记录不能由代码补成真实历史。自动确认还缺所有写路径一致锁序与事务内依据重验，详见[P4](P4-consumption-forecast-integration.md)、[P5](P5-auto-replenishment-integration.md)。
5. 满足前置条件后受控部署通过验证的候选功能，核对所有旧动作和新动作；随后按唯一资源白名单归档、试停、复核再清理长期测试。UNKNOWN/SHARED始终保留。

这些阻塞不是已完成事项；目前没有端到端全功能完成或服务器已清理的结论。
