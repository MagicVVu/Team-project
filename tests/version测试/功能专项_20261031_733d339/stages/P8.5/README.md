# P8.5 旧话题续接 测试结果

来源：docs/versions/V1-P8.5/README.md。按功能归属测试，不回退安装历史版本。

功能细项：会话片段与话题检索；旧任务续接和事实刷新；原引用有效期不延长。

模块源码检查：{'PASS': 80}；当前P8.6入口真实模型：{'FAIL': 14, 'PASS': 18}，实际32题次。


## 本组真实模型问题

- r1-vt-P8.5-s3：刚才说牛奶在书房，那只是旧记录，现在核对；失败断言 status；程序或模型循环问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:227。
- r1-vt-P8.5-s7：接着之前那件，核对现在位置；失败断言 status,error_code；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:231。
- r2-vt-P8.5-s5：整理厨房好累，先聊聊如何分类；失败断言 status；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:485。
- r2-vt-P8.5-s7：接着之前那件，核对现在位置；失败断言 error_code；版本契约差异待复核。证据 runs/formal-20261031T133800/questions.jsonl:487。
- r1-vt-P8.5-s1：回到先前牛奶的话题，它在哪里；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:1。
- r1-vt-P8.5-s2：之前聊的牛奶还剩几件；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:2。
- r1-vt-P8.5-s8：开始新的问题，不沿用原对象；失败断言 clear_reference；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:4。
- r1-vt-P8.5-m1-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:13。
- r1-vt-P8.5-m2-t3：回到牛奶，核对现在数量；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:19。
- r2-vt-P8.5-s1：回到先前牛奶的话题，它在哪里；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:21。
- r2-vt-P8.5-s2：之前聊的牛奶还剩几件；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:22。
- r2-vt-P8.5-m1-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:33。
- r2-vt-P8.5-m2-t1：继续牛奶的话题，查现在的位置；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:37。
- r2-vt-P8.5-m2-t3：回到牛奶，核对现在数量；失败断言 status,fact_quantity；程序或模型理解问题待定位。证据 runs/archive-recheck-20261031T134901/questions.jsonl:39。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
