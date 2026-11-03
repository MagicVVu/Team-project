# P5 确认文字 测试结果

来源：docs/versions/V1-P5/README.md。按功能归属测试，不回退安装历史版本。

功能细项：编辑后的最终文字；未确认零调用；否定口误取消和任务协议。

模块源码检查：{'PASS': 83}；当前P8.6入口真实模型：{'PASS': 28, 'FAIL': 4}，实际32题次。

输入确认元数据在模块测试验证；真实语义题仅发送最终文字，不代表手机已实现确认流程。

## 本组真实模型问题

- r1-vt-P5-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:92。
- r1-vt-P5-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:96。
- r2-vt-P5-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:348。
- r2-vt-P5-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:352。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
