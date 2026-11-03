# P8.3 规划来源 测试结果

来源：docs/versions/V1-P8.3/README.md。按功能归属测试，不回退安装历史版本。

功能细项：显式商品聚合和事件语义；待购三态与当前数据限制；精确basis和只读重验。

模块源码检查：{'PASS': 48}；当前P8.6入口真实模型：{'PASS': 17, 'FAIL': 15}，实际32题次。

原P3给定完整事实可验证0.25、8天、建议1；当前商品级规划契约仍明确缺整体覆盖/可用量，不编造精确日期。

## 本组真实模型问题

- r1-vt-P8.3-s2：牛奶所有关联物品合计多少；失败断言 product_total,planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:194。
- r1-vt-P8.3-s4：牛奶未购项为空时给我规划依据；失败断言 planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:196。
- r1-vt-P8.3-s5：牛奶的过期数量能直接当可用库存吗；失败断言 no_precise_product_forecast；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:197。
- r1-vt-P8.3-s6：没有商品整体覆盖天数时预测牛奶耗尽日；失败断言 no_forecast_date；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:198。
- r1-vt-P8.3-s8：牛奶库存更正能当消费吗，请查询消费统计；失败断言 recorded_consumption；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:200。
- r1-vt-P8.3-m1-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:204。
- r1-vt-P8.3-m2-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:208。
- r2-vt-P8.3-s1：按牛奶这个商品汇总登记消费；失败断言 recorded_consumption,planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:449。
- r2-vt-P8.3-s2：牛奶所有关联物品合计多少；失败断言 product_total,planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:450。
- r2-vt-P8.3-s4：牛奶未购项为空时给我规划依据；失败断言 planning_evidence；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:452。
- r2-vt-P8.3-s5：牛奶的过期数量能直接当可用库存吗；失败断言 no_precise_product_forecast；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:453。
- r2-vt-P8.3-s8：牛奶库存更正能当消费吗，请查询消费统计；失败断言 recorded_consumption；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:456。
- r2-vt-P8.3-m1-t1：查牛奶过去28天登记消费统计；失败断言 recorded_consumption；规划入口或理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:457。
- r2-vt-P8.3-m1-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:460。
- r2-vt-P8.3-m2-t4：重新核对牛奶现在的位置；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:464。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
