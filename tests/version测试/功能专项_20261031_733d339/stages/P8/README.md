# P8 聊天任务控制 测试结果

来源：docs/versions/V1-P8/README.md。按功能归属测试，不回退安装历史版本。

功能细项：任务解释；草稿修改和取消；等待和请求恢复。

模块源码检查：{'PASS': 46}；当前P8.6入口真实模型：{'PASS': 25, 'FAIL': 7}，实际32题次。


## 本组真实模型问题

- r1-vt-P8-m1-t3：更正刚才的位置，改到餐桌旁；失败断言 status,draft.action,draft.to_location,same_draft；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:155。
- r1-vt-P8-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:156。
- r1-vt-P8-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:160。
- r2-vt-P8-s2：刚才准备改哪些内容；失败断言 pending_reply；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:402。
- r2-vt-P8-m1-t1：一起核对这件牛奶数量和位置；失败断言 status；模型结构输出问题。证据 runs/formal-20261031T133800/questions.jsonl:409。
- r2-vt-P8-m1-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 status,fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:412。
- r2-vt-P8-m2-t4：这件牛奶目前实际在哪里，尚未确认移动；失败断言 fact_location；程序或模型理解问题待定位。证据 runs/formal-20261031T133800/questions.jsonl:416。

完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。
