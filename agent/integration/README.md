# V1-P2 真实后端对接工具

2026-10-16 P5更新：AI输入配置及既有数据库任务客户端已实现，45运行文件已核验同步；网关保持不变、正式服务未切换。P5直接兼容既有消息/任务/澄清/草稿协议，不复制backend/app.py。见[P5交付记录](../../docs/versions/V1-P5/delivery-and-validation.md)。下文34/16文件为前序同步历史。

2026-10-16更新：已将P0–P4 AI运行白名单34文件核验同步至 ~/workspace/agent，实际更新7文件，远端共用解析及P2/P3工厂检查通过。仅同步AI，backend/app.py未上传，未切换正式服务。见[同步记录](../../docs/versions/V1-P4/server-sync-2026-10-16.md)。下文16文件及P4未同步的描述是历史记录。

2026-10-15 P4更新：运行同步白名单新增6个已修复的P0/P1基础依赖，避免后续仅同步P2/P3时遗漏修复。参见[本地修复与验收记录](../../docs/versions/V1-P4/README.md)。P4没有执行远端同步；下文的同步数量及状态属于此前阶段。

这里提供 HTTP 客户端、容器探针和 AI 交付打包工具，不提供库存、业务后端、Mock 服务或演示页面。所有工具沿用当前 Python 依赖。

## 服务器开发目录约定（2026-10-15）

用户已明确：AI 实现统一直接存放在 `~/workspace/agent`，按 p2/、integration/ 分类；说明文档、OpenAPI 导出和验证报告保留在本地仓库。服务器不使用交付包暂存目录。规则 JSON、独立依赖文件和 Dockerfile 属于运行必需文件，随代码同步；原 P0/P1、原 Dockerfile 和 requirements.runtime.txt 保留。

当前已同步 16 个文件，由 `python -m integration.source_manifest` 的白名单定义，不包含 README、导出器、文档、测试夹具或密钥。远端 `.venv-p2` 使用既有 Python 3.12.3 和锁定依赖；P2 导入、规则载入、后端健康/ready/OpenAPI 的真实 HTTP 检查已通过。校验结果只保存在本地。

服务器当前已有源码和独立开发环境，正式容器尚未切换到 P2。后端应以该工作区为镜像构建源，发布和专用测试身份准备由现有有权限的操作者协同；不需要把 AI 开发源码复制到其他宿主机目录。

## 当前实现与协议

AI 工厂为 `p2.app:create_app`，应用版本 0.3.1，默认 `P2_ENGINE=rules`；P0/P1 入口未修改。部署仍使用容器内 8767。health 新增 `clarification_protocols` 和 `inventory_contracts`，容器探针校验版本、实际配置的引擎、只读标志、规则 SHA 和风险续接能力。

旧 P1 请求、上下文及草稿保持原结构。风险指代缺名称时生成 `protocol_version=p2-risk-selection-1` 的服务端上下文：包含原文、身份、时区、15 分钟有效期、revision、reminder_days，以及固定 QUERY_RISK 的 parsed；只允许补 `name`，同名多批次分别评估，不允许在答案里补写标签、温度或开封事实。续接不调用模型，重新读真实库存；超时保留已补名称和新 revision，原有效期不延长。

后端必须完整保存该上下文，并仅向 App 返回 `{revision,allowed_fields,expires_at}`。续接时从数据库恢复原始 context。若后端严格依赖 P1 的 Context/Intent/AgentResult 模型，需要增加对新上下文、QUERY_RISK、risks、evaluated_count 和扩展 facts 的支持；不能把它们静默删除。新协议见实际 AI OpenAPI。

2026-10-15 已读取正式服务器 v0.6 网关源码：其结果和上下文使用 JSON 存储、保留新增字段，name 属于澄清白名单，基础 P2 结果及名称续接不需要按原先假设重构网关。实际正向链路仍需专用测试身份和真实库存验证；自定义 reminder_days 尚未由业务消息转发，当前先使用默认 3。

P2 将库存工具的 401 映射为 `TOOL_UNAUTHENTICATED`、409 映射为 `TOOL_DATA_CONFLICT`，均不建议自动重试；403 拒绝家庭读取，404 表示批次或作用域不可访问，临时 HTTP/格式故障仍为 `TOOL_UNAVAILABLE`。上游原始错误消息不会转发给 App。P1 工具行为不变。

## 真实 HTTP 检查

在 agent 目录运行。远端连接通过现有 HTTPS 或 SSH 本地转发；不要将服务 token 放入参数、终端历史或报告。当前部署的 8000 仅回环可见，需要可用 SSH 登录后建立本地转发，或在服务器容器网络内运行工具。

```powershell
# 只检查健康、数据库就绪与业务 OpenAPI，不需要用户身份。
& 'D:\python\python3.13.5\python.exe' -m integration.backend_v06 --base-url http://127.0.0.1:18000 --output .cache/p2-integration/inspect.json

# 通过受保护的运行环境提供已有测试用户 USER_ACCESS_TOKEN 和真实测试家庭：
# MAGICVVU_USER_ACCESS_TOKEN、MAGICVVU_TEST_HOUSEHOLD_ID。
# 不使用 AI_SERVICE_TOKEN 或 BACKEND_TOOL_TOKEN 代替用户登录令牌。
& 'D:\python\python3.13.5\python.exe' -m integration.backend_v06 --base-url http://127.0.0.1:18000 --positive --output .cache/p2-integration/p1-http.json

# 后端已适配 P2 并实际部署后：
& 'D:\python\python3.13.5\python.exe' -m integration.backend_v06 --base-url http://127.0.0.1:18000 --positive --expect-p2 --output .cache/p2-integration/p2-http.json
```

正向检查需要专用测试家庭中已存在真实活动库存。工具会创建 AI 任务和“全部丢弃”的待确认草稿，用于核对草稿事实与持久化，但绝不调用确认、撤销、购物或库存写入接口。测试前后比较同一家庭库存快照；如果有其他客户端并发改库存会判为变化，需要在隔离测试环境复核。

检查包括：真实库存读取、同键相同结果、同键不同内容拒绝、GET 任务恢复、多批次必要时选择、草稿读取、P2 风险结果存储恢复、风险名称续接、前后库存一致、公开响应不含原始 context、风险批次版本对应事实。报告不保存原文、库存详情、家庭 ID、手机号、token 或原始异常，只保留检查结果、数量、版本及任务/草稿/trace 标识供后端定位。

HTTP 相同结果不单独证明供应商只调用一次；`provider_call_count_verified=false`。库存前后快照也不代替数据库写审计；`database_write_audit_verified=false`。这两项应由后端结合计数、事务和审计补充。跨家庭、过期及并发真实链路亦需专门测试身份与后端配合，不能由单个健康检查替代。

## 容器与发布材料

`agent/Dockerfile.p2` 使用已核对的 Python 3.12 基础镜像和阿里云 PyPI 地址，从独立 requirements.p2.runtime.txt 安装现有锁定依赖，显式复制 p0/p1/p2、规则、定价文件和客户端工具。Dockerfile.p2.dockerignore 排除环境、密钥、文档及测试数据；以 UID/GID 10002 运行，与原 P1 对齐。

`deploy/compose.p2.override.yaml` 必须与服务器现有 Compose 合并使用。它保留 agent 服务名和 8767 端口，仅覆盖 AI 镜像/构建、入口、P2_ENGINE 和探针。需要核对合并后的服务认证、BACKEND_BASE_URL、网络隔离、内存限制、只读根文件系统与缓存卷仍有效；旧 agent_cache 卷需允许 UID 10002 写入。用 `compose config --quiet` 验证，不能打印解析后的密钥。若服务器已有 user 设置，也需核对与新镜像的一致性。

构建 context 默认 `/home/magicvvu_ai/workspace/agent`，可由受信任操作者设置 MAGICVVU_AGENT_SOURCE_DIR；该覆盖模板保留在本地供后端审阅，不由 AI 同步到正式部署目录。

发布顺序：先确认网关可保存 P2 结果/上下文，再构建 AI 镜像、核查探针，最后在专用测试作用域跑真实 HTTP。后端开始输出扩展批次字段前，先切至兼容旧字段的 P2。回滚 P1 前先关闭扩展字段输出；保留旧镜像，不删除数据库/缓存卷。

```powershell
& 'D:\python\python3.13.5\python.exe' -m p2.export_contract
& 'D:\python\python3.13.5\python.exe' -m integration.package
```

打包工具保留为历史本地交付辅助，采用白名单输出至 `.cache/p2-integration/`。当前服务器协作改用代码按模块同步，不上传该包或说明文件；正式构建和切换仍需核对服务器基线，不能因源码已同步就声称已部署。
