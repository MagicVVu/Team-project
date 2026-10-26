# V1-P9 AI 开发交接

后端P9已于后续授权发布中部署生产，0011迁移和16项只读预检通过，详见[生产发布记录](backend-ai-p9-production-release.md)。无AI源码修改；AI新增适配仍未联合发布。原开发阶段双库/HTTP测试和下述AI交接边界继续有效。

## 后端已完成

- 在现有内部规划接口提供显式Product UUID与批次UUID；facts接口provenance.product_identity、内部库存batch.product_id复用相同身份。
- 商品创建与批次关联需要认证成员逐项确认来源，不按同名归组。household_attested只说明家庭确认，不代表平台规则审核。历史数据保持null。
- 采购PATCH来源省略/UUID/null三义；来源变更带operation_id+expected_version；跨家庭拒绝、已购保护、冲突和永久回执。
- 商品聚合放provenance.product_aggregates_v1；盒/瓶不可推换算，汇总不完整时null，批次仍保留。过期批次不计入未过期ACTIVE数量，可用量仍未知。
- 原BusinessEvent扩展普通写入、采购、盘点和更正。AI继续从同一内部规划一致快照读取，不要用分页展示接口拼凑一致快照。
- 新重验basis与只读诊断；确认入口对新basis过期请求明确拒绝，不静默按旧数据提交。

## AI 侧待实施

1. Reader保留并解析规划provenance扩展；旧data不改。商品级视图使用product_id映射，item_key建议使用`product:<uuid>`作为AI内部商品键，执行时仍要求明确batch_id及expected_version。
2. 不兼容单位、未知期限、用户来源标签、过期/终态批次和缺盘点必须保留缺口；不要把total_quantity或nonexpired_active_quantity当成已审定usable_quantity。
3. pending_complete=false时不能把pending=[]解释为零待购。展示pending_state及pending_count，并要求修正来源；采购重叠检查不能按同名推断。
4. 按inventory-ledger-1区分Consumed、Adjusted、Counted、Purchased、Archived和Corrected。只有Consumed为消费；当前库存更正投影Adjusted并可能使原日期覆盖证明失效。禁止把库存更正的related_event_id当作旧AI Corrected“替换消费总量”的指令。
5. 适配新的planning_basis字段（详见contract）。当前严格AI响应模型还未接受该basis；由AI服务从可信后端快照复制并返回，不能让普通客户端指定。原建议、版本、procurement_source和人工改动必须可追踪。
6. 支持stale/blocked重验结果及PLANNING_BASIS_STALE，重新读取并生成建议。不要重用旧basis或把diagnostic通过作为未来写许可。
7. 采购执行反馈待扩展：原库存after-commit schema要求batch_versions，PLAN_ADD无库存变更，因此当前接口not_applicable。双方需定义采购回执读取与只读反馈的适配方式，不伪造库存版本。

## 需要人工审核

AI规则负责人负责核实source_refs、适用商品/规格/类别/批次、审核人、版本、有效时间及发布/撤销。零active_human_rule_count保持未知/待审核。普通家庭资料接口不能审核规则，不能用补齐用户标签代替规则发布。后端尚未接受任何“平台approved”规则同步；须先约定受认证的注册表协议、权限与撤销行为。

## 需要双方联合验收

| 场景 | 必须验证 |
| --- | --- |
| 商品A两个批次 | 合法单位聚合，批次位置/期限/版本完整 |
| 同名不同商品 | 分开product_id，不跨商品引用规则或数量 |
| 不兼容单位 | 汇总null且保留两批，不猜包装换算 |
| 采购来源未知 | 不当零待购，修改/清空重试不覆盖新关联 |
| 标签/用户风险资料 | 来源明确，未知规则不解释为安全 |
| 真实消费与盘点 | 盘点/编辑/更正不产生消费记录；引用的旧日期覆盖失效 |
| 自动建议期间库存/消费/偏好/规则/待购变化 | 版本失效拒绝并重新生成 |
| 人工改量/换单位/重复点击/两机确认 | 保护字段、合法单位、一次业务效果 |
| 业务已提交但反馈失败 | 查原receipt恢复，不能再次扣量/建采购 |
| 会话重开/超时/原请求恢复 | 用户与家庭隔离、幂等回执及任务版本保持 |

## 需要生产授权

完整生产备份恢复演练、受控0011迁移和后端镜像部署已经用户授权并完成。专用生产测试家庭和最少真实DeepSeek调用仍待单独明确授权；当前只做生产只读验收，不把它解释为业务写入链路已验收。

自动提交始终false，manual_plan_only始终true。联合契约、安全验收和明确版本批准之后，才可另行完成事务内的重读/重算/提交/结果保存并讨论开关；不得只因本地测试通过就开启。
