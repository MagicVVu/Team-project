# P6 位置摘要与反馈 测试结果

来源：docs/versions/V1-P6/README.md。按功能归属测试，不回退安装历史版本。

功能细项：按位置反查和明确用完；首页按需摘要；真实回执与操作后反馈。

模块源码检查：{'PASS': 93}；当前P8.6入口真实模型：{'PASS': 24, 'FAIL': 8}，实际32题次。


## 本组真实模型问题

- r1-vt-P6-s3：这件牛奶用完了；失败断言 status,draft.action,draft.quantity,draft.batch_id；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:99。
- r1-vt-P6-s6：现在这件牛奶还放冰箱吗；失败断言 status,fact_location；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:102。
- r1-vt-P6-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:108。
- r2-vt-P6-s3：这件牛奶用完了；失败断言 status,draft.action,draft.quantity,draft.batch_id；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:355。
- r2-vt-P6-s8：给我查牛奶数量和位置；失败断言 status；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:360。
- r2-vt-P6-m1-t3：更正刚才的位置，改到餐桌旁；失败断言 status,draft.action,draft.to_location,same_draft；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:363。
- r2-vt-P6-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:364。
- r2-vt-P6-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:368。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
