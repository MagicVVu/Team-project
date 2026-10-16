# V1-P6.1 服务器 DeepSeek 运行配置

本次配置改动单独归档为 V1-P6.1，基于 V1-P6，AI 业务版本仍为 0.6.0；本次不修改业务接口或现有数据库网关。两份 Word 及当前状态见[本阶段入口](README.md)。

日期：2026-10-16。用户授权配置，真实密钥由用户在自己的终端输入；不从本机复制已有密钥，不通过聊天或工具返回值收集密钥。

## 已完成

- 服务器私有文件：`/home/magicvvu_ai/workspace/agent/.env.runtime`，权限600，默认模型`deepseek-flash`，`P3_ENGINE=deepseek`。用户已在独立SSH窗口亲自输入密钥，之后仅检查到`provider_key_present=true`，没有读取展示或回传密钥值。
- 服务器操作工具：`~/workspace/agent/integration/runtime_config.py`，负责初始化、隐藏输入、状态检查及手动启动时加载配置。不会自动启动服务、调用模型或生成/替换后端令牌。
- 初始化保留已有密钥；写入采用私有临时文件与原子替换，拒绝符号链接和其他账号所有的配置。密钥需输入两次，若不能隐藏输入则拒绝，不退回明文输入。
- 配置文件由`.env.*`规则排除Git及AI镜像构建；新增工具测试17项通过，Windows上1项符号链接测试因权限跳过，服务器Linux实际权限及符号链接检查通过。
- 原58个P6业务运行文件及网关未修改，操作工具单独核验同步，配置文件不回传本地。本轮没有重置预算、修改模型业务代码或切换正式服务。

## 输入密钥

在用户自己的SSH终端运行：

```bash
cd ~/workspace/agent
.venv-p2/bin/python -B -m integration.runtime_config set-key
```

出现`DeepSeek API key (hidden input):`后粘贴真实密钥并回车；第二次输入同一密钥确认。输入过程中不显示字符，也不将密钥放入命令行或历史。工具只显示保存成功及布尔配置状态，不能证明密钥已通过供应商验证；本步骤不会产生模型请求。

检查状态：

```bash
cd ~/workspace/agent
.venv-p2/bin/python -B -m integration.runtime_config status
```

`provider_key_present=true`表示已配置；不要使用`cat .env.runtime`或截图分享密钥。

## 手动启动与正式部署边界

现有应用仍通过`os.getenv`读取变量；配置加载由操作工具完成，直接运行旧uvicorn命令不会自动读取`.env.runtime`。

后续在已注入原业务认证配置的终端中，可执行：

```bash
cd ~/workspace/agent
.venv-p2/bin/python -B -m integration.runtime_config run
```

工具继承启动环境中的`AI_SERVICE_TOKEN`、`BACKEND_TOOL_TOKEN`及`BACKEND_BASE_URL`，密钥文件的非空模型配置覆盖旧规则模式。主机侧未指定后端地址时默认使用已检查可访问的`http://127.0.0.1:8000`。仅监听本机8767，不启动后台进程。缺少密钥或任一认证令牌会明确拒绝启动，不生成替代令牌。

本轮检查发现：AI工作区与SSH环境未提供两项后端认证令牌，当前账号也无法列出正式部署目录。不能据此认定正式后端本身没有配置令牌；应由原部署配置注入其已有值，避免与网关认证不一致。DeepSeek密钥已保存，模型配置已就绪；正式服务启动仍依赖这两项认证配置。供应商在线有效性未验证，本步骤未调用模型。

若正式环境使用Docker，由部署负责人合并本地[模型环境变量覆盖示例](../../../deploy/compose.ai-model-env.override.yaml)，保留既有服务/工具令牌、容器后端地址、网络及账本卷。该文件只是配置片段，不是独立部署文件。私有文件需由授权部署账号读取，不放宽权限供其他账号任意读取；不能把主机侧localhost地址直接当成容器后端地址。

本轮未修改或读取展示正式部署的密钥，未构建/重启容器，未提交或推送Git。
