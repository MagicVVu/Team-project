"""Small handoff, complete raw evidence stays in the testing round."""
import json,shutil
from datetime import datetime
from prepare import ROUND,REPO,sha,write
d=json.loads((ROUND/'reports/analysis.json').read_text(encoding='utf-8'))
t=json.loads((ROUND/'reports/diagnostics.json').read_text(encoding='utf-8'))
assert d['formal_questions']==1152 and not d['unexecuted'] and not d['unpaired_executions']
main=d['summaries']['主功能集'];a=main['off'];b=main['assist']
text=f'''# Jev开关对照测试交接

本轮测试已完成：固定提交c2d5ea6，P8.7入口，中文，Jev1.13.0。原功能集256题次与独立32条Jev专项，关闭、开启各两遍，共1152有效题次，576组配对，没有缺测。另有18题次小批量检查，成绩单列。

## 建议

当前建议保持默认关闭，先优化接入后复测。本轮没有证明Jev带来综合收益：主功能自动匹配率小幅提高1.17个百分点，但差异的场景分组95%描述区间为负2.10至正4.34个百分点，包含没有提升；平均整题耗时约增加87.2%，总API约增加86.8%。结论只针对当前接法和这套用例，不是对Jev模型整体能力的定论。

## 主要数据

| 主功能集 | Jev关闭 | Jev开启 |
|---|---:|---:|
| 有效题次 | 512 | 512 |
| 自动PASS | 400 | 406 |
| 自动FAIL | 112 | 106 |
| 自动匹配率 | 78.13% | 79.30% |
| 平均每题秒 | {a['question_seconds']['mean']:.3f} | {b['question_seconds']['mean']:.3f} |
| P95秒 | {a['question_seconds']['p95']:.3f} | {b['question_seconds']['p95']:.3f} |
| 平均每题API | {a['mean_calls']:.3f} | {b['mean_calls']:.3f} |
| DeepSeek请求 | 554 | 575 |
| Jev请求 | 0 | 460 |
| 四轮任务全通过 | 16/64 | 23/64 |
| 每题保守折算元 | {a['mean_conservative_cny_per_question']:.6f} | {b['mean_conservative_cny_per_question']:.6f} |
| 每API保守折算元 | {a['mean_conservative_cny_per_api']:.6f} | {b['mean_conservative_cny_per_api']:.6f} |

Jev专项两遍：关闭60/64，开启62/64；平均每题1.480秒、2.549秒。专项单列，未混入主功能率。

正式共1812次实际HTTP，包含原额度阻断题的一次Jev请求。正式有效配对排除该次未完成尝试，但首次输出及费用保留。包括检查共1846次真实HTTP。本轮保守占用10.377690208元，不是平台实扣；80次正式Jev请求用量未知，检查另有3次未知，均未记零。原币估算及已知请求均价见Excel“调用与费用”。

## AI负责人优先复核

1. **快捷路径没有生效。** 主功能460次Jev调用最终458次回退、2次保护；专项58次调用最终56次回退、2次保护，快捷读取均为0。主功能回退352次是已有引用/任务等上下文，31次是门槛未过，75次超时。无需模型即可识别的前提是否还应先调用Jev，需要优化策略后另测。
2. **简单查询也被门槛挡回。** JEV-01“牛奶还有多少”第一遍意图识别正确，但澄清门置信度0.4、选中概率0.6，低于源码0.8/0.9。先分析门槛和问题定义，不在验收过程中改阈值来追求通过。
3. **稳定的结束状态退步。** `vt-P8.6-m2-t1`“一起核对这件牛奶数量和位置”：关闭两遍PASS，开启两遍FAIL。两遍都已读对数量1盒、位置冰箱，但以no_progress或repeated_plan停止，没有按预期completed收口。这是流程/状态问题线索，不能说库存数字算错。
4. **计划语气的契约争议。** `vt-P8.1-s3`期望采购草稿，Jev按非肯定变更保护而澄清；本轮保留FAIL，需团队确认“计划买2盒”应进入哪个状态。安全保护本身不能直接当成理解错误。
5. **共同失败与模型波动。** 主功能41题次改善、35题次退步、71题次双方都失败。288个输入中78个出现遍间波动；稳定改善3个，稳定退步1个。移动目标字段错放到location、new_task与ADD混杂等线索见问题CSV。分类是定位建议，尚待人工核实。

最慢关闭题 `vt-P1-s5` 第一遍4.174秒，DeepSeek三次循环，HTTP合计3.687秒；最慢开启题 `vt-P8.3-s2` 第二遍6.344秒，Jev回退再加DeepSeek三次循环，HTTP合计5.641秒。Top5、IQR门槛和原始证据均保留，不删除极端值；不能由客户端日志断言网络或供应商排队各占多少。

## 测试与费用说明

- 原生AI离线1277通过、2跳过，Garin适配器13通过。两个跳过分别为本账号不能创建符号链接、原生付费烟测未启用；真实Jev由本轮独立付费链路覆盖。模拟预检576题次不算模型成绩。
- 每组初始数据和时钟一致，交错开关顺序，第二遍反转；多轮各自继承实际回复。仅允许两家模型外网，未接正式后端、数据库或MuMu。
- 初始10元和原DeepSeek累计20元保护先触发，原998题次保留。11月4日用户明确要求完成实验、不以费用限制；另批续跑155题次，只补缺测和1次预算阻断，没有重试任何已完成PASS/FAIL，账本未清零。
- 人工标注和规则签字仍待确认。全部FAIL保留，状态契约和样本争议单列，不改正确预期。
- Jev原币USD、DeepSeek原币CNY；8元每美元只是保守折算参数，未知费用仍未知，未核对平台账单。

## 文件

- Excel：逐题并排、每题均值、两家API均时均价、功能分组、失败与极端值。
- Word：独立四页工作记录，可直接给团队。
- 完整证据：`tests/jev模型测试/Jev开关对照_20261103_c2d5ea6/runs`。摘要JSON、CSV、环境和哈希同目录。
- 本交接只放报告及小型摘要；重复嵌套的分析缓存、源码副本、依赖、渲染检查和私钥不进入Git。

本轮没有修改队友源码、正式服务开关或真实用户数据。接下来由AI负责人确认问题后修复，再另开新批次复用冻结用例进行双组复测。完整后端与App验收另做。
'''
(ROUND/'reports/团队交接摘要.md').write_text(text,encoding='utf-8')
handoff=REPO/'tests/交接文件夹/2026-11-04_Jev开关对照';handoff.mkdir(parents=True,exist_ok=True)
names=['Jev开关对照测试总览.xlsx','Garin_Jev开关对照测试工作记录.docx','团队交接摘要.md','summary.json','问题清单.csv','逐题开关对照.csv']
for name in names:shutil.copy2(ROUND/'reports'/name,handoff/name)
manifest={name:sha(ROUND/'reports'/name) for name in names}
write(ROUND/'evidence/deliverable-hashes.json',{'files':manifest,'handoff_copies_identical':all(sha(handoff/name)==digest for name,digest in manifest.items())})
print('Reports copied to',handoff)
