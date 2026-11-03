# P0 基础操作 测试结果

来源：docs/versions/V1-P0/README.md。按功能归属测试，不回退安装历史版本。

功能细项：新增与采购草稿；库存与位置查询；确认前不写入。

模块源码检查：{'PASS': 26}；当前P8.6入口真实模型：{'PASS': 27, 'FAIL': 5}，实际32题次。


## 本组真实模型问题

- r1-vt-P0-m1-t2：把这件牛奶移到书房；失败断言 status,draft.action,draft.batch_id,draft.to_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:10。
- r1-vt-P0-m1-t3：更正刚才的位置，改到餐桌旁；失败断言 same_draft；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:11。
- r1-vt-P0-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:12。
- r1-vt-P0-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:16。
- r2-vt-P0-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:268。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
