# P2 路由与安全审计（离线草案）

## 依据与完整性

2026-10-21 通过SSH读取当前Backend镜像源码，不导入/启动应用。镜像为
`magicvvu/backend:p72-units-736c2299edda`，镜像ID见 `P2-runtime-audit.json`。
实际启动模块 `app.main:app`；Agent启动模块为 `conversation.app:create_app`。
源码原始SHA256及脱敏源码见运行审计JSON和 `runtime-sources/`。

解析 `main.py` 中实际注册的7个router，组合每个 `APIRouter(prefix=...)` 与具体decorator路径。
得到38个API操作，已与 **运行中的 `/openapi.json` 所含38个操作逐项比对，集合完全一致**；
不是只使用工作区源码或路由局部片段。运行schema只从服务器loopback读取，没有公开它。

以下是未来入口决策，不代表已经配置Nginx。`允许`仅表示可转交Backend，认证与数据权限仍由Backend决定。
仅有当前Android main代码调用证据的30个操作进入白名单；3个内部操作和5个其他操作不进入白名单。
依据来自本地 `frontend/.../data/CloudApi.kt`、`CloudStore.kt`、`AgentClient.kt`；本次只读交叉核对，未改Android。

## 完整API清单

超时列为拟定Nginx上游读取间隔超时，非业务保证；全部当前API为JSON，无已发现的SSE/WebSocket。
`AI`表示AI相关业务，确认执行/任务查询不等于调用外部模型。

| Method | 完整路径 | 认证 | 功能 | Android公网决策 | 内部 | AI | 读取超时/流式 | 部署源码 |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/v1/health` | 无会话认证 | Android写操作前版本/目标预检 | 允许 | 否 | 否 | 20s / JSON | [main:36](runtime-sources\backend\app\main.py#L36) |
| GET | `/api/v1/ready` | 无会话认证 | 主机数据库就绪 | 暂不开放/待确认 | 否 | 否 | 20s / JSON | [main:42](runtime-sources\backend\app\main.py#L42) |
| POST | `/api/v1/auth/register` | 无会话认证 | 未验证手机号注册（运行开关关闭） | 暂不开放/待确认 | 否 | 否 | 20s / JSON | [auth:33](runtime-sources\backend\app\routers\auth.py#L33) |
| POST | `/api/v1/auth/login` | 无会话认证 | 手机号密码登录并创建会话 | 允许 | 否 | 否 | 20s / JSON | [auth:57](runtime-sources\backend\app\routers\auth.py#L57) |
| GET | `/api/v1/users/me` | 会话Bearer + 活跃用户校验 | 当前用户 | 允许 | 否 | 否 | 20s / JSON | [auth:68](runtime-sources\backend\app\routers\auth.py#L68) |
| POST | `/api/v1/auth/logout` | 会话Bearer + 活跃用户校验 | 撤销当前会话 | 允许 | 否 | 否 | 20s / JSON | [auth:73](runtime-sources\backend\app\routers\auth.py#L73) |
| PATCH | `/api/v1/users/me` | 会话Bearer + 活跃用户校验 | 修改显示名称 | 允许 | 否 | 否 | 20s / JSON | [auth:84](runtime-sources\backend\app\routers\auth.py#L84) |
| PATCH | `/api/v1/households/{household_id}` | 会话Bearer + 活跃用户校验 | 家庭重命名，仅owner/admin | 允许 | 否 | 否 | 20s / JSON | [households:22](runtime-sources\backend\app\routers\households.py#L22) |
| POST | `/api/v1/households` | 会话Bearer + 活跃用户校验 | 创建家庭 | 允许 | 否 | 否 | 20s / JSON | [households:41](runtime-sources\backend\app\routers\households.py#L41) |
| GET | `/api/v1/households` | 会话Bearer + 活跃用户校验 | 列出本人家庭 | 允许 | 否 | 否 | 20s / JSON | [households:59](runtime-sources\backend\app\routers\households.py#L59) |
| GET | `/api/v1/households/{household_id}/members` | 会话Bearer + 活跃用户校验 | 家庭成员 | 允许 | 否 | 否 | 20s / JSON | [households:72](runtime-sources\backend\app\routers\households.py#L72) |
| POST | `/api/v1/households/{household_id}/invitations` | 会话Bearer + 活跃用户校验 | 创建单次邀请，仅owner/admin | 允许 | 否 | 否 | 20s / JSON | [households:91](runtime-sources\backend\app\routers\households.py#L91) |
| POST | `/api/v1/households/join` | 会话Bearer + 活跃用户校验 | 消费有效邀请码加入家庭 | 允许 | 否 | 否 | 20s / JSON | [households:110](runtime-sources\backend\app\routers\households.py#L110) |
| GET | `/internal/v1/inventory/search` | 服务Bearer + X-User/Household + 活跃用户/家庭校验 | Agent按家庭搜索库存 | 禁止 | 是 | 是 | 30s / JSON | [ai_inventory:56](runtime-sources\backend\app\routers\ai_inventory.py#L56) |
| GET | `/internal/v1/inventory/batches/{batch_id}` | 服务Bearer + X-User/Household + 活跃用户/家庭校验 | Agent读取家庭批次 | 禁止 | 是 | 是 | 30s / JSON | [ai_inventory:80](runtime-sources\backend\app\routers\ai_inventory.py#L80) |
| POST | `/api/v1/agent/messages` | 会话Bearer + 活跃用户校验 | AI消息及持久化任务 | 允许 | 否 | 是 | 30s / JSON | [agent_gateway:216](runtime-sources\backend\app\routers\agent_gateway.py#L216) |
| POST | `/api/v1/agent/clarifications/{task_id}` | 会话Bearer + 活跃用户校验 | AI补充信息 | 允许 | 否 | 是 | 30s / JSON | [agent_gateway:260](runtime-sources\backend\app\routers\agent_gateway.py#L260) |
| GET | `/api/v1/agent/tasks/{task_id}` | 会话Bearer + 活跃用户校验 | 恢复本人AI任务 | 允许 | 否 | 是 | 30s / JSON | [agent_gateway:306](runtime-sources\backend\app\routers\agent_gateway.py#L306) |
| GET | `/api/v1/drafts/{draft_id}` | 会话Bearer + 活跃用户校验 | 读取本人草稿 | 允许 | 否 | 是 | 30s / JSON | [agent_gateway:312](runtime-sources\backend\app\routers\agent_gateway.py#L312) |
| GET | `/api/v1/households/{household_id}/shopping-list` | 会话Bearer + 活跃用户校验 | 采购清单元信息 | 暂不开放/待确认 | 否 | 否 | 20s / JSON | [shopping:52](runtime-sources\backend\app\routers\shopping.py#L52) |
| GET | `/api/v1/households/{household_id}/shopping-list/items` | 会话Bearer + 活跃用户校验 | 采购条目分页 | 允许 | 否 | 否 | 20s / JSON | [shopping:59](runtime-sources\backend\app\routers\shopping.py#L59) |
| POST | `/api/v1/households/{household_id}/shopping-list/items` | 会话Bearer + 活跃用户校验 | 新增采购条目 | 允许 | 否 | 否 | 20s / JSON | [shopping:79](runtime-sources\backend\app\routers\shopping.py#L79) |
| PATCH | `/api/v1/households/{household_id}/shopping-list/items/{item_id}` | 会话Bearer + 活跃用户校验 | 修改待采购条目 | 允许 | 否 | 否 | 20s / JSON | [shopping:113](runtime-sources\backend\app\routers\shopping.py#L113) |
| DELETE | `/api/v1/households/{household_id}/shopping-list/items/{item_id}` | 会话Bearer + 活跃用户校验 | 删除待采购条目 | 允许 | 否 | 否 | 20s / JSON | [shopping:128](runtime-sources\backend\app\routers\shopping.py#L128) |
| POST | `/api/v1/households/{household_id}/shopping-list/items/{item_id}/purchase` | 会话Bearer + 活跃用户校验 | 原子购买入库 | 允许 | 否 | 否 | 20s / JSON | [shopping:140](runtime-sources\backend\app\routers\shopping.py#L140) |
| GET | `/api/v1/households/{household_id}/inventory-items` | 会话Bearer + 活跃用户校验 | 家庭库存列表 | 允许 | 否 | 否 | 20s / JSON | [inventory:56](runtime-sources\backend\app\routers\inventory.py#L56) |
| POST | `/api/v1/households/{household_id}/inventory-items` | 会话Bearer + 活跃用户校验 | 添加库存 | 允许 | 否 | 否 | 20s / JSON | [inventory:67](runtime-sources\backend\app\routers\inventory.py#L67) |
| PATCH | `/api/v1/households/{household_id}/inventory-items/{item_id}` | 会话Bearer + 活跃用户校验 | 编辑库存 | 允许 | 否 | 否 | 20s / JSON | [inventory:127](runtime-sources\backend\app\routers\inventory.py#L127) |
| POST | `/api/v1/households/{household_id}/inventory-items/{item_id}/adjustments` | 会话Bearer + 活跃用户校验 | 调整库存数量 | 允许 | 否 | 否 | 20s / JSON | [inventory:136](runtime-sources\backend\app\routers\inventory.py#L136) |
| DELETE | `/api/v1/households/{household_id}/inventory-items/{item_id}` | 会话Bearer + 活跃用户校验 | 软删除库存 | 允许 | 否 | 否 | 20s / JSON | [inventory:145](runtime-sources\backend\app\routers\inventory.py#L145) |
| GET | `/api/v1/agent/execution-capabilities` | 会话Bearer + 活跃用户校验 | Android写操作前能力预检 | 允许 | 否 | 是 | 30s / JSON | [draft_execution:19](runtime-sources\backend\app\routers\draft_execution.py#L19) |
| POST | `/api/v1/agent/reference-messages` | 会话Bearer + 活跃用户校验 | 保留接口，当前固定503 | 暂不开放/待确认 | 否 | 是 | 30s / JSON | [draft_execution:30](runtime-sources\backend\app\routers\draft_execution.py#L30) |
| GET | `/api/v1/drafts/{draft_id}/execution` | 会话Bearer + 活跃用户校验 | 草稿执行状态 | 允许 | 否 | 是 | 30s / JSON | [draft_execution:36](runtime-sources\backend\app\routers\draft_execution.py#L36) |
| POST | `/api/v1/drafts/{draft_id}/commit` | 会话Bearer + 活跃用户校验 | 按版本确认执行草稿 | 允许 | 否 | 是 | 30s / JSON | [draft_execution:41](runtime-sources\backend\app\routers\draft_execution.py#L41) |
| POST | `/api/v1/drafts/{draft_id}/cancel` | 会话Bearer + 活跃用户校验 | 取消草稿 | 允许 | 否 | 是 | 30s / JSON | [draft_execution:63](runtime-sources\backend\app\routers\draft_execution.py#L63) |
| GET | `/api/v1/operations/{operation_id}` | 会话Bearer + 活跃用户校验 | 本人操作回执/恢复 | 允许 | 否 | 是 | 30s / JSON | [draft_execution:75](runtime-sources\backend\app\routers\draft_execution.py#L75) |
| GET | `/internal/v1/operations/{operation_id}` | 服务Bearer + X-User/Household + 活跃用户/家庭校验 | Agent按用户/家庭读取内部回执 | 禁止 | 是 | 是 | 30s / JSON | [draft_execution:80](runtime-sources\backend\app\routers\draft_execution.py#L80) |
| GET | `/api/v1/households/{household_id}/consumption-events` | 会话Bearer + 活跃用户校验 | 家庭消耗事件，当前仅测试代码调用 | 暂不开放/待确认 | 否 | 是 | 30s / JSON | [draft_execution:96](runtime-sources\backend\app\routers\draft_execution.py#L96) |

## 框架默认路由与未知路由

当前部署的 `FastAPI(...)` 没有关闭默认文档。只读GET实测 `/docs`、`/redoc`、
`/docs/oauth2-redirect`、`/openapi.json` 均200。环境里有没有docs开关不能替代当前代码行为。

| 路径 | Method | 认证 | 用途 | 公网策略 |
|---|---|---|---|---|
| `/openapi.json` | GET/HEAD（FastAPI默认路由） | 无 | schema | 禁止 |
| `/docs` | GET/HEAD | 无 | Swagger UI | 禁止，含子路径 |
| `/docs/oauth2-redirect` | GET/HEAD | 无 | 文档OAuth跳转 | 禁止 |
| `/redoc` | GET/HEAD | 无 | ReDoc | 禁止，含子路径 |
| `/debug`、`/metrics`、`/admin`及子路径 | 未发现已注册业务路由 | 不推断 | 运维/调试保留空间 | 一律禁止 |
| `/internal`、`/internal/`及子路径 | 包含上述3个GET | 服务凭据 | Docker内网工具 | 一律禁止 |
| 所有未列出的路径/方法 | 任意 | 不推断 | 包括未来新增路由 | 默认404，不转发 |

HEAD/OPTIONS没有为业务API另行开放。当前原生客户端没有浏览器CORS预检依赖。
白名单使用规范UUID路径，客户端现有UUID均是标准带连字符形式；尾斜线、非规范UUID未开放，
不会自动扩大到全部 `/api/v1/`。Query不参与路径白名单，仍原样交给Backend验证，日志不记录。

## 认证和数据隔离

- 运行版本使用Argon2密码哈希、随机opaque Bearer token、服务端保存token SHA256，默认12小时到期；并非JWT。
- `get_identity` 校验会话存在、未撤销、未到期及用户active，缺凭据返回401；本机 `GET /api/v1/users/me` 实测401。
- 家庭库存/采购依赖成员关系且按家庭过滤。同家庭成员按现有共享规则访问库存，不能将这误述为同家庭内也完全按创建者隔离。
- AI任务/草稿/操作回执校验当前用户及家庭成员身份；写入保持版本校验和原有幂等语义。
- 家庭rename/invitation中的owner/admin属于家庭业务角色，不是宿主机管理接口，App确有调用，保留Backend角色校验。
- 内部 `_authorize` 校验独立 `BACKEND_TOOL_TOKEN`，并校验可信X-User/Household及活跃家庭成员关系；Agent的 `AI_SERVICE_TOKEN` 也已配置（只记录存在性）。
- Nginx不创建身份、不验证/重写Bearer；覆盖外部可伪造的Forwarded头并清空内部身份头。

## 待确认和不可自动扩大的范围

1. **注册**：App有注册入口，但服务器 `AUTH_ALLOW_UNVERIFIED_SIGNUP=false`，运行代码明确警告不适合公网开放注册。
   草案拒绝注册；这意味着新用户注册流程不可用，已有测试账号登录可用。不得宣称所有App功能无条件兼容。
   若需要手机注册，要另行确认防滥用/身份验证和开放范围，不能仅为通过验收打开注册开关。
2. **ready**：主机检查继续从loopback访问，App只需要health，不公开数据库就绪信息。
3. **reference-messages**：保留协议当前固定503，当前AgentClient未调用，拒绝；不因AI相关就公开。
4. **shopping-list元信息**：当前main客户端只取 `/shopping-list/items`，元信息操作暂不开放；若真实安装包依赖需提供对应源码/调用证据再审核。
5. **consumption-events**：仅发现instrumentation测试调用；业务main客户端调用未确认，暂不开放。后续确认要保留测试能力时单独加精确GET。

## AI完整链路、超时和中断

Android `CloudApi`（连接5s、读取20s）→ Backend `agent_gateway._call_ai`
（连接3s，其余httpx阶段13s、无重定向、trust_env=false）→ Docker `agent:8767` →
`conversation.app`/`p3.app` 创建 `conversation.Manager` → 继承 `v1.Manager/Operation`，
整个Agent operation受 `asyncio.timeout(10)` 约束。DeepSeek payload `stream:false`，
模型请求也有10s墙钟约束且无SDK自动重试；内部库存工具HTTP读取5s，位于operation总预算内。
不能把每个5s/10s/13s简单相加，也不能把httpx阶段超时当成整个Backend请求绝对上限。

Agent通过 `http://backend:8000/internal/...`（具体配置目的主机只读核验见运行证据/固定网关设计）回读，
不经公网Nginx。公网阻断 `/internal/` 保留内网调用能力。当前Backend没有注册
`/internal/v1/planning/context`，而Agent RemoteReader包含该可选依赖；代码定义了
`PLANNING_CONTEXT_UNAVAILABLE`降级。此既有能力缺口不在P2修复，不声称完整规划功能已通过实测。

草案普通API读取20s、AI相关30s、连接3s、发送15s，给数据库操作/序列化留余量。
Android读取仍为20s，因此手机可能先于Nginx超时；P4需按专门测试构建审查，P2不修改。
`proxy_read_timeout`是两次读取之间的空闲超时，不是全请求硬截止。
当前没有流式输出：保留JSON请求缓冲，关闭响应缓冲和响应磁盘临时文件；未来增加流式协议必须重新审计。
请求体上限64KiB，与当前1000字符AI输入、1500字节补充字段及小型库存JSON相容；当前没有音频/图片上传API，照片由客户端本地保存。

客户端断开时 `proxy_ignore_client_abort off` 让Nginx关闭上游连接，但ASGI同步/异步处理或已提交事务不保证被撤销。
`proxy_next_upstream off` 禁止代理自动重放写请求。必须用既有request_id/operation_id和回执恢复，不能以超时推断“写入未发生”。

## 安全结论

当前运行登录函数未调用LoginGuard，也无已确认的账号级公网防爆破措施，不能从工作区较新代码推断线上已有。
草案补充每源IP登录5次/分钟、全站登录10次/分钟（均突发3）、API每源10次/秒（突发30）、总并发16，返回429。
这只是单手机低并发场景的入口缓解，分布式攻击、持有其他有效账号、应用级审计与实际设备绑定仍未解决。
P2只完成配置和静态检查；Nginx语法、转发、限流和日志行为均需P3在实际安装版本验证。
