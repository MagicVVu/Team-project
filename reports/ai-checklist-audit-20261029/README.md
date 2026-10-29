# AI 助手单窗口清单核对结果

检查日期：2026-10-29。对照用户提供的《前端AI助手接入任务清单-单窗口版.md》、当前工作区 Android/后端代码，以及 `ssh magicvvu` 读取的实际运行服务。

本次是核对，没有修改 Android 或后端业务代码、部署、服务开关、数据库，也没有调用模型。文件内的开发任务作为待核对要求，不作为本次直接实施或切换协议的指令。

## 结论

清单中的手机端基础公开接口已经全部加入客户端，不需要再新增一套聊天地址。当前并非“所有要求都完成”：主要缺口是最新自主循环的后端适配、90秒聊天预算和状态显示，以及原流程的恢复同步与输入保留细节。

线上后端声明 `conversation_dialogue_protocol=p85-dialogue-1`；公开响应只接受 P8.4/P8.5，`model_calls` 上限为2。AI健康同样声明 P8.5、20秒、最多两次调用。没有证据显示线上已启用 `inventory-autonomous-1`。实测记录见 [server-capabilities.json](server-capabilities.json)。能力声明是从运行容器的现有能力函数读取，并非使用真实用户登录发起端到端业务验收。

## 接口核对

下表“已接”表示已有客户端方法和对应调用链，服务器也已提供相应路由；不等于所有输入和异常场景均已完成线上联调。

| 手机调用的接口 | 结果 |
|---|---|
| GET `/api/v1/agent/execution-capabilities` | 已接，CloudApi.verifiedCapabilities；用于能力及动作检查 |
| GET `/api/v1/agent/conversation` | 已接，窗口恢复、家庭选择与历史分页 |
| POST `/api/v1/agent/conversation/reset` | 已接，仅服务器要求初始化时使用 |
| POST `/api/v1/agent/conversation-turns` | 已接，普通新版消息、自然补充走同一入口 |
| GET `/api/v1/agent/conversation-turns/{request_id}` | 已接；恢复返回字段的处理仍有缺口，见下文 |
| GET `/api/v1/agent/tasks/{task_id}` | 已接，读取当前任务 |
| GET `/api/v1/drafts/{draft_id}` | 已接，读取草稿 |
| GET `/api/v1/drafts/{draft_id}/execution` | 已接，检查草稿执行状态 |
| POST `/api/v1/drafts/{draft_id}/execution-preview` | 已接，复核预览 |
| POST `/api/v1/drafts/{draft_id}/commit` | 已接，确认前持久保存原操作编号和请求 |
| POST `/api/v1/drafts/{draft_id}/cancel` | 已接，正式取消和取消恢复 |
| GET `/api/v1/operations/{operation_id}` | 已接，确认响应丢失后先查询原回执 |
| POST `/api/v1/drafts/{draft_id}/planning-revalidation` | 已接，补货建议依据核对，自动提交仍关闭 |
| 旧 conversation-messages、messages、clarifications、reference-messages、chat-control | 保留，用于旧服务/旧请求及现有表单核对；新版普通聊天优先走 conversation-turns |

方法位置：`frontend/app/src/main/java/com/example/teamapp/data/AgentClient.kt:9`；能力调用在 `CloudApi.kt:40`。现有 App Key 和用户 Bearer 令牌仍由 CloudApi 统一发送。

没有发现需要手机直接调用 AI 内部 understand、resolve、respond 或自主循环工具的要求。这些属于后端与 AI 的适配范围。

## 尚需处理的内容

### 1. 最新自主循环必须先补后端支持（高优先级）

当前实际运行 `magicvvu/backend:p85-memory-20261029`、`magicvvu/agent:p85-0266f64869d7`。后端 `memory_schemas.py:63` 仅接受 p84/p85，`:83` 限制 model_calls<=2；`services/dialogue.py:34` 也只调度已有两种协议。

若要启用清单第8项，需要按 AI 方正式交付契约增加后端自主协议的请求/响应、执行流程、阶段持久化和恢复调度，采用非负计数规则，并落实清单提出的 AI60秒/后端75秒预算与旧请求兼容。不能直接改协议环境变量或只改手机超时。

Android目前保存原始 JSON，没有对 dialogue.model_calls 实施“最多两次”的校验。因此超过两次的主要阻断在现有后端，不能误报为 Android 已经会因次数解析失败。

### 2. 手机的新版长请求读取预算仍为30秒（高优先级，随新协议适配）

`ConversationProtocol.kt:6–11` 目前对聊天和会话恢复使用30000毫秒，其余普通业务请求保持20000毫秒。清单最新自主流程要求90秒，尚未实现相应预算策略。

应根据目标环境正式支持情况与契约，针对可能等待自主流程完成的聊天/恢复请求配置90秒，保留普通业务接口原预算；同时核对后端以及入口代理的预算。原P8.5的30秒是此前明确要求，不能说前次实施本身错误。

### 3. dialogue.status 和 stop_reason 没有专门展示（高优先级）

`AssistantStore.kt:379` 的 acceptMemoryResponse 保存完整 JSON 和 reply，但随后主要按 task 状态呈现业务卡片。`CloudAssistant.kt:177` 显示 AssistantStatus；没有读取 dialogue.status/stop_reason 的呈现逻辑。

自主返回 stopped 时，如果没有本轮任务，当前消息可能只显示普通“已回答”，看不到为何停止。需要分别呈现 completed、needs_input、needs_confirmation、stopped，保留已核实文字/卡片，不因停止自动重新发起推理。对未知类型也应保留回答并作可理解提示。正式库存执行仍以成功回执为准。

### 4. 原消息恢复没有全面同步外层活动任务和 recovery_hint（中优先级）

`AssistantStore.kt:425–444`：completed 会交给 acceptMemoryResponse；processing/prepared/result_unknown 仅更新本地文字/状态，未读取恢复响应外层 active_task，也未使用 recovery_hint。

目前线上 completed 的 response 内已经由服务端刷新了 active_task 和 current_conversation_revision，这条路径已有同步，不能一概认定 completed 总是使用旧任务。缺口主要是其他恢复阶段，以及最新契约若通过恢复外层提供新状态时的处理。

需要把恢复得到的最新活动任务与本轮历史结果分开更新，按照正式 recovery_hint 决定展示及允许恢复行为。原 request_id、完整请求体不能悄悄改写后重交。

### 5. 修订冲突后输入框可能被清空（中优先级）

`CloudAssistant.kt:55–58`：只要本地新增了对应消息记录，就清空输入，不检查发送是否已被明确拒绝。`AssistantStore.kt:409–416` 遇到修订冲突会保存失败并刷新会话，因此这条路径仍满足清空条件。

原文还保存在消息记录中，没有彻底丢失，但不满足任务3/9“冲突时保留用户输入”的要求。应在明确未受理的冲突/权限失败时保留或恢复输入，供用户看完当前状态后决定，不自动变更修订重发。

### 6. 商品规划卡片的计算时间未展示（补充完善）

`AgentResultCards.kt:56–85` 已展示商品汇总、统计范围、未知数据、待购和原因；部分sections也有evaluated_at。但 product_planning 的 as_of 字段尚未展示，清单任务6的“更新时间”不能全部记为完成。应补齐计算时间及可复核来源/依据入口；无需新增聊天接口。

### 7. 完整联合验收仍待完成

上一轮已有67项JVM和42项离线设备测试通过，涵盖十轮修订、改口、超时恢复、并发确认、旧持久确认记录恢复等。它们不能代替真实 AI 理解“喝了一半”“还是两盒”“先别执行”等话语的验证，也不能代替手机—目标后端—AI的长请求、重启登录、跨家庭、权限过期和历史P8.4阶段恢复验收。

本次未新增测试或重新运行生产业务流程；结论来自静态核对和线上只读检查。

## 按清单任务标记

| 任务 | 核对结果 |
|---|---|
| 1 公开接口 | 基础接口已接；自主目标契约尚需同步，线上联调未验收 |
| 2 会话信息和完整响应 | 主要已实现；保留完整响应、本轮task与active_task分开处理 |
| 3 打开恢复与原请求查询 | 已有主链路；需补外层active_task/recovery_hint、冲突保留输入 |
| 4 自然回复与活动任务 | 主流程已实现；新自主状态和未知类型提示待补 |
| 5 同任务候选、补字段和改口 | 已有实现与离线用例；真实语言联合验收待补 |
| 6 统计/风险/补货展示 | 主要已补；商品计算时间等可复核信息仍需完善 |
| 7 正式确认及回执 | 已实现稳定确认和先查回执；生产异常场景联合验收待补 |
| 8 最新自主循环 | 尚未完成，前后端都存在增量，线上AI也仍是P8.5 |
| 9 联合验收 | 离线测试完成部分，完整联合验收未完成 |

## 契约资料的限制

附件引用 `docs/ai-autonomous/contracts/` 及 `docs/ai-autonomous/前后端交接说明.md`，当前工作区没有该目录。通过 GitHub 连接器查询 MagicVVu/Team-project 的默认 dev 分支，上述交接说明、public-response.schema.json、recovery.schema.json 路径均404；main分支交接说明路径也404。搜索未找到自主协议内容。这只能证明已核查位置未取到资料，不能推断其他分支或未公开交付包也不存在。

因此，本次能够确认与附件文字不符的实际缺口，但尚不能独立核验最新自主协议的完整枚举、停止原因和恢复细节。实施前需要同步AI方清单所指的正式响应/恢复Schema、后端OpenAPI和manifest到可访问位置，并确认对应版本。

建议顺序：先补现有恢复和输入保留细节；取得完整自主契约后适配后端与AI部署，再完善90秒及自主状态显示，最后完成隔离环境联合验收。继续使用同一个窗口，不增加会话列表。
