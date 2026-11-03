# P2 风险判断 测试结果

来源：docs/versions/V1-P2/README.md。按功能归属测试，不回退安装历史版本。

功能细项：标签期限与保存条件；未知信息降级；规则来源与审核边界。

模块源码检查：{'PASS': 92}；当前P8.6入口真实模型：{'PASS': 30, 'FAIL': 2}，实际32题次。


## 本组真实模型问题

- r1-vt-P2-m2-t1：核对这件牛奶的风险与依据；失败断言 risk_unknown；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:45。
- r2-vt-P2-s3：缺少保存条件时能判断这件牛奶安全吗；失败断言 risk_unknown；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:291。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
