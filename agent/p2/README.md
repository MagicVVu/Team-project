# V1-P2 基础风险与本地规则服务

P2 新增确定性风险工具、本地规则查询及 Manager 风险问答，沿用 P1 的生命周期草稿和澄清续接。只开发 AI 服务，不修改前后端，不新增 Mock 服务或演示页。风险结果是基于登记事实的关注提示，不代表实物已经检测安全。

## 已实现

- 区分食品 use-by、best-before 与药品 expiry，不把所有日期混为安全期限。
- 输出 green、yellow、orange、red、unknown，以及原因、事实证据、来源、缺失信息、规则版本和评估时间。
- 检查明确登记的保存条件；不会从“冰箱”等位置文字推定温度或保存合规。
- 开封后规则要求具体商品、包装来源和明确天数；默认不提供通用“牛奶开封几天”规则。
- 缺事实、无适用规则、规则冲突或标签适用性不明确时返回待核对；已证实的严重关注不会被普通缺字段隐藏。
- P2 Manager 支持“哪些需要关注”“牛奶为什么被提醒”等问题。模型只提取任务与名称，风险和中文解释由工具与受控模板生成，不额外付费生成自由安全结论。
- 继续复用 P1 的新增、消耗、开封、移动、丢弃、查询、采购草稿及结构化续接；P0/P1 原服务文件与接口不变。

## 运行

在 `agent` 目录使用已有 Python 与依赖：

```powershell
# 通过安全本地环境提供 AI_SERVICE_TOKEN、BACKEND_TOOL_TOKEN、DEEPSEEK_API_KEY。
$env:BACKEND_BASE_URL = 'http://127.0.0.1:8080'
$env:P2_ENGINE = 'deepseek' # 或 rules；默认 deepseek
& 'D:\python\python3.13.5\python.exe' -m uvicorn p2.app:create_app --factory --host 127.0.0.1 --port 8768
```

不自动加载 .env。缺少服务认证或读工具配置时启动失败；没有后端时读取失败会明确返回，不提供假库存。`P2_RULES_PATH` 可选择管理员维护的本地规则文件；规则校验失败时拒绝启动。风险请求不能上传或修改规则。

模型配置、768 输出 token 上限、无自动付费重试和累计 20 元账本复用 P0。纯 `/risk/evaluate` 和 P1 结构化续接不调用模型；P2 消息路由最多一次模型提取，然后调用风险工具或委托 P1 工作流。总截止时间覆盖路由、读取与处理。

## 验证与资料

```powershell
& 'D:\python\python3.13.5\python.exe' -m pytest tests -q
& 'D:\python\python3.13.5\python.exe' -m p2.export_contract
& 'D:\python\python3.13.5\python.exe' -m eval.p2.run --engine rules --split dev
& 'D:\python\python3.13.5\python.exe' -m eval.p2.run --engine rules --split test
# 以下产生供应商费用，仅在核实费率、密钥及剩余预算后执行：
& 'D:\python\python3.13.5\python.exe' -m eval.p2.run --engine deepseek --split dev
& 'D:\python\python3.13.5\python.exe' -m eval.p2.run --engine deepseek --split test
```

测试与评测使用独立输入夹具，夹具不在运行服务中加载。`p2-1` 为 150 条 AI 构造表达，90 开发／60 保留，50 个场景组；不代替真实用户语言、专家规则审核或正式数据库验收。

内置 5 条规则只核对官方标签原则和提醒偏好，`review_kind=source_check` 明确表示自动来源核对，**不是人工或专家审核**。商品专属开封规则需要真实包装证据，尚未添加到生产规则文件。

运行接口与前端映射见 [P2 接口说明](../../docs/versions/V1-P2/ai-contract.md)，规则来源见 [来源与审核](../../docs/versions/V1-P2/rule-sources.md)，实测结果见 [评测报告](../../docs/versions/V1-P2/ai-experiments.md)。
