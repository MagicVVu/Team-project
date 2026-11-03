# P3 统计预测 测试结果

来源：docs/versions/V1-P3/README.md。按功能归属测试，不回退安装历史版本。

功能细项：有效消费与去重更正；日均和耗尽日期；待购扣减与补货公式。

模块源码检查：{'PASS': 94}；当前P8.6入口真实模型：{'FAIL': 12, 'PASS': 20}，实际32题次。

原P3给定完整事实可验证0.25、8天、建议1；当前商品级规划契约仍明确缺整体覆盖/可用量，不编造精确日期。

## 本组真实模型问题

- r1-vt-P3-s1：查牛奶过去28天的登记消费统计；失败断言 status；降级状态契约待复核。证据 runs/formal-20261031T133800/questions.jsonl:49。
- r1-vt-P3-s2：牛奶最近完整观察期实际登记了多少消耗；失败断言 status；降级状态契约待复核。证据 runs/formal-20261031T133800/questions.jsonl:50。
- r1-vt-P3-s3：牛奶还可以用多少天，给出依据；失败断言 no_precise_product_forecast,planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:51。
- r1-vt-P3-s4：牛奶预计哪天用完；失败断言 no_precise_product_forecast；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:52。
- r1-vt-P3-s8：牛奶历史记录还没接通，请查消费统计；失败断言 status,stop_reason；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:56。
- r1-vt-P3-m1-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:60。
- r1-vt-P3-m2-t4：重新核对牛奶现在的位置；失败断言 status,fact_location；程序或模型循环问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:64。
- r2-vt-P3-s1：查牛奶过去28天的登记消费统计；失败断言 status；降级状态契约待复核。证据 runs/formal-20261031T133800/questions.jsonl:305。
- r2-vt-P3-s2：牛奶最近完整观察期实际登记了多少消耗；失败断言 status；降级状态契约待复核。证据 runs/formal-20261031T133800/questions.jsonl:306。
- r2-vt-P3-s3：牛奶还可以用多少天，给出依据；失败断言 no_precise_product_forecast,planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:307。
- r2-vt-P3-s8：牛奶历史记录还没接通，请查消费统计；失败断言 status,stop_reason；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:312。
- r2-vt-P3-m2-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:320。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
