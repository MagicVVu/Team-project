# V1-P7 家庭库存对话接入配置

入口 `conversation.app:create_app`，版本 0.7.0。复用 P6 生命周期、风险与规划工具；AI 无状态、不写库存或采购清单。P6 入口保持原样。

本阶段提供受信对象引用、原批次重读、引用澄清续接，以及调用方的零模型回复解析参考。Android 页面、任务持久化和确认执行由业务方承接。

```bash
python -m uvicorn conversation.app:create_app --factory --host 127.0.0.1 --port 8767
```

启动进程需要已有的 AI_SERVICE_TOKEN、BACKEND_BASE_URL、BACKEND_TOOL_TOKEN；DeepSeek 模式还需要 P3_ENGINE=deepseek、LLM_MODEL 和 DEEPSEEK_API_KEY。直接运行 uvicorn 不会自动读取私有配置文件；由部署方注入既有环境。P6.1 的运行工具仍启动 P6，不因同步 P7 自动改动。

容器构建文件为 Dockerfile.conversation，仅供部署负责人审阅，本轮不构建/重启正式容器。

内部消息可选 reference。手机不得直连内部接口或自行声明可信引用。公开四字段网关不会自动转发 reference；须由独立受信业务适配层接入。没有引用时明确要求名称或重新选择，不从聊天文字猜库存。

`replies.py` 是调用方参考实现：BoundTask 必须由业务方按真实用户权限和最新修订加载，resolve_reply 只返回建议的结构化答案。它不保存任务、不替 Android 生命周期管理、不证明选项仍是最新。结构化答案最终仍由原网关检查修订并由 AI 重读库存。

完整交付：[本阶段入口](../../docs/versions/V1-P7/README.md)。
