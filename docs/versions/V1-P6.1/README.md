# V1-P6.1 AI 运行配置与后端协同

日期：2026-10-16。本阶段单独记录 P6 之后的 DeepSeek 配置工作：配置操作工具、用户隐藏输入密钥、启动环境加载及 Compose 配置片段。AI 业务版本仍为 0.6.0，沿用 P6 的 OpenAPI、结果和澄清协议，现有数据库网关不改动。

## Word 交付

- [AI运行配置改动记录（3页）](V1-P6.1_AI运行配置改动记录_2026-10-16.docx)：本次完成的工作、文件位置、测试证据、服务器同步及尚未完成的验收。
- [AI后端配置契约（4页）](V1-P6.1_AI后端配置契约_2026-10-16.docx)：六项运行变量、身份与认证、主机和容器配置、后端验收步骤及维护方式。

两份 Word 已逐页渲染检查；文档不包含真实密钥或内部令牌。说明、测试和文档保留本地仓库，未上传服务器。本次没有提交或推送 Git。

## 当前状态

| 项目 | 状态 |
|---|---|
| 密钥保存 | 用户已在自己的 SSH 终端隐藏输入；仅验证存在性，未回传密钥值 |
| 服务器私有配置 | `~/workspace/agent/.env.runtime`，权限 `0600` |
| 操作工具 | `agent/integration/runtime_config.py` 已单独核验同步到服务器 |
| 本地专项测试 | 17 项通过、1 项 Windows 符号链接权限跳过；服务器 Linux 实际权限与符号链接检查通过 |
| 内部认证 | 本次可检查的 AI 工作区和 SSH 环境尚未注入两项原有令牌，不代表正式后端没有配置 |
| 模型在线有效性 | 未验证，本次没有调用供应商 API |
| 正式部署 | 未启动、构建、重启或切换正式服务；Compose 片段尚未应用 |
| 业务接口 | 沿用 P6；原 58 个 P6 业务运行文件和数据库网关未改动 |

下一步由部署负责人注入原有 `AI_SERVICE_TOKEN`、`BACKEND_TOOL_TOKEN` 和实际网络中的 `BACKEND_BASE_URL`，显式加载模型配置，再分别验证进程、模型和真实业务链路。

## 代码与说明

- [运行配置工具](../../../agent/integration/runtime_config.py)
- [工具专项测试](../../../agent/tests/test_runtime_config.py)
- [Compose 模型环境覆盖示例](../../../deploy/compose.ai-model-env.override.yaml)：仅配置片段，非独立部署文件。
- [服务器配置与密钥输入说明](model-runtime-configuration.md)
- [P6 业务接口契约](../V1-P6/ai-contract.md)、[P6 OpenAPI](../V1-P6/ai-openapi.json)

`status` 的 `service_ready` 仅检查所需变量非空，不能代替网络和权限验收；`services_started` 与 `provider_key_validated_online` 固定返回 false，不能用来监控其他进程或证明供应商调用结果。P6 的 557 项回归和模型保留 96/96 是前一阶段证据，本次未重跑。
