# Android 新会话流程接入

2026-10-29，Asia/Shanghai。

## 已完成

- 打开助手先通过 `GET /api/v1/agent/conversation?household_id=...&limit=20` 恢复当前会话、修订、历史和活动任务。只有服务器明确 `requires_reset=true` 且没有未核实新回合时初始化 reset，不在每次打开时清空会话。
- 按 next_cursor 加载更早历史，按 request_id 去重；历史与当前活动任务分开，不以旧气泡状态替代当前草稿状态。
- 新消息走 `POST /api/v1/agent/conversation-turns`。发送前持久保存原文、稳定 request_id、conversation_id、conversation_revision，以及成对的 task_id/revision（有活动任务时）。不上传内部 context、archive、basis 或猜测的批次事实。
- POST 超时或响应丢失时先 `GET /api/v1/agent/conversation-turns/{request_id}?household_id=...`。completed 使用保存响应；processing/result_unknown 只查询、不重新理解；prepared 经用户点击恢复后才按原ID和完整原请求继续。明确未找到原请求时也不会自动换ID重发。
- 会话和发件箱按服务器地址、用户、家庭隔离。应用重建、重新登录后可查询恢复同一身份的原请求；会话历史与本地请求中不保存明文登录令牌。
- 完整公开回合响应保存到 conversationResponse，包括 dialogue、evidence、活动任务等后续卡片展示所需字段。下一条消息采用 current_conversation_revision，保留原请求修订以便幂等恢复。
- 新聊天不再先调用旧 chat-control 或旧 reference-message 流程。候选和批次续接沿用受信顺序，业务确认仍走既有草稿/操作回执链。
- 新会话、初始化与恢复请求读取超时为30秒；普通业务请求保持20秒，连接超时保持5秒。继续由现有 CloudApi 发送 App Key 和用户 Bearer 登录令牌，未替换认证配置。
- 窗口预填消息先等待会话恢复；初始化失败时保留输入框原文。新会话边界不会删除旧发件箱或操作回执。

旧协议保留用于既有请求恢复及未声明会话记忆能力的服务，新消息按 capabilities 选择新版流程。

## 修改位置

- AgentClient.kt：公开会话 GET、reset、turns 和原请求恢复方法。
- AssistantStore.kt：持久化选择器、会话恢复、历史分页、超时查询、活动任务同步。
- AssistantModels.kt：保存完整回合响应、历史标志及所属会话。
- ConversationProtocol.kt / CloudApi.kt：按路由设置读取超时，保留认证与网络校验。
- CloudAssistant.kt：打开恢复、较早历史入口、历史只读呈现和预填消息顺序。

路径均位于 frontend/app/src/main/java/com/example/teamapp/。

## 验证

Android 编译、debug APK 与测试包构建成功。JVM 单元测试 **67项全部通过**，含新增会话读取超时策略用例。

独立 Android 36 无界面模拟器：**12项全部通过**，包含8项新会话测试和4项旧批次、预览、取消兼容测试。覆盖打开恢复、分页去重、必要时初始化、原文与选择器保存、响应丢失只查询、未完成轮次可恢复、应用对象重建后按原请求继续、结果未知不重新理解、重新登录后查询原请求和活动草稿独立保留。

测试使用完全离线的 HTTP 边界夹具，没有使用生产账号、写生产库存或调用付费模型。未据此声称生产用户端到端联调已经通过。本次没有修改或重新发布服务器后端。

构建日志：build.log；设备测试日志：instrumentation.log；摘要和APK摘要：validation.json。Gradle 保留原有 compileSdk 37.1 与插件测试上限37.0的提示，本轮未升级构建工具链。

## 安装包

`frontend/app/build/outputs/apk/debug/app-debug.apk`，debug测试包，默认沿用现有服务器地址 `https://8.134.172.165:8000`。用户可安装后使用自己的现有账号验证；本轮仅安装到新建独立模拟器。

构建命令（使用现有 JDK/SDK）：

```powershell
./gradlew.bat :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest --offline
```

本轮启动的独立测试模拟器位于项目 .cache/android-p85，测试后关闭；未使用或清空已有模拟器。
