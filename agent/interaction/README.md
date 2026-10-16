# P5 确认文字输入适配

入口 `python -m uvicorn interaction.app:create_app --factory --host 127.0.0.1 --port 8767`。继续使用AI_SERVICE_TOKEN、BACKEND_BASE_URL、BACKEND_TOOL_TOKEN、P3_ENGINE和已有模型认证/累计账本，不自动加载.env。新增的是P3输入配置，未复制业务Manager或新增ASR服务。

schema/policy/manager负责确认文字、保守口语防护及续接来源；session是调用方持有的无存储状态参考；tasks是现有数据库网关的类型客户端。它们不会接管业务任务数据库、确认事务或Android系统识别。

正式网关保持不变；公共消息只发送household_id/text/request_id/household_timezone。input元数据可由受信调用方直接向AI使用，当前公开网关路径上保存在调用端，不要求转发。公开澄清不发送item_key或空answers。

本地验证（agent目录）：

```text
python -m pytest tests/test_interaction.py -q
python -m eval.p5.run --engine rules --split test
python -m eval.p5.run --engine deepseek --split test
python -m interaction.export_contract
```

独立真实模型保留评测59/60完整流程通过，有1次非法模型输出被拒绝；未修改保留集、没有重跑覆盖该失败。默认规则引擎60/60通过。现有前端、数据库网关和正式服务没有更改，真机语音及真实用户链路待协同验收。

详细契约和交付见[阶段文档](../../docs/versions/V1-P5/README.md)。运行源码按白名单同步~/workspace/agent，README、导出器、OpenAPI和评测数据不上传。
