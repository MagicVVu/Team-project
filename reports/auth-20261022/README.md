# 后端注册与登录检查及启用记录

日期：2026-10-22（北京时间）。结果：已连接服务器，确认现有能力，开启团队内测自助注册，实际 TLS 接口验收通过。

## 现有后端功能

实际服务为 FastAPI `app.main:app`，版本 `0.9.0`。后端、PostgreSQL、Agent 三个容器均健康。通过服务器运行时路由确认已有以下接口；本次完整执行的是认证链路，其他业务仅检查接口存在。

| 模块 | 现有能力 |
|---|---|
| 用户认证 | 手机号和密码注册、登录、读取/修改个人资料、退出及会话撤销 |
| 家庭 | 创建、读取、修改家庭，成员列表，生成邀请码、加入家庭 |
| 库存 | 家庭库存分页读取、新建、修改、数量调整、删除 |
| 采购 | 家庭共享清单，添加/修改/删除采购项，购买并入库 |
| AI | 消息、澄清、任务、对象引用，草稿读取/确认/取消，执行结果与操作查询 |
| 系统 | 健康检查、内部数据库就绪检查、内部库存与操作查询 |

## 本次改动

认证接口原本已经实现。阻止 App 自助注册的直接原因是服务器的 `AUTH_ALLOW_UNVERIFIED_SIGNUP=false`，有效注册请求会返回 403。

本次仅将服务器 `/srv/magicvvu/magicvvu-starter/deploy/compose.yaml` 中 backend 的该变量设为字符串 `true`，并重建 backend，使配置持久生效。已验证只改变该配置字段；未升级业务镜像、迁移数据库或修改 `.env`。Agent 与 PostgreSQL 容器 ID 保持一致，数据卷继续使用原有配置。

变更前配置仅备份在服务器 root 私有目录：`/etc/magicvvu/ip-direct/auth-before-20261022T061633314035Z/compose.yaml`，权限 0600。未导出服务器源码、配置内容、密码或令牌。

新增工具：

- `deploy/ip-direct/signup.py`：默认只读检查；`--enable`/`--disable` 切换注册开关，备份原配置，检查失败恢复配置，只重建 backend。
- `tools/auth_smoke.py`：现有部署镜像的无网络一次性 SQLite 验证，并挂载实际公网入口脚本验证限流和路径隔离。
- `tools/auth_live_verify.py`：真实 TLS 注册/登录/退出验收，凭据仅保存在服务器内存，最后精确清理本次唯一临时用户及会话。

## 接口与 App 接入

内测服务地址：`https://8.134.172.165:8000`。使用现有「Mewstow 内测」internal 构建，其证书配置已经信任项目私有 CA。当前源码的注册页面已依次调用注册、登录、个人资料及家庭列表，无需为本次后端配置变更重建 APK。本次没有在设备上重新执行 UI 注册流程。

| 方法 | 路径 | 请求/结果 |
|---|---|---|
| POST | `/api/v1/auth/register` | JSON 包含 `phone`、`password`、`display_name`；成功 201，返回用户资料 |
| POST | `/api/v1/auth/login` | JSON 包含 `phone`、`password`；成功 200，返回 `access_token`、`token_type=bearer`、`expires_in=43200` |
| GET | `/api/v1/users/me` | 带 Bearer Token；返回当前用户资料 |
| PATCH | `/api/v1/users/me` | 带 Bearer Token；JSON 包含 `display_name` |
| POST | `/api/v1/auth/logout` | 带 Bearer Token；成功 200，原 Token 后续请求返回 401 |

注册规则：接受中国大陆 11 位手机号并规范化为 `+86…`，也接受 E.164 国际格式；密码 10–128 字符；后端昵称 1–100 字符，去除首尾空白，不接受全空白。现有 App 昵称表单限制为 1–20 字符。重复手机号返回 409，无效字段返回 422，手机号或密码错误返回 401。

密码使用 Argon2id 哈希；会话为 12 小时的随机 Bearer Token，数据库只保存其 SHA-256 摘要，支持过期与退出撤销。新注册用户尚无家庭，之后由用户选择创建或加入家庭；不会自动取得其他家庭的数据。

本次仍是**来源白名单内的团队内测注册**。手机号码尚未进行短信所有权验证，`phone_verified=false`；未新增短信验证码、密码找回或号码所有权能力。现有公网入口按真实 TCP 来源限制全部 `/api/v1/auth/` 请求合计 8 次/分钟（含注册、登录、退出），不信任伪造转发头。现有请求体限制 64 KiB、TLS 和 `/32` 白名单继续生效。不要将本记录解释为面向全网开放注册。

## 验证结果

| 验证 | 结果 | 证据 |
|---|---|---|
| 现有镜像与实际公网入口脚本，隔离 SQLite | 41 项通过；无网络，无业务数据库/数据卷 | `isolated-verification.json` |
| 部署检查 | 9 项通过，注册开关已生效，镜像/Agent/数据库/密钥文件保持不变 | `deployment-verification.json` |
| 实际后端 TLS + PostgreSQL 认证闭环 | 19 项通过，含临时账号及会话清理 | `live-verification.json` |
| 当前电脑至公网地址 | 8 项状态检查通过；另确认项目 CA 未被系统全局信任 | `public-verification.json` |

隔离验证覆盖：关闭注册、字段校验、手机号规范化/去重、Argon2id、令牌摘要、正确/错误/不存在/禁用账号登录、个人资料、家庭隔离、退出撤销、令牌过期、认证限流与伪造转发头、请求体上限、管理及内部路径隔离。

真实验收使用同一个已发布的 TLS listener，校验项目 CA 和 `8.134.172.165` 证书身份。由于云服务器公网 IP 无法回环访问自身，服务器内的完整认证验收通过回环连接已发布端口 8000；当前电脑另对公网 IP 完成只读验证。临时账号、密码和令牌没有离开服务器，测试未创建家庭、库存或采购数据。设备 UI 注册/登录尚未重新验收。

## 操作与回退

在本仓库目录使用已有 `magicvvu` SSH 配置执行，默认命令不修改服务器：

```powershell
Get-Content -Raw deploy/ip-direct/signup.py | ssh magicvvu "sudo -n python3 -"
```

需要关闭自助注册时：

```powershell
Get-Content -Raw deploy/ip-direct/signup.py | ssh magicvvu "sudo -n python3 - --disable"
```

这会持久关闭新注册，已有账号仍可登录。需要再次开启时使用 `--enable`。两种操作均检查现有 TLS、白名单和后端健康，只调整 backend 注册开关。

服务器实际认证源码与本地源码存在版本差异（例如部署镜像没有本地较新的 `login_guard.py`）；本次没有把本地后端整体覆盖到服务器。已单独验证部署入口的注册和登录限流。后续升级业务代码时应按完整发布流程处理差异。
