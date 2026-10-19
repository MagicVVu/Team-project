# MagicVVu Tailscale HTTPS 最终诊断与验收报告

检查时间：2026-10-19 22:28–22:32，Asia/Shanghai（UTC+08:00）。

## 1. 结论

**当前公网 HTTPS 已验证可用；整体验收状态：NOT PASS，待 DNS 稳定性和登录安全问题处理。**

证书签发后的访问已经恢复。此次通过 SSH 检查服务器，同时从本地 Windows 的以太网公网出口访问公共 Funnel 入口。两个公网 IPv4 地址均返回 HTTP 200，默认可信证书校验通过，未使用 `-k` 或任何跳过证书校验的设置。

公网连通性通过不代表长期稳定性或生产安全性通过。本次没有更改服务器配置、业务代码、认证逻辑、数据库、Agent、容器、SSH、防火墙或安全组，也没有重启服务或服务器。

## 2. 验收表

| 项目 | 状态 | 实时证据 / 限制 |
|---|---|---|
| 本地后端健康检查 | 已验证成功 | `http://127.0.0.1:8000/api/v1/health` HTTP 200 |
| tailscaled | 已验证成功 | active、enabled，版本 1.104.1 |
| Funnel 转发 | 已验证成功 | HTTPS 443，根路径代理 `http://127.0.0.1:8000`，AllowFunnel=true |
| Tailnet HTTPS | 已验证成功 | 服务器解析为 100.123.235.8，HTTP 200，verify=0 |
| 公网 DNS | 已验证成功 | 公共 DNS 1.1.1.1 返回公网 A/AAAA 记录 |
| 真正公网 HTTPS | 已验证成功 | 非 Tailscale 网络接口，经公网 IPv4 .153 和 .217 分别 HTTP 200 |
| 证书及 TLS | 已验证成功 | 公网系统默认验证通过，TLS 1.3，域名匹配 |
| 三个主容器 | 已验证成功 | backend、agent、db 全部 healthy，RestartCount=0 |
| 操作期间后端连续性 | 已验证成功（检查范围内） | 前后健康检查 200，启动时间未变，未执行中断操作；未部署连续探测 |
| Funnel 后台持久配置 | 已验证成功 | status JSON 的顶层配置及磁盘 `_serve/3595` 状态键存在 |
| 重启后 HTTPS 端到端恢复 | 尚待验证 / 存在风险 | 服务自启及容器恢复策略具备；未重启实测，临时 DNS 会丢失 |
| DNS 重启持久性 | 存在风险 | eth0 仅运行时 1.1.1.1；Netplan 仍为 DHCP DNS |
| 自动续期 | 机制明确，尚待实际续期 | tailscaled 管理证书；DNS/ACME 可达性仍是续期前提 |
| 公网认证与权限 | 部分已验证成功 | 无身份拒绝测试通过，运行源码存在家庭和资源归属校验 |
| 登录防滥用 | 存在风险，阻断正式上线建议 | 未发现应用限流、失败锁定或验证码机制 |
| 手机移动网络 / 公网 IPv6 | 尚待验证 | 不是本次公网 IPv4 成功结论的前提，但仍建议补充移动端验收 |

## 3. 故障原因与日志判断

历史日志明确记录了 ACME 请求失败于 DNS：

```text
lookup acme-v02.api.letsencrypt.org on 127.0.0.53:53: ... i/o timeout
acme.GetReg: context deadline exceeded
22:19:53 registered ACME account.
22:20:28 requesting cert...
22:20:29 got cert
22:20:29 health(warnable=tls-cert-pending): ok
```

可以确认的故障链是：系统解析 ACME 域名超时 → 无法及时取得证书 → HTTPS 握手等待并超时。用户此前临时切换 DNS 后，ACME 申请成功；当前正常证书校验和公网请求证明证书已经实际加载。

**底层 DNS 不通的原因尚未定位到具体设备或策略。** 阿里云两个默认 DNS 当前仍超时；路由查询显示 100.100.2.136 经 eth0 的 VPC 网关，而非直接进入 tailscale0。未据此断言阿里云 DNS 服务自身故障；主机网络过滤、云侧出站策略或 VPC 路径仍未排除。本次没有修改或完整审计防火墙、安全组。

22:20:29/22:20:33 的 `TLS handshake error: EOF` 与客户端提前断开相符。当前成功的握手和请求说明这几条记录不能作为持续证书故障的证据，日志本身也不能证明每次断开的具体原因。22:20:34 后抽查日志没有持续 ACME 错误；仍有到 58000 端口的 Tailnet Drop 日志，未证明与当前正常的 Funnel HTTPS 有因果关系。

## 4. 公网、Tailnet 与证书证据

健康响应：

```json
{"status":"ok","service":"magicvvu-backend","version":"0.9.0","isolated_test":false}
```

注意：运行后端自报版本为 0.9.0，不能沿用背景说明中的 v0.8 镜像假设。

公共 DNS 记录（TTL 300，记录可变化）：

```text
A     103.84.155.153
A     103.84.155.217
AAAA  2403:2500:400:20::25a
AAAA  2403:2500:400:20::e8e
```

公网测试使用 Windows 系统 curl，`--noproxy '*'` 禁用显式代理，`--resolve` 分别固定上述两个公共 A 记录，同时保留原域名作为 SNI 和证书验证名称。两次均为 `http=200 verify=0`。`Find-NetRoute` 显示实际出口为以太网、网关 192.168.8.1；接口清单没有 Tailscale 适配器。机器有 Radmin VPN，但本次目的地址的选路经过以太网。访问未依赖 Tailnet 内网地址，具备独立于服务器 Tailnet 的公网 IPv4 验证条件。

另以 .NET SslStream 直连公网 103.84.155.153，使用系统默认可信链和域名验证，结果：

| 证书字段 | 结果 |
|---|---|
| Subject / SAN | iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net |
| Issuer | Let's Encrypt，YE2 |
| 生效时间 | 2026-10-19 13:21:58 UTC（北京时间 21:21:58） |
| 到期时间 | 2027-01-17 13:21:57 UTC（北京时间 21:21:57） |
| 公网 TLS | TLS 1.3 |
| 默认验证 | passed |

服务器 Python 默认 SSL 上下文也验证成功，协商 TLSv1.3 / TLS_AES_128_GCM_SHA256；该服务器测试属于 Tailnet 路径，不计作公网证据。

## 5. DNS 现状与稳定方案

系统为 Ubuntu 24.04.5 LTS。网络由 cloud-init 生成 Netplan，systemd-networkd 管理 eth0，systemd-resolved 处理解析；NetworkManager inactive。`/etc/resolv.conf` 正确指向 `/run/systemd/resolve/stub-resolv.conf`，不应覆盖。

当前 eth0 DNS 为临时设置的 1.1.1.1。`/etc/netplan/50-cloud-init.yaml` 仅配置 DHCP4，未设置静态 DNS 或 `use-dns: false`；生成文件也提示由 cloud-init 管理。当前设置没有发现持久化依据，重启、链路重配等情况下可能丢失，恢复原有问题。

tailscale0 单独使用 100.100.100.100 和 IPv6 DNS，并有 Tailnet/反向解析路由域；这与阿里云 DNS 100.100.2.136、100.100.2.138 是不同服务，不应混淆。

只读采样结果（短期采样不代表长期 SLA）：

| DNS | ACME UDP 查询 | ACME TCP 查询 | 补充 |
|---|---|---|---|
| 100.100.2.136 | 3/3 超时 | 超时 | 内部 OSS 域名也超时 |
| 100.100.2.138 | 3/3 超时 | 超时 | 内部 OSS 域名也超时 |
| 1.1.1.1 | 2 成功、1 超时 | 成功 | 不宜仅凭已有一次成功认为稳定 |
| 223.5.5.5 | 3/3 成功，3–79 ms | 成功 | 内部 OSS 域名解析成功 |
| 119.29.29.29 | 3/3 成功，9–12 ms | 未测 | 可作为公共 DNS 备选 |

公共 223.5.5.5 将 `oss-cn-shenzhen-internal.aliyuncs.com` 解析到 100.118.78.1–4。这仅验证了一个通用 OSS 内网端点，**不能证明租户 PrivateZone、自定义私有域名或所有阿里云内部服务均兼容公共 DNS**。未尝试访问 OSS 数据。

建议分两步实施，均未执行：

1. 先确认实际使用的 PrivateZone/内部域名清单，并向阿里云排查两个 VPC DNS 的 UDP/TCP 53 可达性。不能通过混填公共与私有 DNS 来保证分域解析，也不能仅配置 `FallbackDNS` 就声称解决已有上游超时。
2. 若确认没有依赖公共 DNS 无法解析的私有域，可在独立 `/etc/netplan/90-magicvvu-dns.yaml` 中覆盖 DHCP DNS，保留 DHCP 地址、网关及现有网卡匹配。建议候选内容如下，待批准与内部域名核验后使用：

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses: [223.5.5.5, 119.29.29.29]
```

如果确有私有域依赖，应先恢复 VPC DNS，再设计分域转发：公共域走已验证的公共 DNS，明确列出的私有域走 VPC DNS，保留 Tailscale 的 DNS 路由。可用本地条件转发器实现同一网卡上的按域上游选择；需要额外服务与配置评审，不在本次擅自引入。systemd-resolved 的域路由是按解析作用域选择，不能把同一链路上的两台 DNS 简单理解为各自负责一组域名。

持久变更的执行前提与回滚：

- **必须先获用户明确批准**，并确认控制台/VNC 等带外恢复方式；本报告不代表批准执行。
- 先将 `/etc/netplan`、`/etc/systemd/resolved.conf`、已有 resolved drop-in（若有）备份到独立的 root 权限目录；记录当前 `resolvectl status`、选路、配置校验结果及新增文件是否原先存在。
- 不编辑 cloud-init 生成文件，不覆盖 resolv.conf，不重启整个网络服务或生产主机。
- 先执行 `netplan generate` 校验；应用阶段需维护窗口、第二 SSH 会话和 `netplan try --timeout 120` 回退机制。只有 SSH、新旧域名解析及服务复核均通过后才确认；回退机制不能替代带外恢复。
- 回滚时恢复备份或移除本次新增的单个覆盖文件，再校验并在同样受控条件下应用。若需要恢复本次检查前的临时状态，执行 `resolvectl dns eth0 1.1.1.1` 和 `resolvectl flush-caches`。这恢复的是本次检查基线，而不是已经异常的 DHCP DNS。
- 变更后检查公共 ACME 域、真实内部域、Tailnet 域、Docker 服务名及容器公共解析，再复测 ACME HTTPS、Funnel 公网 HTTPS和三个容器健康。

影响评估：当前 SSH 按 IP 连接，不依赖目标主机名解析，但 Netplan 应用仍可能影响链路，不能保证零风险；Docker 的内部服务名解析与外部上游解析须分开验收。backend/db 的外部解析指向 host(127.0.0.53)，可能受宿主 DNS 改动影响；agent 当前显式外部上游为 223.5.5.5、223.6.6.6，不能据此认定其所有 AI 依赖正常。数据库容器不因 DNS 修改直接改写数据，但客户端连接及启动解析需复核。私有阿里云服务是应用公共 DNS 方案前的主要兼容性检查项。

## 6. Funnel、证书与重启恢复

`tailscale serve status --json` 显示 HTTPS 443、根路径 HTTP 代理和 AllowFunnel=true，未见前台会话的单独配置；状态文件中存在 `_serve/3595` 键。只查看了键名，未输出节点密钥、Token 或完整状态文件。

tailscaled 为 enabled，Restart=on-failure；Docker 为 enabled/active，三个主容器 restart policy 均为 unless-stopped。证书文件存在，私钥文件权限为 600，仅检查文件元数据，未读取私钥。

依据 [Tailscale Funnel CLI 文档](https://tailscale.com/docs/reference/tailscale-cli/funnel)，后台 Funnel 配置可在设备/Tailscale 重启后恢复。当前配置与此一致，但未进行实际重启验收。依据 [Tailscale CLI 证书说明](https://tailscale.com/docs/reference/tailscale-cli?tab=macos)，由集成服务管理的证书支持自动续期；本环境由 tailscaled 直接终止 TLS，无需导出证书另建续期任务。未来真实续期尚未发生，DNS 故障可能阻断续期。

因此可报告“恢复配置已具备”，不能报告“生产重启后 HTTPS 已实测成功”。

## 7. 公网只读安全审计

审计依据为运行中 backend 容器 `/app/app` 的源码、实时 OpenAPI，以及少量公网拒绝测试；没有仅凭本地仓库推断线上行为。未使用真实用户账号、有效用户/服务令牌或真实家庭 ID，未读取用户私人数据，未注册、登录、写入、爆破或压测。

### 已验证的保护

- `/api/v1/users/me`、家庭列表、家庭成员、库存、购物列表、AI 任务和草稿读取接口，无身份请求均返回 401；家庭/资源路径采用全零占位 UUID。
- 明确无效的虚构 Bearer 令牌访问 users/me 返回 401。
- 运行源码 `get_identity` 校验令牌摘要、过期、撤销及用户 active；密码采用 Argon2，令牌随机生成且数据库保存摘要，默认有效期 12 小时，logout 撤销会话。
- 家庭成员查询与库存操作调用 membership 校验；库存按 household_id 过滤。购物资源按所属清单过滤；AI task/draft/operation 按当前 user_id 及家庭成员关系过滤。邀请和家庭改名限制 owner/admin。
- 内部库存及 operation 接口虽然在 OpenAPI 中没有 security scheme 声明，实际通过自定义 Header 依赖校验服务 Bearer Token，并校验用户 active、家庭成员及资源 scope。无身份公网请求均 401；不能把 OpenAPI 的 `security=[]` 误判成无保护。
- 当前运行开关 `AUTH_ALLOW_UNVERIFIED_SIGNUP=false`，注册代码首先返回 403。只读取这一非敏感开关，未输出容器全部环境变量，也未通过真实注册请求验证。

### 风险与限制

| 级别 / 状态 | 发现 | 建议 |
|---|---|---|
| 高，正式上线阻断建议 | 登录直接暴露公网；运行应用代码未发现速率限制、失败锁定、验证码或相应中间件；源码明确注明面向 loopback/SSH 的原型认证 | 正式公网使用前补充登录防滥用保护及验收；本次不擅改认证逻辑 |
| 中 | `/openapi.json`、`/docs`、`/redoc` 公网全部 200，暴露业务和内部 API 结构 | 正式环境关闭或限制文档入口，另行授权后实施 |
| 中 | `/internal/v1/*` 通过根路径 Funnel 公开可达，当前依赖共享服务凭据 | 建议限制公网路径到 App 必需接口；不能去掉服务鉴权 |
| 尚待验证 | 静态检查未发现已确认的跨家庭读取路径，但未用两组受控账号执行已登录越权验证 | 独立测试环境/专用测试家庭补测；不能宣称全面排除越权 |
| 尚待验证 | 没有做登录爆破或账号枚举测试，也未完整审计外部身份防护系统 | 不以“没有攻击成功”证明登录保护合理 |

未在注册路由中看到独立管理员接口；实时 OpenAPI 无明显 admin/debug 路由，公网 `/admin` 和 `/debug` 返回 404。这是有限检查，不能证明所有可能路径都不存在。公开 health/ready 为状态接口；未从这些接口取得数据库凭据。

**建议在安全整改完成前暂时关闭公网 Funnel，保留 SSH/Tailnet 联调，尤其不应接入真实用户数据。此次未关闭 Funnel。** 如果必须继续短期受控联调，应明确接受登录缺少防滥用及文档/内部路径暴露的风险；不能把它等同于正式上线批准。关闭公网会影响 Android 公网调用，需用户确认后操作；不得用 reset 清空配置。

## 8. 实际执行的关键命令与结果

本机首次受限执行被网络沙箱拒绝，随后按授权通过工具网络提权执行成功；不是服务器 SSH 用户权限不足，也没有绕过服务器鉴权。所有 sudo 命令使用 `sudo -n`，无需交互密码。

以下为已执行命令或批处理中相同的命令；重复查询通过循环执行，表中 `HOST` 指完整 ts.net 域名，UUID 为全零占位值。

| 命令 | 关键结果 |
|---|---|
| `ssh -o BatchMode=yes -o ConnectTimeout=12 magicvvu ...` | 使用已有 SSH 别名/admin 公钥连接 |
| `date -Is; cat /etc/os-release` | Ubuntu 24.04.5，UTC+08:00 |
| `systemctl is-active tailscaled` / `systemctl is-enabled tailscaled` | active / enabled |
| `tailscale version` / `tailscale funnel status` | 1.104.1 / Funnel on |
| `tailscale serve status --json` | 443 HTTPS、根路径代理、AllowFunnel=true |
| `curl -sS --max-time 15 -o /dev/null -w 'local_health=%{http_code}\n' http://127.0.0.1:8000/api/v1/health` | 200 |
| `sudo -n docker ps --format '{{.Names}}\|{{.Image}}\|{{.Status}}\|{{.Ports}}'` | 主容器和额外测试容器 healthy；后端只绑定 127.0.0.1:8000 |
| `sudo -n journalctl -u tailscaled --since '2 hours ago' --no-pager -n 100` | DNS 超时历史和 got cert |
| `sudo -n journalctl -u tailscaled --since '2026-10-19 22:20:34' --no-pager -n 30` | 抽查范围无持续 ACME 错误 |
| `resolvectl status; readlink -f /etc/resolv.conf; networkctl status eth0 --no-pager` | resolved stub、临时 DNS |
| `sudo -n cat /etc/netplan/50-cloud-init.yaml /run/systemd/network/10-netplan-eth0.network` | DHCP、无 DNS 持久覆盖 |
| `dig @DNS acme-v02.api.letsencrypt.org A +time=2 +tries=1 +noall +answer +stats` | 对照 DNS 结果见第 5 节 |
| `dig @DNS acme-v02.api.letsencrypt.org A +tcp +time=2 +tries=1 +short` | TCP 对照结果见第 5 节 |
| `dig @DNS oss-cn-shenzhen-internal.aliyuncs.com A +time=2 +tries=1 +noall +answer +stats` | VPC DNS 超时，223.5.5.5 成功 |
| `curl -sS --max-time 15 -o /dev/null -w 'acme_https=%{http_code}\n' https://acme-v02.api.letsencrypt.org/directory` | 200 |
| `ip route get 100.100.2.136; ip rule show` | 目的地址经 eth0 VPC 网关 |
| `getent ahostsv4 HOST` / 服务器域名 HTTPS curl | 100.123.235.8 / 200 verify=0 |
| Python `ssl.create_default_context()` + `wrap_socket(..., server_hostname=HOST)` | 有效证书、TLS 1.3 |
| `Resolve-DnsName HOST -Server 1.1.1.1` | 公共 A/AAAA |
| `C:\Windows\System32\curl.exe --noproxy '*' --resolve "HOST:443:IP" -sS --connect-timeout 10 --max-time 25 -w ... https://HOST/api/v1/health` | 两个公共 IP 均 200 verify=0 |
| PowerShell `SslStream.AuthenticateAsClient(HOST)`，连接公共 IP | 系统默认验证 passed；证书有效期见第 4 节 |
| `Get-NetAdapter` / `Find-NetRoute -RemoteIPAddress '103.84.155.153'` | 无 Tailscale 网卡，目的地址经以太网 |
| `docker exec ... cat /app/app/{指定源码文件}` 和容器内 AST/关键词检查 | 只读认证、权限及防滥用实现 |
| Python urllib 读取本地 `/openapi.json` | 只输出路由及安全方案，不输出用户数据 |
| 公网 curl GET（输出丢弃，仅记录 HTTP 状态） | 文档 200、受保护接口 401、admin/debug 404 |
| `docker exec 容器 cat /etc/resolv.conf` | Docker 127.0.0.11 及不同外部上游 |
| `systemctl is-enabled docker; systemctl is-active docker` | enabled / active |
| `sudo -n docker inspect --format ...`（仅指定状态字段） | 重启策略、启动时间、健康状态及 RestartCount |

一次 SSH 标准输入脚本末尾带 CR 导致 `head` 和 `systemctl is-enabled docker` 命令失败；后续用 Python SSH 脚本重新检查 Docker 自启并用 Python SSL 及公网 SslStream 完成证书检查，未把失败命令计作通过。

## 9. 修改与回滚记录

服务器配置修改：**无**。本次未执行 DNS 切换、持久化写入、Funnel 重配置、服务重启、数据库写入或业务代码修改。不存在本次服务器修改需要回滚。

此前用户临时执行的 `resolvectl dns eth0 1.1.1.1` 并非本次变更。`resolvectl revert eth0` 可撤销该链路运行时覆盖，但可能重新使用当前异常的 DHCP DNS，因此本次未执行。建议保留当前可用状态，待受控持久方案获批后处理。

本次本地仅新增本报告；原有两个 Android 文件的未提交修改保持原样。

## 10. Android Base URL 与剩余事项

最终 HTTPS Origin / Base URL：

```text
https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net
```

当前 Android 代码自行拼接 `/api/v1/...`，因此 Base URL 不再附加 `/api/v1`，也不使用 100.123.235.8、公共 IP 常量或 HTTP 8000。Funnel 公共 IP 可能变化，应使用域名。release 构建现有 Gradle 属性为 `mewstowReleaseApiUrl`，debug 为 `magicvvuApiUrl`；本次未修改 App 配置。

**建议：可以将 HTTPS 地址用于专用测试账号的受控移动端连通性检查；不建议进入面向真实用户的 Android 正式对接/上线阶段。** 正式阶段前需解决登录防滥用缺口、批准并验证 DNS 持久化，并完成受控账号之间的权限验收。

尚需用户完成或确认：

1. 决定是否临时关闭公网 Funnel；关闭前明确移动端影响。本次保持原配置。
2. 提供实际 PrivateZone/阿里云私有域依赖清单，确认带外恢复手段，并明确批准 DNS 持久配置及受控应用；未获批准不实施。
3. 将登录防滥用及文档/内部路径暴露治理作为独立授权变更处理，本任务不改后端认证或权限逻辑。
4. 手机关闭 Tailscale、其他 VPN 及 Wi-Fi，改用 4G/5G，浏览器打开下面的健康地址；应无证书警告并显示 status=ok。若用电脑连接该手机热点，可运行不带 `-k` 的 `curl -i` 确认 HTTP 200。记录运营商、时间和响应；若浏览器失败，保留具体错误，以区分移动 DNS、IPv6 和路径问题。

```text
https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net/api/v1/health
```

公网 IPv4 已完成独立验证，手机测试属于补充验收；不得将其尚未执行混同于“完全没有公网测试”。

参考配置依据：[Netplan 官方配置文档](https://github.com/canonical/netplan/blob/main/doc/netplan-yaml.md)、[systemd-resolved DNS 路由说明](https://www.freedesktop.org/software/systemd/man/latest/systemd-resolved.service.html)。配置方案为结合现场结果的建议，未实施，也未保证适用于尚未提供的私有域依赖。
