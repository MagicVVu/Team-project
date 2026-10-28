# 团队 API 共享密钥接入（2026-10-28）

**最新状态（2026-10-28 22:21，北京时间）：用户已开放阿里云 TCP 8000；本机旧白名单已备份并改为 `0.0.0.0/0`，公网 HTTPS 验收通过。以下早先的“尚未开放”描述仅记录部署当时状态。**

## 三种独立机制

| 层次 | 输入 | 判断 | 拒绝结果 |
| --- | --- | --- | --- |
| App 共享密钥 | `X-MagicVVu-App-Key` | 是否持有团队分发的共享凭据 | 403 / `APP_KEY_INVALID` |
| 用户身份认证 | `Authorization: Bearer <用户登录令牌>` | 当前用户是谁、会话是否有效 | 401 |
| 业务权限 | 当前用户、家庭成员关系与角色 | 是否有权读取或修改目标数据 | 沿用现有 403/404 等 |

共享密钥只能证明持有凭据，不能证明来自官方 App，也不赋予用户身份或家庭权限。按本次明确约定，团队密钥写入随源码分发的 `frontend/app/src/main/java/com/example/teamapp/data/TeamApiAccess.kt`，所有团队成员同步源码即可构建。用户密码、用户会话令牌、数据库密码与 AI 内部令牌没有写入仓库。

## 实现

- Android `CloudApi.request` 统一添加共享请求头，包括登录、注册、健康探测和 Agent 请求；原 Bearer 头继续独立发送。禁用自动跳转和原 HTTPS 证书策略保留。
- FastAPI 全局 `AppKeyMiddleware` 在请求体处理和路由之前校验 `/api/v1` 与所有 `/api/v1/*` 业务请求，覆盖新路由、所有 HTTP 方法以及尚未登录的注册/登录。使用恒定时间比较，缺失、错误、重复请求头统一拒绝。
- 后端通过环境变量 `MAGICVVU_APP_API_KEY` 配置密钥，没有配置时业务请求关闭并返回 503 / `APP_KEY_NOT_CONFIGURED`。本地及隔离环境也须设置为 Android 源码中的同一密钥。
- `deploy/ip-direct/serve.py` 的公网 HTTPS 入口额外在读取请求体前验证密钥，覆盖 `/health` 与 `/api/v1/health`。私有监听器上的精确 health/ready 路径保留用于 Docker 与内部 AI 健康检查。该例外仅适用于探测接口，不适用于任何业务接口。
- `/internal/*` 继续沿用独立服务令牌；公网仍拒绝 internal、ready、docs 等原有隐藏路径。共享密钥不代替内部服务令牌。
- Android 将共享密钥错误显示为“同步最新 App / 联系维护者”，与登录失效和家庭权限错误区分。

## 验证

本地后端与公网入口回归：467 passed / 39 skipped；额外入口复核 5 passed。跳过项为原有需外部环境或显式开关的用例。包含缺失/错误/重复密钥、缺失服务器配置、有效密钥无登录、跨家庭访问、普通成员与管理员操作差异，以及现有注册、登录、退出和业务回归。

Android `:app:testDebugUnitTest :app:assembleDebug` 通过。产物为 `frontend/app/build/outputs/apk/debug/app-debug.apk`。未进行手机实机验收。

部署只从当前线上镜像覆盖两个访问校验相关 Python 文件，并更新原 TLS 包装器；不执行数据库迁移，不变更 agent/db、不变更端口和防火墙。脚本与原 Compose、包装器备份保存在服务器发布目录，切换验证失败时自动恢复。

## 后续开放网络

目前没有修改公网放行范围。服务器除了阿里云安全组，还有 `magicvvu-direct-firewall.service` 管理的本机 `MAGICVVU-TLS` 来源限制，来源列表位于 `/etc/magicvvu/ip-direct/allowed-sources.txt`。后续允许不同网络访问时，需要同时调整这两处；只开放安全组不足以解除本机限制。现有持久化脚本会在启动时重新应用来源列表，需要同步处理其配置。

开放前安装本次新版 App；旧 App 不携带共享头，会被拒绝。网络超时仍应区分安全组、防火墙、证书和连通性问题；应用层的 403 则说明请求已经到达服务器。

## 密钥更换

生成新的随机团队密钥，同时修改 `TeamApiAccess.kt` 和服务器 Compose 的 backend 环境变量 `MAGICVVU_APP_API_KEY`，仅重建 backend，重新分发 App。本版只接受一个有效密钥，切换后旧 App 即失效。修改代码后需要重新构建，单独同步仓库不会更新手机中已经安装的 APK。

## 运维复核

`deploy/ip-direct/verify.py --ca <团队 CA 文件> --output <报告路径>` 默认从仓库的 Android 密钥文件读取共享密钥，也可通过 `MAGICVVU_APP_API_KEY` 提供。它验证 HTTPS 信任、正确密钥、缺失/错误密钥、身份认证与内部路由隔离，不调用付费模型或写业务数据。

## 正式部署结果

2026-10-28 22:04（北京时间）已部署 `magicvvu/backend:app-key-20261028t140429z`。完整脱敏验收见 [verification.json](verification.json)。服务器私有备份目录：`/srv/magicvvu/releases/app-key-20261028T140429Z`，内含原 Compose、原 TLS 包装器、原 main.py 和构建源码。现有 TLS 证书指纹保持不变。

切换后公网 HTTPS 监听器（经服务器回环访问并验证团队 CA）确认：缺失/错误密钥返回 403；正确密钥的健康请求返回 200；正确密钥但无用户令牌返回 401；登录/注册持有密钥后进入原参数校验（422），没有测试账号或业务数据写入。内部路径继续返回 404。agent/db 容器 ID、现有环境变量和 `.env` 文件、实际来源过滤规则与主机入站策略保持不变。

从开发电脑对公网地址做带密钥的 HTTPS 请求仍出现 URLError，不能据此声称不同网络已经可达；本次没有调整网络放行范围。

部署过程先修复了本地镜像引用和候选容器双网络配置。第一次正式切换的应用层验收成功，但最后的全量 iptables 文本比较因动态状态差异误报并自动回退；改为比较实际 raw 来源过滤规则和 INPUT 策略后重新切换并全部通过。数据库未执行迁移或恢复。

需要回退时：先核对本次发布目录和当前容器，恢复该目录的 `compose-before.yaml` 到原部署 Compose、`serve-before.py` 到 `/srv/magicvvu/ip-direct/serve.py`，仅重建 backend；数据库和卷保持原状。回退意味着旧 App 可继续访问，持有共享密钥的要求也会被撤销。

## 22:21 本机来源配置与公网验收更新

用户已明确授权在阿里云放开 TCP 8000 后调整本机来源白名单。本次实际检查发现，`magicvvu-direct-firewall.service` 早已被 mask 且未运行（mask 链接时间为 2026-10-24）；nft 和 legacy 两套 raw 表均无 `MAGICVVU-TLS` 链或跳转，INPUT 默认 ACCEPT，UFW inactive。因此此前仅从旧来源文件推断本机仍有白名单阻拦，不代表本次检查到的实时状态。变更前从开发电脑进行完整公网检查也已通过。

为避免日后重新启用旧防火墙脚本时恢复固定 IP 限制，本次将 `/etc/magicvvu/ip-direct/allowed-sources.txt` 持久化为 `0.0.0.0/0`，旧文件及防火墙状态备份在 `/etc/magicvvu/ip-direct/public-access-before-20261028T142114Z`。白名单服务继续保持 masked/inactive，没有恢复该旧服务；原活动防火墙规则、其他端口、容器 ID 与健康状态保持不变。

变更后从开发电脑直连 `https://8.134.172.165:8000`，使用团队 CA 验证 HTTPS，12 项接口检查全部通过：正确共享密钥健康接口 200；缺失/错误共享密钥 403；共享密钥正确但缺少用户登录令牌 401；internal、ready、docs、openapi 公网路径仍为 404。系统默认证书信任库仍拒绝项目私有 CA，证明没有关闭 TLS 验证。完整结果见 [public-network-verification.json](public-network-verification.json)。本次未向业务库写入测试数据或调用模型。

现在使用内置共享密钥和团队测试 CA 的新版 debug App 可按该公网地址连接；用户仍须正常登录，家庭数据隔离与业务权限继续独立校验。该地址当前使用 IPv4，本次没有配置 IPv6 监听。
