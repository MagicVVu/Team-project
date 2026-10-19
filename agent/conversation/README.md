# V1-P7 家庭库存对话接入配置

入口 `conversation.app:create_app`，版本 0.7.0。复用 P6 生命周期、风险与规划工具；AI 无状态、不写库存或采购清单。P6 入口保持原样。

本阶段提供受信对象引用、原批次重读、引用澄清续接，以及调用方的零模型回复解析参考。Android 页面、任务持久化和确认执行由业务方承接。

```bash
python -m uvicorn conversation.app:create_app --factory --host 127.0.0.1 --port 8767
```

启动进程需要已有的 AI_SERVICE_TOKEN、BACKEND_BASE_URL、BACKEND_TOOL_TOKEN；DeepSeek 模式还需要 P3_ENGINE=deepseek、LLM_MODEL 和 DEEPSEEK_API_KEY。直接运行 uvicorn 不会自动读取私有配置文件；由部署方注入既有环境。

V1-P7.1 的私有配置工具支持显式选择 P7；以下检查仅返回配置是否齐全及启动参数，不连接模型或启动服务，缺配置时退出码为 1：

```bash
cd ~/workspace/agent
.venv-p2/bin/python -B -m integration.runtime_config check --profile p7
```

部署负责人正式选择 P7 时，可使用 `integration.runtime_config run --profile p7`（同一 Python、工作目录）。这会启动本机监听进程，不能与已有服务重复运行。本轮只同步源码，不执行此命令；旧命令省略 `--profile` 时仍保留 P6 行为。配置检查通过只证明本地配置完整，不证明令牌有效、网络可达或模型在线可用。详见 [P7.1 收尾与运行说明](../../docs/versions/V1-P7.1/README.md)。

容器构建文件为 Dockerfile.conversation，仅供部署负责人审阅，本轮不构建/重启正式容器。

内部消息可选 reference。手机不得直连内部接口或自行声明可信引用。公开四字段网关不会自动转发 reference；须由独立受信业务适配层接入。没有引用时明确要求名称或重新选择，不从聊天文字猜库存。

`replies.py` 是调用方参考实现：BoundTask 必须由业务方按真实用户权限和最新修订加载，resolve_reply 只返回建议的结构化答案。它不保存任务、不替 Android 生命周期管理、不证明选项仍是最新。结构化答案最终仍由原网关检查修订并由 AI 重读库存。

完整交付：[本阶段入口](../../docs/versions/V1-P7/README.md)。
