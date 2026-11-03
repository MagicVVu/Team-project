# P8.1 范围和来源修复 测试结果

来源：docs/versions/V1-P8.1/README.md。按功能归属测试，不回退安装历史版本。

功能细项：指定对象查询与全部用完；单位和采购来源；归档与降级反馈。

模块源码检查：{'PASS': 49}；当前P8.6入口真实模型：{'PASS': 28, 'FAIL': 4}，实际32题次。


## 本组真实模型问题

- r1-vt-P8.1-s3：根据这件牛奶，计划买2盒；失败断言 procurement_source；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:163。
- r1-vt-P8.1-s8：采购草稿生成就已经买到牛奶了吗；失败断言 pending_reply；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:168。
- r2-vt-P8.1-s3：根据这件牛奶，计划买2盒；失败断言 procurement_source；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:419。
- r2-vt-P8.1-s8：采购草稿生成就已经买到牛奶了吗；失败断言 pending_reply；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:424。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
