# P8.4 自然语义 测试结果

来源：docs/versions/V1-P8.4/README.md。按功能归属测试，不回退安装历史版本。

功能细项：自然任务理解；否定假设和改口；只读和草稿边界。

模块源码检查：{'PASS': 48}；当前P8.6入口真实模型：{'PASS': 27, 'FAIL': 5}，实际32题次。


## 本组真实模型问题

- r1-vt-P8.4-s3：不是要丢弃，我是说这件牛奶喝完了，登记消耗；失败断言 status,draft.action,draft.batch_id,draft.quantity；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:211。
- r1-vt-P8.4-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:224。
- r2-vt-P8.4-s3：不是要丢弃，我是说这件牛奶喝完了，登记消耗；失败断言 status,draft.action,draft.batch_id,draft.quantity；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:467。
- r2-vt-P8.4-s8：今天收拾厨房累了，帮我安排轻松一点；失败断言 status；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:472。
- r2-vt-P8.4-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:480。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
