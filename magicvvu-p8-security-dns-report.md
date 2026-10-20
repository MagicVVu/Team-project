# MagicVVu P8 公网安全加固与 DNS 稳定化报告

日期：2026-10-20，Asia/Shanghai。现场只读检查约 08:45–08:58。

## 1. 结论与状态

**开发安全补丁及本地回归已完成；生产环境尚未整改，整体仍为 NOT PASS。**

- **已完成**：完整阅读上一阶段报告；核对线上实际源码；开发登录限流、失败响应均衡、默认关闭文档；交付公网入口和 DNS 候选配置、只读验收脚本。
- **已测试**：完整 Backend 套件 **116 passed、5 skipped**；包含 13 项新增应用安全测试及 16 项真实 Nginx 网关测试。两个服务之间的健康端点、生产三个主容器、公开健康接口只读检查正常。
- **已定位**：阿里云 VPC DNS 回包已抵达 eth0，却匹配 Tailscale 的 CGNAT 防伪 DROP 规则。不能再将该超时简单归为阿里云 DNS 不响应。
- **尚待批准**：Backend 镜像部署/容器更新、公网网关安装及 Funnel 转发切换、DNS 回包的窄范围防火墙例外、DNS 持久化及重启验收。
- **尚未验证**：补丁在服务器上的效果、真实 Funnel PROXY v2 链路、Linux 网关服务启动、真实 PostgreSQL 并发锁、PrivateZone 控制台配置及系统重启恢复。

没有改变服务器文件、网络、防火墙、密钥、数据库、容器或 Funnel 状态。未进行生产登录、注册、爆破、用户数据查询或模型调用。

## 2. 实际部署与源码对应关系

本轮线上 Backend 镜像已为 `magicvvu/backend:p72-units-736c2299edda`，Agent 为 `magicvvu/agent:p72-units-755c1561abc8`，后端 health 仍自报 **0.9.0**。不能按旧报告镜像标签部署回退。

只读取得运行容器源码 SHA-256：

| 文件（容器 `/app/` 下） | SHA-256 |
|---|---|
| app/main.py | 720e49a7f53e9cf2c4ed4b20974ffc028d1ea1118e500cbd2e08831a7784e127 |
| app/security.py | f54ee78b2f24cb3c9ddebc2661fb9f74b30aadbc5be7d4e98fcc2b2db8a3609b |
| app/routers/auth.py | f897a278d4eb9c21c5f06c036c1bd30c202d4b7169c44a4b2f44bdd8e54055c0 |
| app/dependencies.py | 4db008a72a889ccda410401f1b83a1f5671ff50b0b1b243004ee36c0758a7441 |
| app/routers/ai_inventory.py | dacb09f45186e3de6704b87dedcac1c1c213edafd79da4008811415f6e6bbae5 |

修改前本地后四个文件直接匹配；main.py 统一换行后与仓库 HEAD 匹配。线上实际启动参数为单 worker，未指定 `--no-proxy-headers`。本轮开发基线为 dev 分支 `208354a`；开始时工作区干净，按协作说明尝试 `git pull --no-rebase origin dev`，因 GitHub 连接重置失败。保留本地开发成果，未提交/推送，后续共享前需重新同步并复核冲突。

## 3. 登录问题、兼容性与开发补丁

### 原问题

1. 原登录接口没有 IP、账号、总体请求或 Argon2 并发限制，存在猜密及资源耗尽风险。
2. 不存在/停用账号跳过密码验证，而存在账号执行 Argon2，即使均返回 401，仍可能形成时间差。
3. 注册开关线上为 false，暂未开放未经验证手机号注册。不能为了内部测试重新开放公网注册；开启后的重复账号 409 仍可能透露存在性，不在本次默认支持的公网模式中。
4. Funnel 后普通连接来源是代理，任意客户端都能提交转发头；不能用头字段直接当真实 IP。

### API 兼容性影响（实现前已说明）

| 行为 | 变更 / 影响 |
|---|---|
| 正常登录、Token、logout | 路径、字段、Bearer 机制和默认 12 小时有效期不变 |
| 失败登录 | 仍为 401，同一通用 detail；增加 no-store，失败耗时至少约 250 ms |
| 超限 | 新增 429、通用 detail、Retry-After 秒数；不返回账号是否存在 |
| 登录密码长度 | 超过 128 字符返回 422，与原注册密码上限一致；已有正常注册账号不受影响 |
| 文档 | `/openapi.json`、`/docs`、`/redoc` 默认 404；独立开发环境可用 `MAGICVVU_ENABLE_DOCS=true` 明确开启 |
| 公网入口候选 | 文档、内部路径和 ready 返回 404，注册返回 403；App `/api/v1/` 路径继续转发 |
| Android | 现有客户端能处理非 2xx，不自动重试；429 目前显示通用错误，后续可另加友好提示，不要求改变认证协议 |
| P7 运维预检 | 原脚本依赖 OpenAPI，已改为无身份 GET 探测 401/405，避免关闭文档破坏预检 |

### 已完成的代码

- `backend/server/app/login_guard.py`：线程锁保护的单进程滑动窗口，**账号 8 次/300 秒，连接来源 30 次/60 秒，总体 120 次/60 秒，最多 4 个在途登录**。成功和失败均计数，不能用成功登录清空猜密预算；账号先由既有 Pydantic 逻辑规范化，手机号两种写法共用额度。
- 限流先于用户查询和昂贵验证。状态最多 4096 个键；过期回收，容量耗尽拒绝而非淘汰仍有效的计数。标识以摘要作为键，不记录密码、原始手机号或 Token。
- `security.py`：不存在/停用用户也执行相同参数的 dummy Argon2 验证。
- `routers/auth.py`：失败响应统一，设置至少 250 ms 的失败耗时下限；睡眠和验证受在途上限保护；失败和成功响应 no-store。没有长期账号锁死或修改用户记录。
- `schemas.py`：登录密码上限 128。
- `main.py`：默认关闭文档，保留内部业务路由给 Agent。
- `Dockerfile`：固定一个 worker 并显式 `--no-proxy-headers`。另附 Compose 候选覆盖，防止现有 command 覆盖镜像 CMD。
- `p7_preflight.py` 与其测试：不再读取 Backend OpenAPI，保持只读，不提交有效消息或写操作。

**限制**：这是团队单实例、单 worker 的最小实现。计数在重启后清空，不能直接扩成多 worker/多副本；扩容前须换共享原子存储。已知账号可被第三方暂时消耗登录额度，最多等待窗口结束，这是无需数据库锁定的短时可用性取舍。失败均衡降低时间差，但不宣称在任意数据库负载下严格恒定时间。

后端只使用 ASGI 连接来源，不解析 Forwarded/XFF。通过 Funnel/网关时，多名用户可能共用后端的 **30 次/分钟代理来源预算**；该预算是总体保护的一部分，不应被标成每位手机用户独享的真实 IP 配额。真实公网 IP 限流由下述经过验证的入口协议承担。

## 4. 公网接口治理与真实 IP 信任边界

候选链路：

```text
手机 HTTPS → Funnel（TLS 终止、PROXY v2）
           → 127.0.0.1:18081 Nginx
           → 127.0.0.1:8000 Backend
Agent ─────────────────→ backend:8000（现有 Docker 内网）
```

文件：

- `deploy/p8/nginx-public.conf.candidate`
- `deploy/p8/magicvvu-public-gateway.service.candidate`
- `deploy/p8/compose.security.override.yaml.candidate`

入口只监听回环，接受 tailscaled 提供的 PROXY v2。Nginx realip 只信任 127.0.0.1 的 PROXY 数据，不信任用户 HTTP 头；清除 XFF、X-Real-IP、Forwarded、额外客户端 IP 和 Tailscale 用户声明头。Bearer Authorization 保留。

Nginx 登录来源 IP 限制为 **6 次/分钟，burst=4**；开发测试连续前 5 次通过，第 6 次为 429，伪造 XFF 无法换 IP。不同 PROXY 来源地址独立计数。其他 App API 为 10 次/秒、burst=20；候选入口请求体上限 1 MiB，读取响应超时 60 秒，部署前须用团队最大实际测试消息确认边界，不能假定任何将来的上传功能都适用。

只转发 `/api/v1/`，对内部、文档及未知路径默认拒绝；`/api/v1/ready` 只保留在内网；公网注册显式 403。Agent 仍直连现有 backend:8000，继续使用原服务 Token 与 scope 校验，不经公网入口，不需要变更密钥或数据库。开发旧套件验证了内部工具鉴权与家庭过滤。

**实际测试范围**：Windows nginx 1.30.6（官方 HTTPS 下载）真实进程、临时回环端口、虚构 HTTP upstream、合成 PROXY v2 包，16 项均通过；包含 encoded dot/encoded slash、重复斜杠、伪造头、无 PROXY 元数据、文档/内部路径阻断及 Authorization 保留。没有把这一结果当作 Linux 服务或线上 Funnel 已验证。

[Tailscale 官方文档](https://tailscale.com/docs/reference/tailscale-cli/funnel) 支持 `--proxy-protocol=2 --tls-terminated-tcp=443`；[Nginx realip 文档](https://nginx.org/en/docs/http/ngx_http_realip_module.html)说明 PROXY 元数据的接收方式。服务器上的真实组合仍需在获批后验证，不能退回信任任意 XFF 作为替代。

拟部署文件为 `/etc/nginx/magicvvu-public.conf` 和 `/etc/systemd/system/magicvvu-public-gateway.service`，并建立 `/var/lib/magicvvu-public-gateway/{logs,temp}`，由 www-data 管理。需验证系统 nginx 含 realip 模块并执行配置检查，不能直接照搬 Windows 二进制。

## 5. DNS 依赖与根因的新证据

### 依赖检查

读取容器配置时只输出 URL 的 hostname 和白名单非敏感开关；没有输出完整环境变量、连接串、服务密钥或数据库凭据。

| 实际依赖 | 结果 |
|---|---|
| Backend → DB | DB_HOST=db，Docker 解析到 172.18.0.2 |
| Backend → Agent | AI_SERVICE_URL 主机 agent，解析到 172.20.0.3，健康接口 200 |
| Agent → Backend | BACKEND_BASE_URL 主机 backend，解析到 172.20.0.2，健康接口 200 |
| Agent 模型依赖 | 代码缺省 api.deepseek.com，容器解析成功；未调用付费模型 |
| TLS 证书 | acme-v02.api.letsencrypt.org |
| 公网地址 | iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net |

扫描运行 Python/配置文件和部署环境中的 endpoint 字段，未发现 OSS/RDS/PrivateZone 等实际服务依赖。**没有阿里云控制台/API 的 Private DNS 资源清单权限，不能确认 VPC 中不存在私有域或未来依赖**；需要用户确认关联 PrivateZone、DHCP 域名和团队自定义内部域名。上一阶段通用 OSS 域名解析成功不代表内部服务可访问。

### 已定位的回包丢弃

主机 OUTPUT ACCEPT、UFW inactive，目的地址经 eth0 的 VPC 网关；INPUT 进入 ts-input，相关规则为：

```text
-A INPUT -j ts-input
-A ts-input -s 100.123.235.8/32 -i lo -j ACCEPT
-A ts-input -i tailscale0 -j ACCEPT
-A ts-input -p udp --dport 41641 -j ACCEPT
-A ts-input -s 100.115.92.0/23 ! -i tailscale0 -j RETURN
-A ts-input -s 100.64.0.0/10 ! -i tailscale0 -j DROP
```

08:53:03，窄过滤抓包只捕获本次发送到 100.100.2.136:53 的公开 ACME 查询：

```text
08:53:03.218995 172.19.29.17.45622 > 100.100.2.136.53: 26093 A? acme-v02.api.letsencrypt.org
08:53:03.219455 100.100.2.136.53 > 172.19.29.17.45622: 26093 ... A 172.65.32.248
dig: timed out
ts-input CGNAT DROP counter: 27121 → 27125
```

同一查询 ID 的正确 DNS 回包约 0.46 ms 后已经到达 eth0，因此该查询的主要问题不是远端无响应。源地址属于 100.64.0.0/10，不满足前面任何例外，落入 DROP。计数增量包含同一时间窗其他报文，不能把 4 个丢包全部归为这一查询，但抓包、规则顺序和应用超时共同定位了阻断路径。100.100.2.138 同属该范围，UDP/TCP 查询也失败，尚未单独抓包。

[Tailscale netfilter 文档](https://tailscale.com/docs/reference/netfilter-modes)明确描述该 CGNAT 防伪规则；[阿里云 Private DNS 文档](https://www.alibabacloud.com/help/en/dns/do-i-need-to-modify-the-dns-configuration-of-the)说明默认 VPC DNS 地址。需要在保留防伪保护的同时评审窄例外；不得关闭整个 Tailscale netfilter 或放行整个 100.64.0.0/10。

### 公共 DNS 的有限采样

- 223.5.5.5：本轮 ACME UDP/TCP 均有成功，交付脚本复采也成功。
- 119.29.29.29：UDP 成功，但 TCP 超时/复采未取得完整 A 记录，因此此前“表现较好”不能等同于稳定备用。
- 223.6.6.6：ACME UDP 三次中两次有完整 A，一次只有 CNAME、1645 ms；ACME TCP 3/3 完整 A，DeepSeek UDP/TCP 各 3/3 完整 A。仍不应直接宣称长期稳定。
- 1.1.1.1 仍是 eth0 运行时 DNS；Netplan 没有持久覆盖。

公共 DNS 能绕过此次 VPC DNS 源地址问题，但不能恢复 PrivateZone；解析出的其他 100.64/10 内网服务地址也可能遇到相同回包规则。DNS 成功不等于该服务网络访问成功。

## 6. DNS 持久化候选、备份与断连恢复

**首选：先获批做窄范围 VPC DNS 回包验证，成功后持久化 VPC DNS。** 这样保留公共及阿里云私有解析能力，不需要引入新的解析服务。若存在只适用特定上游的域，再评审按域转发；不要在同一 nameserver 列表混填公网/内网地址并声称自动分域。

### 需批准的第一步：回包规则验证

只允许 eth0 上来自 **100.100.2.136/32、100.100.2.138/32，源端口 53、conntrack ESTABLISHED** 的 UDP/TCP 回包，在 INPUT 的 ts-input 跳转之前处理。不开放服务监听端口，不改 SSH 或安全组，不删除原 DROP 规则。

以下为**待批准的规则规格，不是已执行命令**。对两个地址、udp/tcp 各生成一条，共四条；先检查是否已有同一 comment 的规则，记录位置，避免重复：

```bash
iptables -w -I INPUT 1 -i eth0 -s 100.100.2.136/32 -p udp --sport 53 \
  -m conntrack --ctstate ESTABLISHED \
  -m comment --comment magicvvu-p8-dns-reply -j ACCEPT
# 另三条：.136/tcp、.138/udp、.138/tcp；条件完全相同。
```

测试两台 VPC DNS 的公共及用户提供的私有域，UDP/TCP 各多轮。若失败，删除这四条完整匹配 comment 的规则并停止后续切换；不能升级为放行整个 CGNAT。

### 第二步：独立 Netplan 文件

| 方案 | 开发候选 | 服务器目标 | 启用条件 |
|---|---|---|---|
| 首选 VPC DNS | deploy/p8/90-magicvvu-vpc-dns.yaml.candidate | /etc/netplan/90-magicvvu-dns.yaml | 回包例外获批并成功验证 |
| 公共 DNS 备选 | deploy/p8/90-magicvvu-dns.yaml.candidate | 同上，二选一 | 用户确认无私有依赖，并完成备用上游长期采样 |

首选文件内容：

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses: [100.100.2.136, 100.100.2.138]
```

保留 cloud-init 的 DHCP 地址、网关、MTU 和网卡匹配，不修改 `/etc/netplan/50-cloud-init.yaml`，不覆盖 `/etc/resolv.conf`。公共 DNS 备选保留上一阶段的 223.5.5.5/119.29.29.29，**鉴于本轮备用 TCP 失败，该候选当前不建议直接应用**；需重新选择和验收备用，不能掩盖采样失败。

DNS 回包例外也需要持久性评审：拟用独立脚本 `/usr/local/sbin/magicvvu-vpc-dns-replies` 及 `/etc/systemd/system/tailscaled.service.d/60-magicvvu-dns-replies.conf` 的 ExecStartPost，在 tailscaled 启动完成后幂等校正四条规则的位置。该扩展**尚未实现或测试，不在本轮直接申请部署范围内**；实施前须准备脚本、失败不阻断 tailscaled 启动的处理、精确删除回滚，并验证 daemon 重启/网络重配是否移动 jump。不能只保存静态 Netplan 就宣称 DNS 重启稳定。若用户只批准临时窄规则诊断，不写这些持久文件。

### 备份、应用与恢复（均未执行）

1. 用户确认维护窗口、VNC/云控制台可用；保留当前 SSH 会话并另开一个按 IP 连接的会话。
2. 以 UTC+08:00 时间命名 root-only 备份目录，备份 `/etc/netplan`、resolved 配置及现存 drop-in；保存 `resolvectl status`、IP/路由和 `iptables-save` 快照。记录候选目标文件原先是否存在。防火墙快照只用于核对，不能整表恢复覆盖运行中的 Docker/Tailscale 规则。
3. 先单独批准、测试并回滚验证四条 DNS 回包规则；不切换 DNS。临时测试成功后再单独审批持久规则脚本。
4. 获批后安装唯一候选文件为 0600，`netplan generate` 校验；`netplan try --timeout 120` 只在明确授权后执行，不直接 apply。检查新的 SSH 会话、解析、HTTPS、容器及 Agent 健康后才确认。
5. 若断连，不确认 try，等待回退并从第二 SSH 会话核实；自动回退不是绝对保证。失败则从云控制台恢复备份/移除本次新增的单个 overlay，再受控应用；需要回到本轮基线时，用 `resolvectl dns eth0 1.1.1.1` 及 flush-caches。不得盲目重启网卡或服务器。
6. 回滚防火墙仅删除完整匹配本任务 comment、源地址、协议、接口和 conntrack 条件的四条规则；若曾安装持久脚本/drop-in，先移除新增项并 daemon-reload，避免重新插入。当前 SSH 按 IP 连接不依赖 DNS，但 Netplan 应用仍可能影响链路，不保证零断连。

Docker 无需重建网络。Backend/DB 的外部 DNS 经过宿主 resolved，可能受到切换影响；Agent 已有独立上游 223.5.5.5/223.6.6.6，不能假定会同步改变。Docker 内部 db/agent/backend 解析、服务健康和模型域名均应分别复核。不修改数据库内容或 Agent 配置。

### 重启后验收设计

当前不重启。只在另获明确批准的窗口中执行一次重启，恢复后核对：

- SSH 按公网 IP 可登录、接口/网关与预期一致；netplan overlay 正确加载；DNS 不是依赖上次 resolvectl 运行时命令。
- 四条回包例外存在且位于 ts-input jump 前，原 CGNAT DROP 仍保留；随后受控验证 tailscaled 重启/网络重配不会丢失规则，均须另行授权。
- 公共 ACME、DeepSeek、Funnel 和实际 PrivateZone 域多轮 UDP/TCP 解析；不能只命中缓存，也不能只统计 dig 退出码，必须取得完整所需记录。
- tailscaled/Docker 自启，Funnel 转发配置恢复；内网及独立公网 HTTPS 校验成功；三个主容器 healthy。
- Backend↔Agent health 与专用测试身份的内部 scope 拒绝/允许行为；不使用真实家庭做数据探测。
- 在预定观察窗口继续抽样，例如每分钟一次连续 30 分钟，由操作人员运行，不在本轮创建后台监控或自动重启任务。

## 7. 自动化测试与可复现回归

证据：`docs/versions/V1-P8/backend-tests.xml`、`security-tests.xml`、`edge-tests.xml`、`readonly-snapshot.json`。

Windows 开发环境复现（仓库根目录）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/server/requirements-dev.txt
# 将官方 nginx 二进制放在本地缓存目录；此二进制不提交到仓库。
$env:P8_NGINX_EXE=(Resolve-Path .cache/p8/nginx-1.30.6/nginx.exe).Path
.\.venv\Scripts\python.exe -m pytest backend/server/tests -q --junitxml=docs/versions/V1-P8/backend-tests.xml
# 无有效登录或写操作的服务器快照，需先确认本机为非 Tailnet 公网出口：
.\.venv\Scripts\python.exe tools/p8_readonly_acceptance.py --dns-samples 3
```

完整结果：**116 passed，5 skipped，14 warnings，51.70 秒**。5 项跳过均为原有真实 PostgreSQL 并发/行锁场景；本轮没有生产或专用 PostgreSQL 测试服务，不能用 SQLite 冒充已验证。警告为已有 Alembic 配置和 AnyIO/Starlette 废弃提示。未设置 P8_NGINX_EXE 时，网关测试会明确 skip，不可把这种运行算成完整入口验收。

| 要求 | 已测试 / 可复现方式 | 生产后续门槛 |
|---|---|---|
| 本地健康 | 服务器 127.0.0.1:8000 health=200 | 部署后复测 |
| 公网 HTTPS | 系统 curl 验证 200、verify=0；只读脚本也成功 | 网关切换后重新确认非 Tailnet 路径及证书 |
| 登录失败/滥用 | test_p8_security：虚构账号、dummy 验证、耗时下限、规范化、429、并发和额度恢复 | 仅专用测试账号验收，不爆破真实账号 |
| 无身份保护 | 本地旧套件及公网全零 UUID 请求 401 | 补丁部署后复测 |
| 跨家庭隔离 | 旧库存/购物/草稿/内部工具套件以虚构身份验证 404/隔离 | 专用测试家庭受控验收；不读真实用户数据 |
| 内部 Agent 通路 | 真实容器双向 health 200；本地内部工具 Token/scope 套件通过 | 网关启用后保持 backend:8000 内网直连 |
| 公网文档/内部路径 | 本地文档默认 404；真实 Nginx 入口拒绝与编码绕过测试通过 | 线上仍是文档200、内部401，尚未治理 |
| DNS 稳定性 | 只读脚本默认对四个上游采样公共 ACME 的 UDP/TCP；额外手工检查实际 DeepSeek 域 | 私有域清单、长时间采样及重启后验收未完成 |
| 三个容器 | 检查前后 healthy、启动时间未变、重启数 0 | 任一部署后重新检查 |

只读脚本不下载文档内容，不读取受保护接口返回内容，不登录、不用 Token、不触发 Agent 模型；它始终 `overall_pass=false`，输出观察结果，不能自动批准上线。`--public-only` 和一次 SSH DNS 采样模式均实际运行成功。该脚本不是跨家庭/登录写路径的生产测试器。

## 8. 待批准的生产变更与回滚顺序

按阶段审批，不能把对本报告的认可等同于全部操作授权：

1. **先批准临时四条 DNS 回包规则验证**：仅针对两个 VPC DNS 的已建立连接回包，保留当前运行时 1.1.1.1，失败按精确规则删除。此操作改变生产防火墙，虽范围小也需明确批准。
2. **Backend 补丁部署**：先构建/扫描并固定候选镜像 digest，保存当前 Backend digest/Compose 配置备份，验证 override 后只更新 backend，Agent/DB 不重启、不迁移。Backend 更新会短时中断 API，需要维护窗口；回滚原 digest 和原启动参数。当前线上镜像标签不是旧 v0.8。
3. **公网入口**：先安装/检查 Linux nginx 和候选服务，再按获批方式验证本地 PROXY v2；保存现有 Funnel status JSON；切换根转发到 18081 时有短时中断风险。拟用的 CLI 目标为 `tailscale funnel --bg --proxy-protocol=2 --tls-terminated-tcp=443 tcp://127.0.0.1:18081`，需先按该版本 CLI 处理现有 443 模式冲突；不执行 reset。失败回退到原 `tailscale funnel --bg --https=443 http://127.0.0.1:8000`，先关闭本次新增的 TLS-terminated TCP 443 配置；回退会重新暴露旧路径，需明确风险选择。整段尚未在生产执行。
4. **DNS 持久化**：回包诊断成功、用户确认 PrivateZone/带外恢复后，再完善并审批回包规则持久脚本及唯一 Netplan overlay。未批准前不上传、更改或 generate/apply/try。
5. **重启验收**：独立审批，不为完成报告而重启服务器。保留旧配置、VNC 恢复和公网验收步骤。

目前未发现需绕过认证才能访问真实数据的已证实漏洞；团队可自行决定是否在短期内继续使用当前公网测试入口。登录防滥用缺口和文档暴露仍存在于线上，建议在整改前避免真实账号/数据，必要时先申请暂停 Funnel。**本轮没有关闭或更改 Funnel。**

## 9. Android 对接条件

Base URL 保持：

```text
https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net
```

不附加 `/api/v1`，现有 Android 自行拼接路径。开发测试表明原认证协议、家庭权限和内部 Agent 合约没有被此次修改破坏。

**现在可以继续使用虚构/专用测试身份做受控联调；尚不具备声明“P8 已完成、稳定安全公网正式对接通过”的条件。** 需要补丁实际部署、公网入口与真实 IP 链路验收、DNS 回包修复和持久性验收、专用测试家庭回归完成后再作结论；团队内部用途不等于无需这些验证。本轮不涉及商业化要求。

用户下一步需要确认：是否批准第 8 节第 1 项的最小 DNS 回包诊断，以及提供 PrivateZone/内部域清单和云控制台恢复条件。其余部署、Funnel 切换及重启各自单独审批。
