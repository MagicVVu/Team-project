# P8.2 当前会话记忆 测试结果

来源：docs/versions/V1-P8.2/README.md。按功能归属测试，不回退安装历史版本。

功能细项：可信近期历史；对象追问和新会话；任务状态与恢复。

模块源码检查：{'PASS': 33}；当前P8.6入口真实模型：{'PASS': 18, 'FAIL': 14}，实际32题次。


## 本组真实模型问题

- r1-vt-P8.2-s2：继续刚才牛奶的话题，查数量；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:178。
- r1-vt-P8.2-s4：现在开始一个新任务；失败断言 clear_reference；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:180。
- r1-vt-P8.2-s5：刚才是否已经执行；失败断言 status,unknown_receipt；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:181。
- r1-vt-P8.2-s6：过去的聊天说在书房，请核对现在实际位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:182。
- r1-vt-P8.2-s7：接着之前那一件，位置在哪；失败断言 error_code；版本契约差异待复核。证据 runs/formal-20261031T133800/questions.jsonl:183。
- r2-vt-P8.2-s2：继续刚才牛奶的话题，查数量；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:434。
- r2-vt-P8.2-s7：接着之前那一件，位置在哪；失败断言 error_code；版本契约差异待复核。证据 runs/formal-20261031T133800/questions.jsonl:439。
- r1-vt-P8.2-m1-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:5。
- r1-vt-P8.2-m1-t3：回到牛奶，核对现在数量；失败断言 status；程序或模型循环问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:7。
- r1-vt-P8.2-m2-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:9。
- r2-vt-P8.2-m1-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:25。
- r2-vt-P8.2-m1-t3：回到牛奶，核对现在数量；失败断言 status；程序或模型循环问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:27。
- r2-vt-P8.2-m2-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:29。
- r2-vt-P8.2-m2-t3：回到牛奶，核对现在数量；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:31。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
