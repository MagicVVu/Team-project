# AI、后端、Android 三端对接复核报告

审计日期：2026-10-24（北京时间）。代码基线：`dev / 630b0145c85adf7f32726ad2fe9a68ab02691573`，提交说明“完成了前端对接”。已通过 GitHub 连接器确认远端 `dev` 同为此提交。本次复核覆盖新前端提交，不能再把上一份报告的全部待办当成现存缺口。

**结论：主要页面和基础接口已经接上，但还不能认定三端功能全部闭环。最先要修的是指定批次的 AI 查询、全部用完、采购来源和数量单位展示；随后补齐共享回执、归档与反馈。**

这次仅新增审计报告、复现脚本和证据，没有修改三端业务代码或部署服务器。

## 1. 范围与服务器基线

逐模块检查当前运行链路所用的源码：AI 的 `p0/p1/p2/p3/interaction/v1/conversation` 共 **73 个 Python 文件、6,196 行**；后端 `app` 共 **43 个 Python 文件、4,823 行**；Android 主源码共 **51 个 Kotlin 文件、7,691 行**。同时检查接口 DTO、迁移、相关测试、新提交的实现报告与界面验证记录。文件哈希、路由声明和前端调用索引见 [source-index.json](source-index.json)。历史评测数据、构建缓存和非运行时演示代码不计入这些源码数字。

通过 `ssh magicvvu` 只读检查了运行中容器、后端 OpenAPI/能力开关、AI 健康状态与 Alembic 版本。未读取或导出用户业务记录、凭据和私有配置，未调用正式模型或执行业务写入。

| 项目 | 实际状态 | 对审计的含义 |
| --- | --- | --- |
| 后端 | `magicvvu/backend:p8-771374b-20261024`，healthy | 本地 `771374b..630b014` 的 AI/后端运行源码没有差异 |
| AI | `magicvvu/agent:p8-0175b52f054c`，healthy，DeepSeek | 健康标签仍为 V1-P7，同时有 `p8-chat-1`；不是仅凭版本名判断能力 |
| 数据库 | PostgreSQL 17，healthy；迁移 `20261023_0010` | 规划资料表已上线 |
| 业务执行 | ADD/MOVE/PLAN_ADD/CONSUME/OPEN/DISCARD 均开启 | 后端支持六类动作的草稿确认执行 |
| 会话 | `backend-conversation-1`；可信引用、chat controls 均开启 | 新前端会话与批次引用接口有服务器支持 |
| 规划资料 | `backend-planning-facts-1`；规划上下文 `v1-planning-context-1` | 四类资料可以正式写入并被 AI 读取 |
| 自动补货提交 | `automatic_planning_commit=false`、`manual_plan_only=true` | 计算建议直接确认仍不可用 |
| 风险规则 | `active_human_rule_count=0` | 实际评估会受已审核规则缺失阻塞，见 G1 |
| 音频上传 | `audio_upload_supported=false` | 手机系统语音转文字不等于云音频理解 |

AI 的 `frontend_integration_verified=false` 是当前代码中的固定健康字段，不能单独据此推断前端未做测试。新前端已有离线测试证据；真实手机与当前服务器的新链路联合验收仍未完成。

## 2. 已经接上的功能

“已接上”指源码调用与接口契约存在，且相关后端基础链路有测试支持；不代表本次做过正式账号的手机验收。

| 模块 | 当前链路 | 判断 |
| --- | --- | --- |
| 登录、注册、资料、退出 | Android → 后端认证/个人资料 | 已接；真实短信验证不是当前能力 |
| 家庭创建/加入/切换/邀请/成员 | Android → households/member APIs | 已接 |
| 成员权限、移除、退出、转让、解散 | 新 FamilyManagement → 后端角色接口 | 已补上；需要多账号真实联验 |
| 库存 CRUD、版本冲突、普通盘点修正 | Android → inventory APIs | 已接；修正不冒充消费 |
| 正式消耗 | 云端“消耗”改为批次查询 → 可信引用 → 草稿 → 确认 → Consumed | 已改正旧版 adjustments 充当消耗的问题 |
| 开封、部分/全部丢弃、移动、新增 | AI 草稿 → 后端执行/预览/回执 | 基础能力已接；“全部用完”另有 F2 |
| 四类规划资料 | preferences/stock_verification/coverage/risk_facts GET/PATCH | 已有表单、版本、来源、显式清除、持久原请求恢复 |
| 资料进入 AI | 后端投影 → internal planning/inventory reader → AI | 后端集成测试覆盖，失效后不会继续当成有效证据 |
| 消耗、预测、风险、补货、概览结果 | AI result → Android 结构化卡片 | 已有展示；批次作用域与包装单位仍有 F1/F3 |
| 消费流水 | 家庭 consumption-events → 分页、批次筛选 | 已接 Consumed；跨成员回执和完整时间线仍有缺口 |
| 新建采购来源 | 新采购表单 → source_inventory_item_id | 已接；AI PLAN_ADD 和旧采购修改来源仍缺，见 F4/G3 |
| 购买入库 | purchase → 独立新批次 | 已接，有幂等防重复；不是同商品跨批次规划聚合 |
| 草稿取消与恢复 | 原请求持久化、回执核实、取消后会话清理 | 新提交已补强，不再沿用旧报告的“未实现”结论 |
| 语音文字输入 | 系统识别 → 填入输入框 → 人工发送 | 已接文字流程；没有 AI 音频上传 |
| 分类与单位 | canonical 分类/单位，药品单列 | 新输入明显改善；旧数据/第三方直接写接口仍需兼容治理 |

## 3. 已确认的具体断点

### F1 · P1：指定批次的统计、预测、风险和补货没有正确沿用可信引用

**涉及：AI 编排为主，前端需要跟进验收。**

前端 `BatchOperationsPanel.kt:71–74` 分别发送“查看它最近28天的消费统计”“这批还能用多久？”“评估这批的风险……”等文字；`AssistantStore.kt:299` 先取得真实来源任务，再调用 reference-messages，确实带了当前批次。

但 `agent/conversation/manager.py:179` 对不在 P1 Intent 集合中的意图直接委派旧管理器。QUERY_CONSUMPTION、QUERY_FORECAST、QUERY_RISK、SUGGEST_PURCHASE 都走到这里，未进入后面的批次绑定。旧规划/风险管理器也没有消费这份可信引用。

用**合法、固定的理想字段提取结果**隔离模型误差后，复现如下：

| 页面动作 | 带有效 b1 引用后的实际结果 |
| --- | --- |
| 还能用多久 | needs_clarification，重新要求 name；reference_used 为空 |
| 风险与缺失资料 | needs_clarification，重新要求 name |
| 本次 AI 补货建议 | needs_clarification，重新要求 name |
| 消费统计（“它”） | answered，但 planning selector 为 `name=null,item_key=null`，事实含 b1 和 b2，扩大为全家庭 |

这不意味着正式 DeepSeek 每次都会返回同样的提取 JSON；它证明：**即使模型正确提取意图，当前编排仍无法保证“问这批”只查这批。** 不应通过改成按名称查询掩盖问题，同名多批次仍会歧义。

需完成：这些只读意图在经过权限、TTL 和当前批次读取后，显式使用受信任的 batch/item selector；未知指代必须继续要求明确选择。验收至少包含同名两批与不同名两物品，确保不扩展作用域。

证据：[offline-probes.json](offline-probes.json)，case forecast/consumption/risk/restock。对照 case consume_control/discard_control 能正确绑定 b1，说明不是引用接口整体不可用。

### F2 · P1：“全部用完”没有形成读取当前全部余量的闭环

**涉及：AI 全量消费语义、前端操作文案和编辑规则。**

`BatchOperationsPanel.kt:68` 发送“这批已经全部用完”，并向用户承诺按服务器全部余量准备草稿。当前 conversation 分支将它按普通 CONSUME 处理，跳过 V1 的 literal finish 编排。固定提取 `intent=CONSUME, quantity=null, unit=null` 时，实际返回缺 quantity/unit，没有草稿。

同时，后端 `editable()` 只保护 DISCARD all；CONSUME 的 quantity/unit 一般仍可编辑。前端把 FINISH 与 DISCARD_ALL 一起显示“数量、单位及模式不可编辑”，这项承诺也尚未完整落实。

需完成：将可信批次引用与“全部用完”语义组合，由服务器当前批次读取数量与单位、保留版本校验，并决定全量消费是否保护数量字段；如果允许改为部分消费，应明确改变操作语义与预览。最终仍要求人工确认，生成一个 Consumed 事件及 FINISHED 状态。

证据：[offline-probes.json](offline-probes.json)，case finish。原有 V1 按明确名称“牛奶用完了”的测试通过，不代表新批次页面的指代路径已覆盖。

### F3 · P1：补货卡把库存单位与订货包装单位混用

**涉及：AI 结果契约和前端展示。**

AI `p3/procurement.py` 设置包装量后，只把建议数量换为订货单位；current_stock、pending_quantity、target_stock 仍是库存单位。Recommendation 只有一个 unit 字段。Android `AgentResultCards.kt:75` 把四个数量统一加上这个 unit。

合成例子：库存 2 **盒**、待购 1 **盒**、目标 20 **盒**、每 **包** 6 盒，建议购买 3 **包**。目前卡片会把前三个值也显示成 2 包、1 包、20 包。

需完成：契约区分库存单位和建议订货单位，或前端从同 item_key 的 forecast/facts 明确取得库存单位；展示包装换算依据。不能猜测转换，也不能对全部字段套 recommendation.unit。

证据：[offline-probes.json](offline-probes.json)，case pack_units。当前生产规则缺失常会提前阻塞有效建议；这是包装建议可用时会暴露的确定性契约问题。

### F4 · P1：AI 手动采购草稿没有保留库存来源，进而阻塞待购计算

**涉及：后端执行、AI 采购契约、前端来源修正入口。**

新前端的普通新建采购可以明确关联批次，但 AI PLAN_ADD 执行时，`backend/server/app/services/draft_execution.py:338` 创建 ShoppingListItem 没有 source_inventory_item_id。即使商品在当前库存中已有记录，手动采购也会成为未关联待购。

后端规划投影只认可显式外键关联：任何未购项无法关联时，整个快照 `pending_complete=false`；AI 补货算法拒绝在待购不完整时给出确定建议。因此“聊天加入采购成功”后，下一次 AI 补货可能反而不能计算。前端又不能修改旧采购来源，用户没有原位修复入口。

临时 SQLite 实测：同名同单位 PLAN_ADD 执行成功，source_inventory_item_id=null，规划 pending 为空、pending_complete=false。

需完成：允许经过明确选择/可信引用验证的来源进入采购草稿和正式执行；保留新物品明确无关联的语义。禁止仅按同名自动关联。并补充旧记录来源编辑（G3）。可进一步明确无关新商品的未知待购是否需要阻塞所有商品的补货，应有完整性边界契约。

证据：[backend-probes.json](backend-probes.json)，case manual_ai_plan_loses_inventory_source。

### F5 · P2：共享消费流水有回执按钮，但其他家庭成员读不到原回执

**涉及：后端读取权限契约、前端条件展示。**

consumption-events 按家庭成员授权，返回全家庭的事件。`ConsumptionEventsPanel.kt` 对每条事件都显示“查看原业务回执”。但 `draft_execution.py:140` 的 operation_for 限制 `DraftOperation.user_id == 当前用户`。

临时数据库实测：成员 B 能以 200 读取成员 A 的消费事件，但点同一 operation 的回执返回 404 OPERATION_NOT_FOUND。

需完成：设计一份家庭成员可读、去除私人对话/账号信息的业务回执摘要，或在事件中给出回执可见性并限制按钮。不要直接放开私人 task、draft 的所有者权限。事件还应提供执行者和稳定摘要，避免流水只能显示 UUID。

证据：[backend-probes.json](backend-probes.json)，case shared_event_private_receipt。

### F6 · P2：AI 补录弹窗中的“盘点修正库存”没有接到操作

**涉及：前端导航。**

库存详情入口有传入 adjust 回调；但 `CloudAssistant.kt:249` 从 AI 卡片打开 PlanningFactsPanel 时，没有传回调，而组件参数默认 `adjust = {}`。此处进入库存盘点分区后，点击“盘点修正库存”没有任何操作。

需完成：接入实际库存修正导航，修正后刷新当前库存与 facts，再要求用户重新盘点确认。预测、补货和消费卡的资料/流水入口也可以沿用 item_key 直接定位当前批次，现有 `facts("", ...)` / `events("")` 会让用户再次选择。

证据：PlanningFactsPanel.kt:26、140；CloudAssistant.kt:249；AgentResultCards.kt:53、71、81。此项为源码确定性调用分析，本次未操作模拟器。

### F7 · P2：全部丢弃后，批次的常规详情/历史读取没有闭环

**涉及：后端归档读取、前端历史入口。**

后端库存列表固定只返回 ACTIVE/FINISHED（`routers/inventory.py:68`），没有公开库存单项 GET 或归档状态筛选。全部丢弃后变为 DISCARDED，刷新后不再出现在 cloud.items。前端的生命周期和终态操作限制虽已补充，但没有可重新打开该批次的归档入口；丢弃也不进入仅含 Consumed 的消费流水。

临时数据库实测：全部丢弃 committed，批次 DISCARDED，库存列表 total=0。原执行者若保留助手历史仍可看原回执，这不等于全家庭可浏览归档批次。

需完成：库存详情 GET、明确的归档筛选/分页与前端历史入口；结合统一事件时间线，查看开封、丢弃、移动、增加、修正等记录。不能把消费流水称为全部业务历史。

证据：[backend-probes.json](backend-probes.json)，case discarded_batch_not_publicly_listed。

## 4. 后端/AI 尚未交付的能力与当前边界

这些项目需要明确是否纳入当前版本，不能通过多加一个前端按钮解决。

| 编号 | 尚未闭环的能力 | 现状与下一步 |
| --- | --- | --- |
| G1 | 可实际使用的审核风险规则、具体商品规则关联 | 生产 active_human_rule_count=0；HumanRuleCatalog 只启用人工审核规则。有效在库批次会返回 NO_APPLICABLE_RULE/unknown，并阻塞通常的补货可用库存判断。需要真正审核、记录来源并发布规则。后端 product_id 始终 null，也还无法匹配具体商品的开封窗口规则；需要真实商品关联。不能把“已核对”标志当成审核工作已完成。 |
| G2 | 执行后 AI 反馈 | AI 已有 `/feedback/after-commit`，可核对真实回执与新状态；后端只有内部 receipt adapter，没有公开反馈路由，也没有确认后触发反馈的链路。Android 当前展示正式回执并刷新，未获得执行后的风险/规划反馈。应在业务成功后独立触发反馈，失败不回滚或重复执行业务。PLAN_ADD 无 batch_versions，还需定义适用范围。 |
| G3 | 修改/清除旧采购来源 | ShoppingItemUpdate 仅 name/quantity/unit，未提供 source_inventory_item_id；新前端只在创建时发送关联。应支持明确选择、同家庭验证、单位一致性/明确换算及版本冲突处理；已购项的来源不可随意重写。 |
| G4 | 自动计算补货建议 → 重新校验 → 确认采购 | 服务器明确关闭 automatic_planning_commit，执行端返回 PLANNING_REVALIDATION_UNAVAILABLE。需要后端按确认时快照重算并核验库存、事件、偏好和待购版本，保存计算来源；不能把建议改标为手工输入绕过校验。此项是尚未交付的进阶能力，不是前端漏按钮。 |
| G5 | 不依赖模型的纯结构化批次操作草稿 | 目前没有公开“按 batch_id/action/quantity 创建草稿”的接口。新页面仍先查来源再发送自然语言，依赖模型理解、两轮任务及引用 TTL。可增加后端受认证的结构化 prepare API，复用现有预览/确认/幂等机制。此项属于稳定性与成本改进，现有自然语言操作并非整体不可用。 |
| G6 | 跨批次的商品级消费与补货规划 | 后端把 item_key 设为库存批次 ID，每个 item 只有一个 batch；采购入库创建另一个 batch，历史、coverage、偏好、盘点不形成统一商品序列。AI 算法已能处理一个商品下多批次，但业务层尚无真实 product/item 身份映射。若产品目标是“牛奶整体还能用多久”，需要明确商品实体、单位和批次关联；不能仅凭同名合并。 |
| G7 | 全量、可追溯的业务时间线与纠错 | 公开接口只有 Consumed 事件；普通库存 CRUD/adjustments/购买入库主要存 history_json，最多保留 30 条，不统一进入 BusinessEvent。AI schema 中 Reversed/Corrected/Adjusted/related_event_id 等尚无完整业务写入和撤销/纠正接口。应先统一事件持久化、权限及读取，再设计撤销或纠正；绝不能把盘点差额算成消费。 |
| G8 | 旧库存与直接 API 输入的 AI 兼容治理 | 新前端限制名称/单位，但后端普通 CRUD 仍接受比 AI 更宽的名称/单位。AI adapter 遇到不兼容旧记录会拒绝完整读取；分类中文旧值也可能成为 unknown。需要兼容性检查与显式修复流程，不能默默截断、猜容量或忽略记录。 |

G1 的离线佐证见 [offline-probes.json](offline-probes.json)，case no_human_rules：批次资料完整、盘点与历史基础可用时，0 个可用人工规则仍返回 unknown；补货状态 needs_review / USABLE_STOCK_REQUIRES_REVIEW。用户补齐四类资料不能替代平台提供审核规则。

## 5. 不是本轮“漏接接口”的功能

| 功能 | 三端实际边界 |
| --- | --- |
| 图片识别、OCR、照片云同步 | 前端可以拍照/选图并本机保留，但没有已部署的 AI 图片识别或照片上传契约 |
| 云 ASR、上传音频、TTS | 当前仅系统语音识别后的文字录入；AI 不接收音频 |
| 系统推送、WebSocket、后台实时提醒 | 当前主要为页面内提醒、轮询和设备设置，没有服务端推送基础设施 |
| 设置跨设备同步、位置目录 | 外观、语言、提醒天数/开关、快捷位置主要存在设备本地；不应误认为家庭云配置 |
| 短信验证码、找回/修改密码 | 当前账号流程未提供这些完整公开接口；不属于“AI 端已有但前端没接”的能力 |
| 在线用户意见工单 | 现有“帮助与反馈”使用系统分享，没有在线工单提交/处理闭环；与 G2 的 AI 执行反馈是两件事 |
| release 正式发布配置 | 当前主要验收 debug 测试 APK；release 的 HTTPS origin 需显式配置，不能把 debug 已直连等同正式发布已完成 |

## 6. 测试与证据的实际边界

| 验证 | 本次结果 | 能说明什么 |
| --- | --- | --- |
| AI 会话/V1/P8 相关回归 | **225 passed**，已有锁定环境 fastapi 0.135.1 / pydantic 2.12.5 | 现有 AI 基础能力没有在这些旧测试中失败；不涵盖全部新页面生成的指代请求 |
| 后端资料、真实 AI 编排、会话、开封/丢弃、规划、控制、执行回归 | **267 passed、21 skipped**；临时 SQLite | 基础后端链路可用；跳过 PostgreSQL 专属用例，不能据此声称本次做过 PostgreSQL 并发回归 |
| 新增 AI 离线探针 | 9 个案例，含两个正常操作对照 | 复现 F1/F2/F3、佐证 G1；固定提取隔离模型误差，不是正式 DeepSeek 联验 |
| 新增后端离线探针 | 3 个案例，临时数据库自动销毁 | 复现共享回执权限、采购来源丢失、丢弃后列表不可见 |
| 服务器检查 | AI/后端/DB healthy，接口/能力/迁移已核对 | 运行版本与路由存在；没有用真实家庭做写入验收 |
| Android | 本次静态复核新源码和既有测试/截图记录 | 上次实现记录为 37 单测、44 相关回归、17 专项（集合重叠）；本次没有重新跑 Android 或实体机，不累加为本次结果 |

最初用共享后端 `.venv` 跑 AI 测试出现两个 OpenAPI 快照比较失败（223 passed/2 failed），原因已定位为该环境 FastAPI/Pydantic 与 AI 锁定版本不同，差异见 [openapi-differences.json](openapi-differences.json)。随后切换已有匹配锁定依赖的 AI 环境，225 项全部通过；没有为让测试变绿而改业务代码、快照或安装新依赖。两次 XML 均保留，避免隐藏过程。

当前 Android 专项把 AgentClient 替换为 FixtureAgent，能验证“是否发送 referenceMessage”，不能证明真实 AI 会将该请求绑定到正确批次。需要新增覆盖**页面实际生成文本 → 真 AI 编排 → 真后端读取**的离线跨端用例。

## 7. 建议实施顺序和完成标准

1. **先修当前路径**：F1 批次查询绑定、F2 全部用完、F4 AI 采购来源；同步修 F3 包装单位展示。用户的选择、数量语义和待购依据必须可靠。
2. **再补可追溯性与操作入口**：F5 家庭可读回执摘要、F6 盘点导航、F7 归档批次读取，以及 G3/G7 的采购关联和时间线。
3. **让现有规划真正可用**：处理 G1 审核规则与具体商品关联、G6 商品/批次模型及 G8 兼容记录。保留缺数据降级，不能强行返回预测或采购量。
4. **完成现有 AI 能力的业务封装**：G2 执行反馈；视产品需求做 G5 结构化 prepare。自动规划提交 G4 应单独交付和验收。
5. **用专用测试家庭做新 APK 的真实联合验收**，至少覆盖下表；现阶段不能用“新增页面有截图、旧测试通过”作为三端全部对齐的结论。

| 必验场景 | 完成标准 |
| --- | --- |
| 同名两批，询问其中一批的风险/预测/消费/补货 | 返回对象唯一匹配所选批次，不扩展到家庭或同名其他批次 |
| 全部用完，确认前另一个成员修改数量 | 重新核对/冲突提示；不错误扣减，不重复事件 |
| OPEN、部分/全部 DISCARD | 正式回执、生命周期和归档历史一致；丢弃不计消费 |
| 1 包 = 6 盒的包装采购建议 | 库存/待购/目标用盒，建议购买用包，换算来源清楚 |
| 聊天创建关联采购后再查补货 | 来源被保留，已有关联待购正确抵扣，不变成未知待购 |
| 一个无库存关联的新商品待购 | 明确显示完整性影响；不伪造关联或假定待购为零 |
| A 消费、B 查流水和回执 | B 能读业务许可范围内的摘要，私人任务和对话仍受保护 |
| AI 补录入口发现盘点差异 | 按钮进入真实修正，完成后重读版本并重新核对 |
| 切换家庭、退出重登、请求超时 | 资料/任务/回执不串家庭；结果未知时沿用原 ID 与正文 |
| 四分区资料及他人并发修改 | 409 后保留表单、显式重审；未知不当成零或 false |
| 记录缺口、盘点过期、无适用规则 | 清晰展示不足原因，不给假预测，不反复要求用户填写平台规则 |
| 家庭转让、移除、退出、解散 | 两账号权限即时生效，旧账号不能继续操作 |

## 8. 复现方式

在仓库根目录运行；仅使用合成数据，后端脚本创建临时 SQLite，并强制关闭 PG 测试模式。Windows asyncio 需要本地回环事件循环正常可用。

```powershell
.cache/p2-agent-venv/Scripts/python.exe -X utf8 reports/three-end-integration-20261024/audit_probes.py
.venv/Scripts/python.exe -X utf8 reports/three-end-integration-20261024/backend_probes.py
```

主要证据：[AI 探针](offline-probes.json)、[后端探针](backend-probes.json)、[AI 锁定环境测试](ai-locked-tests.xml)、[后端测试](backend-tests.xml)、[源码索引](source-index.json)。服务器观测值见本报告第 1 节，均为只读核验。
