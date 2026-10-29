# P8.5 后端协议适配：第一步

2026-10-29，Asia/Shanghai。本目录交付本地代码与契约，尚未部署或修改服务器开关。

## 已实现

- 按配置选择新消息协议，分别调用旧 `/agent/dialogue/*` 和新 `/agent/dialogue/p85/*`。
- 后端独立的 P8.5 请求、理解计划、记忆使用、增量、核对和表达 DTO；拒绝未知字段、非法修订及计数。
- 理解返回的 `context_revision` 与本请求上下文核对，原值作为 `plan_context_revision` 传给 resolve，不用手机修订号猜填。
- P8.5 保存独立 `dialogue_v2`，保留完整理解计划、记忆元信息及核对后的增量。P8.4 继续使用 `dialogue_v1`。
- 增量核对用户/家庭、会话、上下文修订、原请求、原文、原文 SHA256 和片段时间。允许拒绝/冲突响应不带增量。
- `expression_required=false` 时跳过表达；正常表达返回次数接受0或1，未知/失败尝试保守计一次，保留已保存核对结果及备用回复，不付费重试。
- 公开 Response/Recovery 允许 P8.4/P8.5 元数据，合并记忆截断标志，不公开原始 memory/delta。
- 恢复按请求保存协议，不受当前新消息开关影响；已保存理解计划可显示 prepared，恢复零模型。旧单阶段 prepared 请求不会因开启新协议而换路线。
- 当前任务计划传给共享类型时排除 memory_id，保留 half/all 等原语义。

## 明确范围

这一步不构建完整历史 archive，不声称十轮外历史检索已经接通。新协议请求省略 archive，AI 按无 archive 模式处理；后端拒绝这类请求响应中的任意历史 memory_id 选择或 archive_available=true。增量保存在内部阶段记录，还没有作为可检索历史供下一轮使用。

下一步再实现真实历史读取、completed_at、增量的最终会话合并及历史引用白名单。这一阶段无需新表或迁移，不改变库存确认事务，不修改 Android。

实际启用前应完成下一步和隔离环境联合验收，再设置 `AI_CONVERSATION_DIALOGUE_PROTOCOL=p85-dialogue-1`。已有 P8.4 请求必须始终按其保存协议恢复，不能通过全局替换 KEY 升级。

## 验证与契约

最终相关回归：**118通过、2跳过、0失败**（92.99秒），见 regression.xml。未运行生产 PostgreSQL、真机或付费模型验收。

`test_p85_dialogue.py` 使用真实后端鉴权/ASGI → 真实 P8.5 AI 路由与流程 → 隔离 SQLite 任务/草稿记录；模型为确定性测试引擎，不访问付费模型或生产数据。

覆盖草稿改口、阶段/增量落库、讨论跳过表达、表达0/1计数、非法计数降级、增量各维伪造、修订转发、可选增量、未知字段、表达超时、重复请求及切换/关闭开关后的双协议恢复。相关旧会话、P8.4、P8.3规划与 App Key 用例一并回归。最终结果见 regression.xml；focused.xml 为早期27项检查记录。

契约导出：在已安装后端开发依赖的环境中运行 `python tools/p85_adapter_export_contracts.py`。输出本目录 contracts/，不连接生产数据库，不覆盖历史 P8.4/P8.5 快照。当前公开 OpenAPI 与 Response/Recovery 做精确比较；旧 P8.4 Response 额外检查仅增加协议枚举后保持兼容。旧全量快照缺少此前已有的商品归组接口，因此不再将其当当前全量契约。

本地 Windows 使用应用自带 Python 3.12、后端锁定依赖及 Pydantic 2.12.5，测试依赖安装在项目 `.cache/p85-backend-deps`。测试进程需要允许本机异步事件循环；没有因此修改业务网络或服务配置。
