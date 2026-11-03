# 真实数据回测状态与记录模板

当前状态：未验证。真实耗尽区间 0；MAE、绝对误差中位数、覆盖率和拒绝率均不报告数值。算法测试和真实模型意图评测使用合成库存/事件，不能作为真实预测有效性证据。

已提供本地 eval/p3/backtest.py。输入为 Interval JSON 数组：id、source=real/synthetic、human_reviewed、item_key、household_timezone、captured_at、snapshot、outcome_known_at、exhausted_on、outcome_verified、followup_complete、followup_events。snapshot 使用规划上下文规范，captured_at 必须等于 snapshot.as_of；事件 recorded_at 不能晚于该截点。

必须保存当时的库存、偏好、覆盖、事件和水位，不能用现在的库存回推过去，也不能利用后来的完整性标记填补当时未知事实。后来的实际耗尽日和干预事件仅用于结果评估，不能进入预测输入。跨页遗漏、随访缺失或标签未经核验的区间不能计入有效样本。

新增/采购入库、丢弃、库存调整以及撤销/更正会改变过程或标签，本工具在捕获后到核验耗尽前发现这些事件时删失。Finished 状态不是额外消费。真实人工核验且未受干预的估计区间少于30时，不输出聚合误差指标；合成来源不进入真实指标。

在本地 agent 目录运行：

```text
python -m eval.p3.backtest --input <经审核的区间文件> --output <本地回测报告>
```

待真实数据具备后填写：

| 项目 | 当前记录 / 待补充 |
|---|---|
| 采集区间与家庭时区 | 待真实数据 |
| 规范商品数量 / 区间数量 | 0 / 0 |
| 人工复核人员与方式 | 待指定，不能填 AI 为人工审核 |
| 已知记录缺失与断货 | 待业务确认 |
| 干预及删失数量 | 待随访 |
| 有资格预测 / 总可核验区间 | 待积累 |
| MAE / MdAE / 覆盖率 / 拒绝率 | 未验证 |
| 与简单基线对比 | 尚未实现真实比较 |
| 误差验收门槛 | 待真实基线后冻结 |
| 效果验收结论 | 不具备验收条件 |

metrics_available 仅表示数据数量允许计算，real_effect_verified 保持 false；上线结论须在审核、基线比较和误差门槛完成后另行作出。
