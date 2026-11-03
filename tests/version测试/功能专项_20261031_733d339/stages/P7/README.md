# P7 引用与续接 测试结果

来源：docs/versions/V1-P7/README.md。按功能归属测试，不回退安装历史版本。

功能细项：可信对象引用；澄清路由和任务修订；跨家庭和过期保护。

模块源码检查：{'PASS': 86}；当前P8.6入口真实模型：{'PASS': 30, 'FAIL': 2}，实际32题次。


## 本组真实模型问题

- r1-vt-P7-m1-t1：牛奶有多件，先让我选哪一件移动；失败断言 status；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:121。
- r2-vt-P7-s7：开始一个新任务；失败断言 clear_reference；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:375。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
