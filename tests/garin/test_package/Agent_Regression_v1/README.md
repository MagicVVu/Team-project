> 本文件保留原测试包 v1.0 的说明与历史成绩。当前交付的运行方法以 `../../README.md` 为准；实际证据位于 `../../evidence/current_run/`，分类失败清单位于 `../../失败清单.md`。本目录没有附带原包的 `reports/p0_rules_baseline` 历史目录，也没有附带模型服务源码。请通过根目录隔离运行入口重测，不要将下文历史成绩当作新版成绩。
# 家庭物品管家 AI Agent 回归测试包 v1.0

给 Garin-cyber 和团队：每次改模型、提示词、规则或业务代码后，运行同一套用例，检查有没有把原来正常的功能改坏。

这套测试不能保证覆盖所有用户情况，也不等于正式上线验收。新增用例由AI构造，尚未人工签字；团队应先确认预期答案，再把它作为正式发布标准。不要为了获得高分而把失败用例删除或改成迎合程序的答案。

## 包含什么

|文件|数量|用途|
|---|---:|---|
|cases/baseline_150.jsonl|150|原样本的复核后断言，保留原ID、分组和原dev/test来源；原文件备份在reference|
|cases/extended.jsonl|96|新增表达、数量、单位、日期、位置、歧义、注入与范围边界|
|cases/flows.jsonl|32|确认、编辑、取消、幂等、权限、撤销、事务失败等HTTP流程|
|cases/future_scenarios.jsonl|24|多轮、真实并发、数据库、语音、离线、性能等后续验收场景；未实现自动适配|

默认运行前3个文件，共278条。其中18条规则存在争议，默认标记REVIEW，不计正式评分。另24条是后续能力清单，不冒充已自动化；显式运行时会显示BLOCKED。总计302条用例/场景，不等于302条独立真实用户表达。manifest.json列出了5组重复文本，保留是为了原样本可追溯和针对性回归。

看中文内容先打开《用例目录.md》；看已有失败先打开 reports/p0_rules_baseline/report.md。

## 本次真实运行结果

环境：Python 3.12，按原项目requirements.lock.txt安装依赖；本地规则引擎+内存Mock后端。

- PASS 242，FAIL 18，REVIEW 18；本轮必测项通过率242/260=93.08%，未通过全部必测项。
- 32条流程全部通过，但仅代表Mock HTTP流程；其中库存版本冲突是依次提交，不是同时并发。
- 未调用真实DeepSeek，未连接真实业务数据库，未验证真实语音/界面/断网体验。
- 原150条中3条“饼干”失败，1条意图待定；其他新增失败涉及名称、中文数字、日期及多操作处理等。
- 11项评分器自测通过，覆盖位置/日期/动作/版本漏检、意外写入、跨家庭数据、候选批次和缺失字段等问题。

详细原始输出、状态快照、HTTP响应、失败断言及报告都已保存。评分器自测通过不代表软件本身通过。

## 第一次运行：你们目前的agent项目

需要Python 3.11或以上。将本测试包与解压后的agent目录放在旁边，例如：

- 工作目录/agent/p0/app.py
- 工作目录/Agent_Regression_v1/run.py

在Agent_Regression_v1目录打开终端。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ..\agent\requirements.lock.txt
.\.venv\Scripts\python.exe run.py --project ..\agent --version V1-P0-local
```

macOS/Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r ../agent/requirements.lock.txt
.venv/bin/python run.py --project ../agent --version V1-P0-local
```

`--project`指包含p0文件夹的源码根目录，不是zip文件；路径有空格时加双引号。路径位置不同就相应调整。

默认使用rules，不需要API密钥，不启动外部服务器。每条用例新建隔离Mock库存，不会清空你们实际业务数据库。P0应用初始化可能创建自己的模型预算记录文件。

每次运行自动创建新的reports/时间戳目录，包括：

- summary.json：版本、用例哈希、分母、统计与是否全部通过。
- results.jsonl：逐条输出、失败原因及状态快照，方便程序读取。
- report.md：团队可直接阅读的问题列表。

退出码0表示本轮选定的required用例全通过；退出码1表示存在失败、错误或未覆盖的必测项。配置错误可能返回2。测试失败返回非零是正常设计，不是脚本坏了。不要仅看“运行结束”。

## 运行真实模型

在终端环境变量中配置原项目要求的DEEPSEEK_API_KEY，不要把密钥写进样本或提交到仓库。然后运行：

```bash
python run.py --project ../agent --version V1-P0-deepseek --engine deepseek --allow-paid-model --repeat 3
```

这会产生真实模型调用，可能收费；原项目预算、超时和网络限制仍然生效。建议先选一个样本文件小批运行。repeat=3会逐条重复并分别保留结果，任何一次必测失败都会使本轮未通过，不能只挑最好的一次。统计分母为运行次数，而不是去重后的样本数。

注意：当前适配器的message用例使用所选引擎，flow用例始终使用规则模式或手工草稿，以独立验证业务行为。单条证据execution明确区分二者。真实模型解析+真实后端的整条链路，需要后续适配器补齐。

## 只运行部分 / 查看待定规则

```bash
python run.py --project ../agent --version V1-P0-flows --cases cases/flows.jsonl
python run.py --project ../agent --version review-trial --cases cases/extended.jsonl --include-review
python run.py --project ../agent --version future-check --cases cases/future_scenarios.jsonl
```

`--include-review`仅用于探索待定用例的实际结果，它们仍不进入required发布分母。待团队确定语义后，修改expected与gate并升级套件版本、记录修改理由。future-check目前会返回BLOCKED，而不是通过；这用于明确记录还缺哪些测试能力。

## 换一代软件如何继续用

1. 保留当前套件版本，每次记录软件版本/提交号、模型名及提示词版本。
2. 如果p0代码结构没变，替换--project路径直接运行。
3. 如果换框架或接口，新增一个Python适配器，实现evaluate(case, config)，不要修改评分器来适应错误输出。详细接口见ADAPTER.md。
4. 原P0“多物品不支持”等规则以后可能升级；发布新套件版本，更新受影响的期望并留变更记录，其他基础用例继续保留。
5. 正式后端必须在独立测试数据库中安装seed-v1或等价数据，用适配器采集真实前后状态；不能把Mock成绩当作数据库验收。
6. 每修复一个真实用户问题，去掉私人信息，将原输入和预期结果补成永久回归用例。另留一批未用于调参的真实用户表达作独立验收，本包是可见回归集，不是盲测集。

对比两次运行：

```bash
python compare.py reports/旧运行目录 reports/新运行目录
```

只把用例文件哈希相同的两轮当成同口径对比。引擎不同也会提示，避免把规则引擎与大模型成绩混为一谈。

## 人工检查仍然必要

自动断言检查结构化意图、状态、完整草稿、查询事实、候选批次、确认前状态不变等；不检查回复每个字是否合适，也无法证明自由文本中完全没有幻觉或泄漏。请抽查回复是否易懂、是否误导、有没有多余要求和敏感信息，并实际走一遍界面。日期/单位/多轮策略有争议时先统一产品规则。

没有预先约定的性能阈值，不自动判定性能通过；没有真实音频，不声称语音识别已经测过；没有并发驱动，不声称通过并发验收。

