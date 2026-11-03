# P8.6 自主循环 测试结果

来源：docs/versions/V1-P8.6/README.md。按功能归属测试，不回退安装历史版本。

功能细项：实际可超过两次调用；错误反馈与停止机制；逐件库存和跨协议恢复。

模块源码检查：{'PASS': 47}；当前P8.6入口真实模型：{'PASS': 26, 'FAIL': 6}，实际32题次。

当前逐件入口与旧批次兼容结果分开；半件扣减不在当前契约。

## 本组真实模型问题

- r1-vt-P8.6-m1-t2：把这件牛奶移到书房；失败断言 status,draft.action,draft.batch_id,draft.to_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:250。
- r1-vt-P8.6-m1-t3：更正刚才的位置，改到餐桌旁；失败断言 same_draft；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:251。
- r1-vt-P8.6-m2-t1：一起核对这件牛奶数量和位置；失败断言 status；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:253。
- r1-vt-P8.6-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:256。
- r2-vt-P8.6-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:508。
- r2-vt-P8.6-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:512。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
