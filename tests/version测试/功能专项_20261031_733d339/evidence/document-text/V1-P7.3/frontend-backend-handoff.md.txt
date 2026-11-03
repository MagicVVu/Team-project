# V1-P7.3 前后端接入交接

日期：2026-10-20，Asia/Shanghai。**本文件对应本地补丁，尚未同步服务器。** 部署前后端需核对实际代码／镜像摘要，不能仅凭 AI 仍报告0.7.0就判断已有这些修复。

阶段实现、测试与未验证范围见 [工作记录](implementation-record.md)。前一轮全部产品缺口见 [V1-P7.2综合交接](../V1-P7.2/chat-assistant-team-handoff-20261020.md)，数据库迁移依据见 [远端数据库分析](../V1-P7.2/remote-database-review-20261020.md)；后两份属于检查时快照，实施前重新核对。

## 1. 本次交给队友的变化

| AI本地已经完成 | 前端需要承接 | 后端需要承接 |
|---|---|---|
| 常见位置指代问法零提取 | 保留原文，有对象时走受信引用流程，无对象时要求选择 | 核实来源任务、修订、批次与15分钟期限，再传内部引用 |
| 四种续接结果与样例 | 主输入框按四结果路由，独立保存每个字段 | 原澄清接口校验权限、修订、有效期、允许字段；继续持久化任务 |
| 六类草稿、业务精度校验 | 显示正确字段、来源及前后摘要，不截断或舍入 | OPEN／DISCARD仍需迁移与事务；所有动作确认复核版本 |
| 统计／预测／补货降级 | 根据状态和原因展示，不把缺失当零 | 提供可信规划快照与事实来源；自动建议确认前重验 |
| 完整离线场景覆盖 | 最终APK补窗口关闭、应用重建及网络中断验收 | 真实PostgreSQL、两账号家庭隔离、幂等和并发验收 |

不重写已有 AI 算法、不替换现有数据库任务网关、不新增 Mock 服务。AI 返回草稿不是已执行结果。

## 2. 主输入框路由顺序

1. 从当前已认证用户／家庭加载当前活动任务；没有活动任务时按新请求处理。
2. 有活动任务时，先解析明确补充、候选与重置；以原任务 allowed_fields 和候选修订为依据。
3. 根据 clarify/new_task/needs_input/clear_reference 执行以下契约。路由不能调用付费模型，也不能改写用户原文。
4. 请求体持久保存后再发送。澄清结果未知时封存原 body；先恢复，不用不同内容覆盖相同修订的未知请求。
5. 用户明确换话题可新建任务；旧任务保存但不继续作为当前引用。不要以列表最后一条自动决定所有后续输入。

## 3. resolve_reply 接入契约

代码：[conversation/replies.py](../../../agent/conversation/replies.py)。这是 Python 调用方纯函数／行为规范，**不是已提供给 Android 的文字续接 HTTP API**。

建议后端调用适配层复用该函数或同一版本的共享包，前端发送用户原文与当前任务关联；若必须在 Kotlin 解析，则以本契约和测试实例做一致性验证，不能另写一套不同规则。需要新增公开适配接口时由后端先交 OpenAPI，不自行假定一个路径已经可用。

### 3.1 输入

```python
resolve_reply(binding, original_text, scope, trusted_now,
              selected_batch_id=None)
```

| 输入 | 含义与可信来源 |
|---|---|
| binding.scope | 业务调用方核实的当前用户＋家庭 |
| binding.task | 已鉴权读取的最新完整公开任务，含task_id、revision、status、result、有效期 |
| binding.household_timezone | 从家庭或原任务加载的IANA时区；默认上海仅兼容本地测试，不从手机当前时区猜测 |
| original_text | 用户真实原文，最多1000字符；调用方另外完整保存 |
| scope | 当前已认证身份，与binding一致；不由客户端随意指定 |
| trusted_now | 可信带时区时间，用于过期和日期辅助校验 |
| selected_batch_id | 当前修订中用户已明确选择的真实批次；不能默认第一批 |

BoundTask本身不是签名或权限证明。构造之前后端必须验证任务用户归属、家庭成员关系及最新修订；函数只核对传入的可信绑定，不代替数据库查询。

### 3.2 四种输出

所有输出均含 `protocol_version=p7-reply-routing-1`、`model_calls=0`。model_calls只统计路由本身；new_task后续理解最多一次提取，另计。

#### A. clarify：续接原任务

假设当前revision=3，allowed_fields包含batch_id，该修订两个候选按顺序为批次A、B。输入“选择第二批”或“就第二个吧”：

```json
{
  "protocol_version": "p7-reply-routing-1",
  "kind": "clarify",
  "answers": {"batch_id": "<该修订第二个候选的真实ID>"},
  "revision": 3,
  "error_code": null,
  "clear_reference": false,
  "model_calls": 0
}
```

使用binding.task.task_id调用原 `POST /api/v1/agent/clarifications/{task_id}`，请求体只取 revision／answers，不把整个路由输出塞进接口。

其他同类输入输出：

| 当前允许字段 | 输入 | answers |
|---|---|---|
| quantity＋unit | 两盒 | quantity="2"，unit="盒" |
| quantity | 2 | quantity="2" |
| opened_at，且只有这一项日期待补 | 昨天 | opened_at="昨天" |
| unit | 毫升 | unit="ml" |
| to_location | 餐边柜 | to_location="餐边柜" |
| batch_id，且B已明确选中 | 这一批 | batch_id=B |

“2盒”在仅允许quantity时不会擅自覆盖已知单位；当前返回needs_input，前端使用数量表单补充。不能为了少问一次而修改不允许补充的字段。

#### B. new_task：新建任务

输入“把纸巾移到书房”：

```json
{
  "protocol_version": "p7-reply-routing-1",
  "kind": "new_task",
  "answers": {},
  "revision": null,
  "error_code": null,
  "clear_reference": true,
  "model_calls": 0
}
```

保留原文、使用新request_id，按原普通消息四字段提交。已有旧任务过期不阻止明确新任务。

输入“它在什么地方”同样是新的查询任务，但clear_reference=false；这表示保留可核实的当前对象，不表示已有可信引用。必须由后端检查后走独立引用适配器，不能发普通消息并偷偷补上猜测名称。没有有效引用时继续要求选择。

#### C. needs_input：继续询问

当前只有两个候选，输入“第三个”：

```json
{
  "protocol_version": "p7-reply-routing-1",
  "kind": "needs_input",
  "answers": {},
  "revision": null,
  "error_code": "INVALID_CANDIDATE",
  "clear_reference": false,
  "model_calls": 0
}
```

保留用户输入并展示有效候选，不创建新模型请求。其他原因包括：

| 原因 | 例子与页面处理 |
|---|---|
| AMBIGUOUS_SUPPLEMENT | 同时缺两个日期时输入“昨天”，要求选择具体字段 |
| INVALID_DATE | 非法日期／按家庭时区属于未来的开封日期，要求纠正 |
| REFERENCE_REQUIRED | “这一批”没有明确选择，展示批次选择 |
| CLARIFICATION_EXPIRED | 原任务过期，要求核对后重建；不延长旧上下文 |
| CLARIFICATION_CONFLICT | 任务与公开澄清修订不一致，GET最新任务 |
| INVALID_CLARIFICATION_FIELDS | 任务暴露了九字段以外的续接项，停止发送并核对契约 |
| INVALID_CLARIFICATION_INPUT | 空白、超长、注入、否定／不确定补充，要求明确输入 |

这些是本地路由原因，不保证现有后端会直接返回相同HTTP错误码；后端HTTP错误与AI结果原因分层处理。

#### D. clear_reference：清除活动引用

输入“开始新任务”：

```json
{
  "protocol_version": "p7-reply-routing-1",
  "kind": "clear_reference",
  "answers": {},
  "revision": null,
  "error_code": null,
  "clear_reference": true,
  "model_calls": 0
}
```

清除当前对象与活动续接绑定，提示输入新任务。不需要调用模型，不删除任务、取消草稿或撤销已执行操作。

### 3.3 修订与日期的额外要求

- 候选顺序必须与revision一起保存。库存变化后新列表可能只剩一个候选，原“第二个”此时必须失效。
- 公开answers仍限name、quantity、unit、location、purchased_at、label_expiry、opened_at、to_location、batch_id。不能增加action、discard_mode、家庭、expected_version或item_key。
- 日期字面量原样续接；辅助函数用可信家庭时区检查，最终转换由AI私有任务上下文负责。现有P1相对日期按context.created_at锚定，不能在手机上按设备日期预先替换；跨日／重试遵循同一任务依据，业务若要改变锚点需另行版本化契约。
- 草稿编辑不是澄清。修改动作或目标需新任务；已有值的编辑、修订与重新确认由业务执行层负责。
- 上述JSON为说明样例，尖括号内容不是可直接发送的批次ID。

## 4. 常见位置表达的调用预算

| 表达 | AI提取次数 | 条件与行为 |
|---|---:|---|
| 它在哪／它在哪里／它在什么地方 | 0 | 有有效引用则重新读取；无引用则补名称／选择 |
| 这批放在哪里／这一批放在哪儿 | 0 | 同上，不猜物品名称 |
| 这个放在哪／这件放在什么地方 | 0 | 同上 |
| 请告诉我它目前的存放位置等自由表述 | 最多1 | 可以走提取；不能承诺任意同义说法都零次或必然识别 |
| 候选、明确数量／日期的结构化澄清 | 0 | 原任务、允许字段及有效修订 |
| 明确新任务 | 最多1 | 路由0次，之后理解另计；不自动付费重试 |

零模型不等于零工具读取。每次涉及库存事实仍重新读取批次，不能展示旧聊天数量／位置作为当前事实。所有路径仍受输入检查、权限与10秒AI总截止约束。

## 5. 六类草稿的页面与确认分工

| 动作 | AI草稿／来源 | 前端处理 | 后端确认要求 |
|---|---|---|---|
| ADD | 名称、数量单位、明确位置，可有购买／到期日期 | 缺位置先补，展示尚未写入 | 稳定创建ID、字段校验与真实回执 |
| CONSUME | 目标批次、预期版本、库存单位下数量 | 展示消费量和预计剩余 | 重读版本、精确扣减、Consumed事件 |
| OPEN | 目标批次、预期版本、opened_at，无数量字段 | 只补开封日期，数量保持不变 | 补迁移／事务／事件；重复开封不重复变更 |
| MOVE | 目标批次、预期版本、to_location，无数量字段 | 展示原位置→目标位置，整批 | 只改位置，检查版本及正式结果 |
| DISCARD partial/all | partial来自明确数量；all来自当前库存，quantity_source=current_batch | 分模式显示原量、丢弃量、剩余及状态 | 补迁移／事务／Discarded事件；all也不能绕过版本检查 |
| PLAN_ADD | 手动quantity_source=user_input；计算建议为planning_calculation且有planning_basis | 明确加入待购，仍需确认 | 自动建议先重验依据；无能力保留草稿，不显示已采购 |

P7新增位置最多100字；采购数量最多三位小数且不超过999999999.999；库存数量仍最多六位小数。错误继续补充，不裁剪或自动舍入。源单位与输出库存单位可以不同，但换算必须可证明，原文及读取依据保留。

自动计算数量不符合采购精度／范围时，返回answered＋BUSINESS_PURCHASE_QUANTITY_INVALID，建议status=needs_review、suggested_quantity=null，无draft/preview/planning_basis。展示偏好／包装核对提示，不把回复文字变成手动采购提交。

preview是生成时预览。用户在业务表单编辑后，后端必须校验并提供与最终编辑值一致的核对信息；本次没有新增“编辑后AI已经重新计算”的接口，不能沿用旧预览伪装为新结果。

## 6. 统计、预测和建议的展示契约

前端必须保留完整结构化结果，至少读取：facts、consumption_summary、forecast、recommendations、planning_basis、quantity_source、sections、data_gaps、evaluated_at／snapshot_id，以及reply和error_code。

| 情况 | 必须显示 | 不得显示 |
|---|---|---|
| 缺历史／完整观察日／完整性来源 | 无法确认完整消费量，具体原因；若有有效小计需注明范围 | 把effective_quantity=0脱离status显示成实际消费0 |
| 可信完整窗口无登记事件 | 未登记到有效消费，不代表实际没有消耗 | 实际零消费、永远用不完 |
| 缺／陈旧／未来的库存核对记录 | 需核对，保留有效消费统计与已读取库存 | 精确耗尽日期、自动采购草稿 |
| 待购未读取完整 | PENDING_INCOMPLETE，需要后端补齐 | 未知待购=0，照旧生成补货数量 |
| 缺明确偏好 | EXPLICIT_PURCHASE_PREFERENCES_REQUIRED及设置入口 | 模型推测采购周期或最低库存 |
| 分区不可用 | sections中的状态和reason_codes，保留其他已核实部分 | 整页清空已有事实或伪造空库存 |
| 充分数据 | 观察窗口、计算依据、已确认待购抵扣、时间与条件 | 保证某天耗尽，或自动下单 |

reason_codes可能在消费摘要、forecast、recommendations、sections内；data_gaps不保证重复所有分区错误。reply已作文字降级，但前端自制卡片同样必须遵守结构化状态。

人工审核风险规则、真实完整消费记录、实物核对与待购版本由业务提供。离线夹具中的充分数据和合成审核规则不代表正式家庭已经具备这些资料。

## 7. 后端仍需完成的内容

1. 解决当前连接／构建对应环境的问题；本阶段没有改Debug、Release、SSH或服务器环境。
2. 完成既有reference-messages受信适配层，不把手机传入的历史事实直接转成ObjectReference。引用最长15分钟，恢复不续期，跨家庭清绑定。
3. 继续保留数据库任务网关及普通消息四字段、澄清九字段协议，保存AI完整私有上下文和最新修订。
4. OPEN／DISCARD补数据库动作、事件及数量约束迁移，再接事务和回执。AI本地草稿通过不等于正式库能写入。
5. 实现已有规划读取契约及真实事实来源，完整性无法证明时明确不足，不造覆盖日、核对时间或事件。
6. 自动PLAN_ADD确认时加载服务器保存的planning_basis，重新检查库存、清单、偏好和事件水位。字段／数量修改按业务修订处理。
7. 正式业务回执才建立已执行状态。AI仍不写库存／采购；提交超时复用原operation_id和原体恢复，刷新失败保留成功。

## 8. 联合验收及交付状态

前后端至少补验：移动→选择第二批→草稿→确认→回执→刷新；期间库存改变则重选。再覆盖缺日期补“昨天”、重复无效字段、无引用问“它在什么地方”、引用过期／删除／终态、换家庭／换话题、关闭窗口与提交响应丢失。

记录四个独立维度：

| 维度 | 本阶段状态 |
|---|---|
| AI本地实现 | 完成五项，79项新增实例；AI全量764通过／1跳过 |
| 前端已承接 | 本阶段未修改，待队友接入 |
| 后端已部署可执行 | 本阶段未修改／部署，待队友确认 |
| 真实模型、PostgreSQL并发、最终APK联合验收 | 本阶段未执行 |

后端现有本地兼容测试93通过／5项PostgreSQL专用场景跳过；P7规则样本90开发／60保留全检查通过，均不能替代上述联合验收。AI HTTP版本仍0.7.0；新增的是调用方续接输出协议版本，不是新HTTP路由。

旧 `V1-P7/reply-resolution.schema.json` 等文件保留为历史交付。本补丁的调用方类型以代码模型及本交接为准，可从ReplyResolution.model_json_schema()／BoundTask.model_json_schema()生成当前schema到新版本目录，不覆盖旧归档。

本次只在本地交付三个AI运行文件、一个离线测试文件和本阶段两份Markdown。未来源码同步与正式发布另行安排；本次不上传服务器、不提交／推送Git。
