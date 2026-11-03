# P4 历史缺陷 测试结果

来源：docs/versions/V1-P4/README.md。按功能归属测试，不回退安装历史版本。

功能细项：中文数字与品牌；日期和查询范围；多操作与异常输出。

模块源码检查：{'PASS': 122}；当前P8.6入口真实模型：{'PASS': 27, 'FAIL': 5}，实际32题次。


## 本组真实模型问题

- r1-vt-P4-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:76。
- r1-vt-P4-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:80。
- r2-vt-P4-s2：新增2盒和润牛奶放厨房；失败断言 status,draft.action,draft.name,draft.quantity,draft.unit,draft.location,created_count；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:322。
- r2-vt-P4-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 status；程序或模型循环问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:332。
- r2-vt-P4-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:336。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。

## 原84次问题

P4另重放旧测试包：原84次程序问题中81次满足原断言，P1 p0-41-2与旧Android网关ext-013/ext-015三次仍保留FAIL。旧包原始37次FAIL按入口/契约分列，未修改预期，也不当作37个新缺陷。
