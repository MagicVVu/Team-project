# P5 已实现的 AI 输入与任务适配契约

日期：2026-10-16，AI输入配置版本0.5.0。按用户明确要求，**服务器现有数据库网关保持不变**，继续作为正式业务入口；本轮没有修改、复制或部署任何后端代码。前端仍需由维护者接入。

## 服务与兼容性

入口为 `interaction.app:create_app`，通过P3工厂的可选profile装配输入适配器；库存工具、鉴权、规则、统计和草稿逻辑继续复用P0–P3。默认 `p3.app:create_app` 的OpenAPI与原导出完全一致，旧P0/P1/P2入口不变。运行引擎沿用P3_ENGINE=rules/deepseek，P5真实模型使用独立的p5-extract-1提示，未更改旧P3提示。

AI内部POST /agent/message、POST /agent/clarification，以及P3结构化查询/风险接口沿用；没有音频上传或自建ASR接口。服务鉴权仍是AI_SERVICE_TOKEN与后端提供的X-User-Id/X-Household-Id，不能发给手机。

机器契约：[AI OpenAPI](ai-openapi.json)、[确认文字](reviewed-message.schema.json)、[续接封套](continuation.schema.json)、[公开任务](public-task.schema.json)、[公开草稿](public-draft.schema.json)、[调用方输入会话](input-session.schema.json)。最后一种是本地调用方受保护状态，不是发送AI或正式网关的请求体。

## 最终确认文字

Message在原P3字段外可选接受input：source=text/voice/manual_fallback、input_session_id、transcript_revision、user_confirmed、user_edited。这是受认证调用方的来源声明，不是AI核验过用户点击或设备录音的证明。

- input不存在：兼容现有网关，只作为普通文字，review_attestation_received=false，不伪称已经验证语音核对。
- input存在但user_confirmed=false：返回INPUT_NOT_REVIEWED，无模型、工具或写入调用。
- 不接受原始转写、音频、ASR置信度等额外字段。删除的“99盒”不能为修改后的“2盒”提供依据。
- 仅移除句首带分隔符的“嗯/呃/额/啊”做提取和旧字段校验；原始最终文字仍保留在original_text及输入记录。不会移除否定、内部逗号、日期或口误修正语句。

input_receipt保存最终文字SHA256、绑定作用域/文字/时区/提醒参数/来源的指纹、来源声明和deduplication_owner=business_backend。不保存原音频或原始ASR文本。此指纹供调用方核对，不是签名，也不替代后端最新revision与任务归属管理。

## 口语边界与澄清

否定、自我修正、数量不确定、假设及引用他人指令先返回needs_clarification，无模型/工具调用。保守规则可能要求用户把含糊表达重新说清，不能推断真实音频中本来想说的数量。

这类结果有input_review.resubmit_required=true、replacement_request_id_required=true，以及p5-text-review-1私有上下文；allowed_fields=[]。用户编辑最终文字后创建**新消息和新request_id**，不在旧任务中改写动作。AI澄清接口也拒绝用该上下文修改正文。单独“取消/算了/不用了”只说明本条未创建新草稿，不声称已取消已有后端任务或撤销已确认库存。

业务补字段/选批次继续原P1/P2/P3协议，结果中的私有上下文用p5-continuation-1封套携带输入记录和原delegate。外层作用域、revision、有效期等与delegate一致，恢复后只补缺失字段、重新读取事实，无第二次模型提取。旧上下文也能直接续接。原始完整上下文仍只能由后端保存，公开响应只保留revision/allowed_fields/expires_at。

P5没有新增任务数据库。AI不能独立确认调用方是否传回最新上下文，不能独立去重重复HTTP消息；这些职责继续由现有数据库网关承担。

## 与不改动的数据库网关对接

正式消息body保持现有4字段：household_id、text、request_id、household_timezone。`session.public_message`明确只构造这4个字段，不发送手机items/inventory_revision或input来源声明。用户身份来自现有业务访问令牌。

语音元数据与原始识别文字先保存在调用端；当前网关不转发它们，AI将按普通确认文字处理。仅这一能力就能复用P5语义防护，不要求改NewMessage或网关存储字段。

`interaction.tasks.TaskClient`实现既有路径：POST消息、GET任务、POST任务澄清、GET草稿。不实现代理服务、库存副本、确认/撤销事务或购物写入。客户端校验完整候选事实、动作草稿和脱敏澄清信息，拒绝旧快照网关响应、私有上下文泄露或其他家庭结果。

当前v0.6白名单仅有name/quantity/unit/location/purchased_at/label_expiry/opened_at/to_location/batch_id。TaskClient在网络请求前拒绝空answers或item_key，返回TASK_CAPABILITY_UNAVAILABLE；不要求修改现有网关。P3内部支持这些恢复协议，不代表公开入口已开放；相关功能保持条件可用状态，不自动降级到猜选批次或伪造历史。

TaskClient的确认文字重放必须复用调用方会话中已有body/request_id；一次传输只尝试一次。超时返回TASK_OUTCOME_UNKNOWN：有task_id时GET原任务，无task_id时只提供用户明确触发的同键恢复方案，不自动重发POST。401/403、404、409、422均有单独且不泄露上游细节的错误码。现有error任务不支持澄清恢复时，读取结果后手动核对或明确新建请求，不修改网关实现。

P3 planning_basis等信息保留在完整任务结果中；现有GET草稿没有该独立字段，客户端不能声称它已进入新确认事务。当前确认写入未验收，所有AI结果仍为“尚未写入”。

## 调用端会话状态参考

`interaction.session`是无数据库的纯函数状态参考，可供受信业务调用方使用；Android需要由前端维护者实现等价生命周期逻辑，它不会自动改变现有App。

状态：idle → recognizing → editing → reviewed → submitted，另有cancelled。每次识别有recognition_id，重录使旧ID失效；迟到/重复结果不覆盖新文字。编辑会清除识别句柄并提高transcript_revision；未核对、空结果或取消不能提交。识别失败可进入manual_fallback，保留可编辑文字。

提交生成一次request_id并保存完整确认消息；重复点击或序列化恢复返回同一消息，变化正文、家庭、时区或已提交字段会拒绝重放。修改已提交文字须新建会话，旧草稿由界面停止继续使用。取消本地输入会话不等于取消后端已有任务。

每次AI初始处理/澄清保持覆盖模型及工具的10秒预算；任务客户端默认15秒总等待，无自动重试。ASR耗时独立记录。会话和HTTP单元测试不证明真机生命周期或数据库供应商调用计数已验收。
