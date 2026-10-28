# P7 AI 接口与有限上下文契约

## 身份与兼容

内部接口保持 Bearer AI_SERVICE_TOKEN 和可信 X-User-Id / X-Household-Id。仅业务服务可调用，手机不得持有服务/工具令牌或 DeepSeek 密钥。

公开数据库网关保持原四字段消息、原九字段澄清和 GET 任务/草稿。公开字段不增加 reference，私有续接上下文仍由业务方保存。现有网关不会自动转发本次引用扩展，需要独立受信适配层；本轮只交付其契约，不修改网关源码。

## 内部 POST /agent/message

原 text/request_id/household_timezone 等兼容字段保留，可选 reference：

| 字段 | 含义 |
|---|---|
| protocol_version | 固定 p7-object-reference-1 |
| scope | 当前真实 user_id、household_id，须与认证头一致 |
| source_task_id/source_revision | 业务方已核实归属和最新修订的来源任务 |
| batch_id | 来源结果中唯一对象或用户明确选中的真实批次 ID |
| issued_at/expires_at | 业务服务器签发时间及有效期，最长 900 秒，带时区 |

引用没有数量、位置、名称或库存版本字段。AI 不自行查询任务库以证明 source_task_id；来源验证是受信调用方责任。伪造一个签名样式字段或手机 JSON 不能代替权限核实。

业务方应把 request_id 与原文、引用绑定，重放时不得替换引用；引用过期须重新选择并创建新请求。沿用旧网关四字段指纹不能独自证明引用未变，此绑定属于未来独立适配层，不是本轮已交付的数据库功能。

只有字面指代请求才使用引用。明确新名称走原流程，不应用旧引用。每次读取当前批次并校验家庭/返回 ID；终态、零库存和不可访问批次要求重新选择。原文字段先经过原证据校验，再仅从工具绑定名称；不偷偷拼接商品名作为用户证据。

“它在哪里/它还有多少”等明确字面查询零模型调用。其他动作沿用最多一次模型提取；名称之外的数量、日期和位置不能从引用补出。风险/统计/预测等复杂跨问句目前要求明确名称，随后复用已有 P6 流程，不猜商品映射。

## POST /agent/clarification

公开仍为原任务 ID、revision 和非空 answers；只允许 name、quantity、unit、location、purchased_at、label_expiry、opened_at、to_location、batch_id。

引用绑定任务的新私有封套为 p7-reference-continuation-1：保留原文、作用域、修订、有效期、输入证明和 P1 委托上下文。封套与委托字段必须一致，候选及目标只能是该引用批次。续接不调用模型；原任务/引用过期、修订冲突、越权字段或候选无效均不能生成执行结果。

重读发现变化时返回当前候选和 VERSION_CONFLICT，要求再次选择；不得把旧草稿版本替换成新版本后自动确认。

## 纯调用方参考

conversation.replies.BoundTask / resolve_reply / reference_from_task 不提供新 HTTP 服务或任务数据库。

- 业务方按真实用户权限加载任务，构造作用域绑定；前端或业务适配层持有当前候选修订。
- resolve_reply 返回 clarify/new_task/needs_input/clear_reference，以及允许的非空答案和修订；不持久化、不调用模型、不自动发送请求。
- 序号按当次候选顺序，超界或重复 ID 不选择；“这一批”必须已有明确选择。
- 日期只填当前唯一允许的日期字段，保留“昨天”交给原任务的可信创建时间和家庭时区转换；多日期歧义要求字段选择。
- reference_from_task 仅在新鲜结果唯一或用户明确选择后使用；不得在重新打开窗口时从缓存历史重新签发以延长引用。
- 返回 clear_reference 或换家庭/退出账号时清空引用和当前任务绑定；历史文字可以展示，不能充当最新事实。

## 返回字段

继承 P6 的 draft/preview/candidates/facts、风险/规划依据、缺项和 trace。新增 object_source（user_input/trusted_reference）、reference_used（来源任务/修订/批次）和 clear_reference。

AI 仍只返回五种结果状态，inventory_writes/shopping_writes 恒为 false。runtime.release 为 V1-P7；P7 任务客户端也能读取旧 P6 任务。健康信息明确 execution_capabilities_owner=business_backend，不能据此启用确认按钮。

草稿按 action 展示：ADD/CONSUME/PLAN_ADD 的数量单位；OPEN 的开封日期；MOVE 的目标位置；DISCARD 的模式和数量。全部丢弃量来自当前批次，不能混入消费。ADD 的 AI 草稿允许位置待补，但正式新增接口要求非空位置，确认表单必须补齐。

初次和澄清各为覆盖模型及工具的 10 秒总截止。失败保留原文和已解析/已补字段；跨作用域错误移除旧原文、候选和引用诊断。没有自动付费重试。

机器规范见 ai-openapi.json、object-reference.schema.json、reference-continuation.schema.json、public-task.schema.json 和 reply-resolution.schema.json。
