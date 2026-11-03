# P3 后端协作契约

日期：2026-10-15。AI 侧实现版本 0.4.0；以下规划数据接口属于 AI 已实现的**提议契约**，尚未与后端共同验收。通过 SSH 实时读取正式 OpenAPI：后端仍为 0.6.0，未出现 planning/consumption/forecast 路径。本轮没有修改后端源码、数据库或运行容器。

## 1. 后端需要提供的只读数据

新增 `GET /internal/v1/planning/context`。认证复用 `BACKEND_TOOL_TOKEN`、`X-User-Id`、`X-Household-Id`；后端校验活跃用户及家庭成员身份。身份不能来自用户问题或答案。查询参数为可选 name 或 item_key，不能同时使用；不传表示该家庭商品列表，指定 name 时应返回全部匹配的稳定商品，而不是第一批。

成功返回 `{"success":true,"data":<PlanningSnapshot>}`。data 的完整机器规范见 [planning-context.schema.json](planning-context.schema.json)。这是拟新增契约，不代表 v0.6 已有该接口。

| 字段 | 后端职责 |
|---|---|
| protocol_version | 固定 p3-planning-context-1 |
| scope | 受认证调用确定的 user_id / household_id，两者均须匹配 |
| snapshot_id | 代表同一原子业务状态的稳定令牌；相关库存、清单、事件、覆盖或偏好改变必须变化，不能每次读取随机生成 |
| as_of | 带时区的可信读取时间；AI 拒绝超过 5 分钟的旧快照或超前超过 1 秒的时间 |
| event_watermark / shopping_version | 事件读取水位及共享清单版本，供确认时复核 |
| items_complete / history_complete / pending_complete | 三种独立传输完整性；不知道须为 false，不能把读取失败当成零 |
| next_cursor | 第一版仅接受完整单快照。非空直接降级，不消费首屏后宣称读取完毕 |
| items | 稳定 item_key、规范名称、统计单位、商品版本、类别、批次、事件、逐日覆盖、明确偏好和可用量核验状态 |
| pending | 当前家庭共享清单中，能明确对应商品的条目；不可混入其他用户私有草稿 |

快照须一次事务/一致性读取完成。name/item_key 过滤时 pending 也应限定到返回的商品，避免丢失商品对应。无权限返回 403/404，未认证 401，数据不兼容或超限 409；不得返回 HTTP 200 的伪成功空数据。AI 仅调用 GET，不直接连接数据库。

首版上限：1000 商品，每商品 1000 批次/20000 事件/3660 覆盖日，共享清单 10000 条。超限需后端返回错误或不完整标记，禁止截断。后续若新增分页，需要共同定义同快照游标读取后再升级 AI；当前 AI 不承诺处理游标续页。

## 2. 商品、事件、覆盖口径

item_key 必须在家庭内稳定，跨多个库存批次指向同一规范商品。名称相同但 SKU/规格不同应返回不同 key，让用户选择。不能用 Android history 文本或批次名称拼出历史。

单位沿用 ml/L、g/kg 和登记的盒/瓶/包等；仅同单位或质量、体积单位可以转换。Decimal 以字符串传输。偏好 minimum_stock、pack_size 使用该商品统计单位；pack_size 表示一个 order_unit 含多少统计单位，必须与 order_unit 同时登记。minimum_stock 是商品级偏好，不是各批最低量相加。

事件字段：id、item_key、kind、quantity、unit、occurred_at、recorded_at、committed、related_event_id。kind 使用规范值 Consumed/Discarded/Added/Opened/Moved/Finished/Purchased/Draft/Reversed/Corrected/Adjusted，需后端显式映射数据库枚举。

- 只有 committed=true 的 Consumed 正数量计为消费；Consumed+Finished 不重复计数。丢弃、购入、移动、开封、草稿均排除。
- 相同 ID 相同内容去重；同 ID 内容冲突要求核对。初始消费不得附带关系 ID。
- Reversed 只关联原 Consumed：quantity=0 表示抵销当前剩余有效消费；正数量表示部分抵销，不能超过当前有效量。
- Corrected 只关联原 Consumed：quantity 是更正后的**总有效消费量**，不是增减差。0 表示归零。多次更正/撤销按 recorded_at 处理；目标记录时间须严格早于关联事件。暂不接受“撤销另一个撤销”的链，后端应先规范化为对原消费的明确操作。
- 关联目标即使发生在统计窗口之前也须随快照提供，不能只裁剪窗口内事件导致关系悬空。不能确定关联时 AI 返回 needs_review。
- occurred_at 表示实际发生时间，recorded_at 表示系统知晓时间。晚于快照 recorded_at 的事件不参与计算。更正后的量归属于原消费发生日。

coverage 是逐个家庭自然日的 records_complete、stockout、unexplained_adjustment。recording_completeness_source 是业务确认完整性的来源说明，不能由模型或聊天内容推断。transport complete 不等于用户把全部消费都记录了。当天未完结部分不进入速率分母；缺失日及断货不能当作零需求。AI 只使用最近连续有效窗口，最多 28 个完整日；较早缺口不会污染足够长的近期有效窗口。

usable_quantity_verified 由业务核验提供。AI 不自动扣除有风险的库存。该字段不为 true，或 P2 对活动批次给出 red/orange/unknown 时，采购建议需要复核；药品补货始终排除。

## 3. 网关、任务和澄清

P3 继续使用原有 POST /agent/message 的 text/request_id/household_timezone/reminder_days；统计窗口和是否草稿从原文一次提取，本轮没有新增必须透传的消息选项。AI 保留五种 AgentResult 状态。新结果字段见 [页面与字段说明](fields-and-states.md)。直接的三个结构化只读 AI 接口需要后端按需代理，不能把 AI 服务令牌发给客户端；对这些新增代理路由应另设请求校验和幂等规则。

新增 clarification.protocol_version=p3-item-selection-1，答案白名单在不同上下文为 name 或 item_key。**不可冒用 batch_id**。后端当前 ContinueMessage 白名单缺 item_key，应仅对已保存的 P3 商品选择上下文开放，并与 allowed_fields 取交集。动作、scope、版本、水位、偏好等一概不能从答案修改。

续接重读快照；令牌或候选商品/批次版本事实变化时返回修订号增加的选择上下文，要求再次核对，不自动选择。后端负责原子维护最新 revision、上下文归属、15 分钟 TTL、幂等与并发租约。AI 无任务数据库，不能独立识别调用方重放的旧上下文。

读取失败保留原文和已解析字段。error + clarification 的任务需要后端允许恢复（v0.6 仅 needs_clarification 可续接，需调整）。若没有缺失字段，allowed_fields=[]，允许**空 answers** 重新读取事实，不能修改已经填写的名称；已选 item_key 也保存在受保护上下文。恢复不调用模型，不能自动发起付费重试。正式公开返回继续脱敏 clarification，仅暴露 revision/allowed_fields/expires_at，不透出整个内部上下文。

## 4. 保存和确认采购草稿

旧 PlanCommand 仍只有 action/name/quantity/unit。新增独立 planning_basis，不能随意塞进旧严格 Command：

| 依据 | 用途 |
|---|---|
| item_key / item_version / batch_versions | 校验商品及库存事实 |
| shopping_version / event_watermark / snapshot_id | 校验未购量、历史和一致性状态 |
| preference_version / policy_version / as_of | 追溯生成时偏好、策略、时间 |
| calculation / original_suggested_quantity | 保存源、目标、库存、已有待购和原建议量 |
| human_modified=false / confirmation_revalidation_required=true | 初始草稿标记；后端需在用户编辑后记录人工修订 |

v0.6 的 result JSON 能容纳新字段，ai_drafts 的 command_json/preview_json 并不能自动保证 planning_basis 持久化。后端需定义独立 JSON 字段或不可变 task-result 引用，并在草稿确认事务中强制取回依据。

正式确认时：重新鉴权 → 校验任务、商品和各版本 → 重读共享未购量并重算/核对 → 用户修改量标明人工修订 → 同一事务、同一幂等键加入清单。已有计划覆盖时不得重复添加。库存/清单变化返回冲突重新确认。AI 本轮没有调用确认写入，也没有实现业务确认接口。

## 5. 接入次序与验收

1. 先验收商品标识、消费与撤销事务、规范事件及覆盖来源；实现单快照只读工具。
2. 在隔离测试家庭配置少量已知真实事件、最低量、共享待购及风险必填字段；验证统计与真实账本逐条相符。
3. 支持 P3 协议的网关选择和 error 恢复，保存 planning_basis；复核跨家庭、旧 revision 和幂等冲突。
4. 用本地 compose.p3.override.yaml 合并正式隔离配置，经后端负责人部署；当前 AI 账号没有 Docker/部署目录权限，本轮未切换容器。
5. 验证文字→只读工具→候选→续接→单项草稿→后端确认闭环及数据库写审计。未取得测试身份/事件前，正向链路待验收。
6. 积累至少 30 个经人工核验的未受干预真实区间，运行回测，并与简单基线比较。合成算法和模型意图通过不能替代真实预测效果验收。
