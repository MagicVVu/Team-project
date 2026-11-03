# V1-P2 规则来源与审核状态

2026-10-14 核对来源。生产配置为 `agent/p2/rules.json`，共 5 条基础规则；没有填入任何虚构商品的开封保存天数。字段 reviewed=true 在本版本仅表示已完成所标明的来源或实现核对，review_kind=source_check，**不是人工专业审核**。所有默认结果 source_human_reviewed=false。

## 官方来源

- [GOV.UK Best before and use-by dates](https://www.gov.uk/understanding-food-labelling/best-before-and-use-by-dates)：区分安全日期和品质日期，强调保存与处理条件会影响原标签的适用性。用于食品标签和保存条件的核对原则；不把文中的示例温度或天数扩展为所有食品规则。
- [FDA Don't Be Tempted to Use Expired Medicines](https://www.fda.gov/drugs/special-features/dont-be-tempted-use-expired-medicines)：药品有效期与包装保存要求需要遵循；用于药品标签和保存条件核对，不推断延长日期、用药剂量或替代医疗决定。

这两项是标签语义和保守处理的来源，并非对具体中国商品标签的法律解释。后端必须明确登记日期含义与标签适用条件，不能从中文名称或“保质期”一词自动套用国外标签类型。

## 项目策略

app-label-reminder 使用用户提供的提前提醒天数，默认 3 天，来源类型 project_policy。此值复用现有前端提醒偏好，是显示窗口，不是健康安全阈值；它不改变任何标签日期或包装规则。

green 表示“已知规则未触发”，unknown 表示“待核对”。缺类别、日期类型、保存条件、开封状态或适用规则时不显示绿色。确切的高优先级依据可同时保留缺失字段，避免把已知关注隐藏为普通无数据状态。

## 商品专属开封规则

Rule 模型支持 after_open，但要求具体 product_ids、manufacturer_label 来源、已开封条件和明确 max_days_after_open，并可约束 storage_condition。需要团队从真实包装或制造商资料提取、复核并记录人员和日期后配置；未审核或禁用规则不会参与计算。

专项测试中的合成包装地址 `example.invalid` 仅证明规则选择、日期边界、冲突和标签优先级代码行为，既不在生产 rules.json 中，也不代表真实牛奶或药品的保存建议。规则引用不接受客户端上传，不作为可执行表达式。

## 后续审核

Garin-cyber 协助复核样本；规则的商品适用性、完整保存条件及安全含义仍需人工专业核验。来源网页更新或包装变化时，应增加版本、保留旧证据并重新验证，不以模型生成文本覆盖用户标签事实。
