# V1-P3 只读规划 AI

一次初始意图提取，确定性 Python 统计/预测/补货，结构化续接不调用模型。复用 P0 的 DeepSeek 请求及累计预算、P1 草稿和 P2 风险规则；旧工厂、旧 Command 不变。

启动入口 `python -m uvicorn p3.app:create_app --factory --host 127.0.0.1 --port 8767`。需要通过受保护配置提供 AI_SERVICE_TOKEN、BACKEND_BASE_URL、BACKEND_TOOL_TOKEN；选择 P3_ENGINE=rules（默认）或 deepseek（需要 DEEPSEEK_API_KEY）。不自动加载 .env。服务只允许可信后端访问；本轮没有替换正式 P2/P1 容器。

接口：POST /agent/message、/agent/clarification、/consumption/query、/forecast/evaluate、/procurement/suggest，兼容 /risk/evaluate 和 /knowledge/rules。均为只读；PLAN_ADD 仅为待确认草稿。

后端需要新增 GET /internal/v1/planning/context，当前 v0.6 尚未提供。没有接口、没有覆盖、没有可靠清单时明确降级；不交付假库存/假事件服务。

本地验证（在 agent 目录）：

```text
python -m pytest tests/test_p3.py -q
python -m eval.p3.run --engine rules --split test
python -m eval.p3.run --engine deepseek --split test
python -m p3.export_contract
```

真实模型沿用 .cache/p0/budget.sqlite、eval/pricing.json 和已有认证；无自动重试。P3 数据集和结果在 eval/p3，仅本地保存。回测方式见 eval/p3/backtest.py；当时捕获的历史快照不能用当前状态重建。

详细交付、字段、后端协作和限制见 [阶段文档](../../docs/versions/V1-P3/README.md)。服务器仅同步 source_manifest.py 白名单的运行代码，不同步本 README、export_contract.py、测试/评测或说明文件。
