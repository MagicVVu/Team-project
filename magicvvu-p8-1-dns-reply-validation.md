# MagicVVu P8.1：VPC DNS 回包临时修复与回滚验证

阶段 A：2026-10-20 09:30–09:32；获批后的阶段 B/C：09:39–09:43，Asia/Shanghai。

## 1. 当前结论与授权边界

**临时修复验证成功，且四条临时规则已全部精确移除，回滚验证通过。** 两台 VPC DNS 对 ACME、DeepSeek 域名的 UDP/TCP 查询在规则有效时 24/24 成功；移除后恢复原有阻断，证明最小回包例外可解决本次问题。系统 DNS 全程保持 1.1.1.1，因此当前并非已永久修复的 VPC DNS 环境。

| 阶段 | 状态 |
|---|---|
| A：只读复核、基线、规则及连接跟踪分析 | 已完成 |
| B：四条临时回包放行规则 | 用户单独回复“确认”后已获批；09:41:47 插入四条 |
| C：修复后验收及回滚演练 | 24/24 DNS 查询成功，服务检查正常；09:42:26 已精确删除四条，09:42:36 完成回滚验证 |
| 永久 DNS/防火墙配置 | 未实施，本阶段不实施 |

本次没有切换运行时 DNS、修改 Netplan、重启服务、安装软件、更改 Funnel、部署 Backend/Nginx 或修改 Android。SSH 只读使用已有 admin 账号和 `sudo -n`，没有绕过服务器权限控制。

授权依据：阶段 A 完成后，已明确询问“是否批准临时插入四条规则、完成验证后精确移除，并确认阿里云控制台/VNC 恢复途径可用”，用户单独回复“确认”。据此执行本次临时验证和精确移除；没有将授权扩大为永久配置、DNS 切换或其他部署。控制台可用性由用户确认，本次未登录控制台或索取凭据。

## 2. 当前服务器健康

| 项目 | 结果 |
|---|---|
| SSH | 两轮新连接成功，ssh.service active |
| Docker / tailscaled / systemd-resolved | 均 active |
| Tailscale | 1.104.1 |
| eth0 | UP，172.19.29.17/18，未变化 |
| 两个 VPC DNS 的选路 | 均经 172.19.63.253、eth0，源地址 172.19.29.17 |
| eth0 当前运行时 DNS | 1.1.1.1，未改动 |
| Funnel | 原 HTTPS 根路径仍代理 http://127.0.0.1:8000 |
| 本地 Backend health | status=ok，version=0.9.0 |
| 独立公网 health | HTTP 200，TLS verify=0，连接公共入口 103.84.155.153 |
| 本机公网出口 | 以太网，默认网关 192.168.8.1（查询公共入口 .217 的路由） |
| Backend → Agent health | HTTP 200，status=ok |
| Agent → Backend health | HTTP 200，status=ok |

主容器检查前后均 healthy、RestartCount=0，启动时间未变化：

| 容器 | 镜像 | StartedAt（UTC） |
|---|---|---|
| magicvvu-starter-backend-1 | magicvvu/backend:p72-units-736c2299edda | 2026-10-19T14:46:49.63851033Z |
| magicvvu-starter-agent-1 | magicvvu/agent:p72-units-755c1561abc8 | 2026-10-19T14:47:04.617674959Z |
| magicvvu-starter-db-1 | public.ecr.aws/docker/library/postgres:17 | 2026-10-15T02:53:50.959608619Z |

Backend 仍只发布 127.0.0.1:8000；Agent/DB 没有发布宿主端口。诊断前后未观察到服务中断；没有将离散检查表述成连续可用性监控。

## 3. 实际 netfilter 后端与规则顺序

没有仅依据 `iptables -S` 推断生效状态，已交叉检查：

- `iptables --version`、`ip6tables --version`：均为 v1.8.10 **(nf_tables)**。
- `/usr/sbin/iptables` 最终指向 `/usr/sbin/xtables-nft-multi`；update-alternatives 当前选择 iptables-nft。
- `nft -a list ruleset` 显示相同规则位于 `table ip filter`，INPUT 为 `hook input priority filter; policy accept`，首先 jump ts-input。
- IPv4 INPUT jump 的 nft handle 为 59；ts-input CGNAT DROP handle 为 69。handle 仅记录现场，后续不以可能变化的 handle 或行号执行删除。
- `iptables-legacy-save` 和 `ip6tables-legacy-save` 均成功且输出为空；没有发现另一套 legacy 规则。未执行 backend 切换。
- nft 全表检查未发现另外的 inet/netdev 基链抢先接受/丢弃本次主机 DNS 回包；现有 raw Docker 隔离规则目的地址为容器或 127.0.0.1:8000，不匹配此次发往宿主 172.19.29.17 的 DNS 回包。
- nft 提示相关表由 iptables-nft 管理，因此若获批，使用显式 **iptables-nft** 添加/删除规则，不混用 native nft 写入托管链。

当前 IPv4 INPUT 只有一条 jump，没有 DNS 专用例外；扫描完整 iptables-nft-save 也未发现两个 VPC DNS、source port 53 或 P8 DNS comment 的同类规则。

```text
-P INPUT ACCEPT
-A INPUT -j ts-input

-A ts-input -s 100.123.235.8/32 -i lo -j ACCEPT
-A ts-input -i tailscale0 -j ACCEPT
-A ts-input -p udp --dport 41641 -j ACCEPT
-A ts-input -s 100.115.92.0/23 ! -i tailscale0 -j RETURN
-A ts-input -s 100.64.0.0/10 ! -i tailscale0 -j DROP
```

两台 DNS 均属于 100.64.0.0/10；回包从 eth0 进入，不符合前四条例外，因而匹配 DROP。

完整规则、nft handle、原有计数器、网卡及解析状态已保存到本地：

`docs/versions/V1-P8.1/firewall-readonly-snapshot.json`

该文件是**只读审计快照**，不是已安装的备份服务，也不用于整体 iptables-restore；没有在服务器创建规则备份文件或持久化任何配置。

## 4. 少量受控 DNS 基线与抓包

09:30:53 对两台 DNS 各发起一次 UDP、一次 TCP 查询；域名均为公开的 `acme-v02.api.letsencrypt.org`，`+time=2 +tries=1`。TCP 内核出现正常 SYN 重传，不是额外爆破或负载测试。使用动态选定的本地源端口关联证据，没有增加监听服务。

| DNS | 协议 | 本地源端口 | dig 结果 | eth0 抓包 |
|---|---|---:|---|---|
| 100.100.2.136 | UDP | 40939 | timeout，exit 9 | 查询 ID 59927，收到完整 CNAME/A 响应 |
| 100.100.2.138 | UDP | 41744 | timeout，exit 9 | 查询 ID 36045，收到完整 CNAME/A 响应 |
| 100.100.2.136 | TCP | 37203 | timeout，exit 9 | 收到匹配 SYN 的 SYN-ACK，但握手未完成 |
| 100.100.2.138 | TCP | 43383 | timeout，exit 9 | 收到匹配 SYN 的 SYN-ACK，但握手未完成 |

关键抓包（仅指定 DNS IP、53 端口，未捕获用户业务内容）：

```text
09:30:53.792460 172.19.29.17.40939 > 100.100.2.136.53: 59927 A? acme-v02.api.letsencrypt.org
09:30:53.792762 100.100.2.136.53 > 172.19.29.17.40939: 59927 ... A 172.65.32.248
09:30:53.795199 172.19.29.17.41744 > 100.100.2.138.53: 36045 A? acme-v02.api.letsencrypt.org
09:30:53.795868 100.100.2.138.53 > 172.19.29.17.41744: 36045 ... A 172.65.32.248
09:30:53.799479 172.19.29.17.37203 > 100.100.2.136.53: SYN
09:30:53.799706 100.100.2.136.53 > 172.19.29.17.37203: SYN-ACK
09:30:53.779875 172.19.29.17.43383 > 100.100.2.138.53: SYN
09:30:53.780026 100.100.2.138.53 > 172.19.29.17.43383: SYN-ACK
```

抓包共 12 个报文，包括两对 SYN/SYN-ACK 重传。tcpdump 的“0 packets dropped by kernel”是捕获缓冲区统计，**不表示后续防火墙没有丢包**。

09:30:53 探测前与探测结束时，ts-input DROP 计数为：

```text
packets: 27917 → 27924
bytes:   2387857 → 2388486
```

该时间窗包含后台报文，不能将增量 7 全部归于四次探测；依据是实际规则顺序、匹配条件、相同查询/连接的回包已到达及应用超时。没有重置计数器来“隔离”数据。

## 5. conntrack 条件的只读核验

服务器未安装 conntrack CLI；**没有为诊断安装软件**。使用 Python 标准库向内核发送 NETLINK_NETFILTER / CT_GET dump 只读请求，在远端仅筛选此次本地源 IP、两个 DNS、目的端口 53 的 tuple 后输出，不更改或删除连接跟踪条目。

四个 tuple 均被内核跟踪，并在探测期间/结束时显示：

```text
status=394 (0x18a)
IPS_SEEN_REPLY=true
ASSURED=false
UDP: .136:53 ← local:40939; .138:53 ← local:41744
TCP: .136:53 ← local:37203; .138:53 ← local:43383
```

TCP 内部协议状态为 2（SYN_SENT），与用户空间未完成握手一致；**不能把 TCP 协议状态名称与 iptables conntrack 的 ESTABLISHED 分类混同**。本机内核头文件明确区分 IP_CT_ESTABLISHED_REPLY 和 IPS_SEEN_REPLY。已发出的查询/连接对应回方向报文具备预期的连接跟踪关系，支持仅接受 `--ctstate ESTABLISHED` 的回包方案；不需要放宽至 NEW、UNTRACKED 或整个源地址段。

阶段 B 现已补足实际命中验证：四条 `--ctstate ESTABLISHED` 规则均有正计数，UDP/TCP 均取得完整 DNS 应答。没有放宽状态、来源、接口或端口；详细计数与结果见第 8 节。

## 6. 获批后实际添加的四条临时规则

本轮独立标识前缀：`magicvvu-p81-20261020T0930`。执行前确认不存在；09:41:47 添加，09:42:26 删除，最终已不存在。

使用 iptables-nft，在 **INPUT 的 ts-input jump 之前** 插入；保留原 ts-input 和 CGNAT DROP。除用户限定的接口、源 IP、协议、源端口和状态外，额外限定当前宿主目的地址 `/32`，进一步缩小范围。只用于本次临时验证，不保证 DHCP 地址变化后适用。

实际脚本以参数数组执行了以下四条规则（SSH 内已为 sudo Python，因此命令与下列 sudo 表达等价）：

```bash
sudo -n iptables-nft -w 5 -I INPUT 1 -i eth0 -s 100.100.2.136/32 -d 172.19.29.17/32 -p udp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-136-udp -j ACCEPT
sudo -n iptables-nft -w 5 -I INPUT 1 -i eth0 -s 100.100.2.136/32 -d 172.19.29.17/32 -p tcp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-136-tcp -j ACCEPT
sudo -n iptables-nft -w 5 -I INPUT 1 -i eth0 -s 100.100.2.138/32 -d 172.19.29.17/32 -p udp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-138-udp -j ACCEPT
sudo -n iptables-nft -w 5 -I INPUT 1 -i eth0 -s 100.100.2.138/32 -d 172.19.29.17/32 -p tcp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-138-tcp -j ACCEPT
```

执行前已重新读取规则和地址，用同一完整规则规格 `-C INPUT ...` 查重，确认原 INPUT 只有 ts-input jump，地址/后端未变，原结构在基线测试后仍未变化。逐条添加并核对，记录四条成功清单；未删除或重排任何既有规则。脚本 finally 只按本次完整规格执行清理。

四次 `-I INPUT 1` 后显示顺序与命令顺序相反，但四条都在 jump 前，条件互不混淆。已用 `iptables-nft -S/-nvxL` 和 nft 实际 INPUT 规则交叉确认：新增规则 handle 为 76–79，原 jump handle 59 和 CGNAT DROP 保留。回滚未使用 handle 或数字行号。

风险：范围较小，但仍是生产 INPUT 策略变更，不能保证绝对无风险；仅信任两个指定 DNS 对已建立连接的回包，不开放 NEW 入站、SSH 或任何监听端口。INPUT ACCEPT 会提前终止当前 filter 链处理，因此必须保持上述精确限定，不能缩成只检查源 IP/53。现有 Docker NAT/FORWARD 链不改动。规则为临时状态，daemon 更新、规则重建或重启可能使其失效；本阶段不做持久化或重启实验。

## 7. 已执行的精确回滚与恢复验证

09:42:26 对四条成功新增规则按逆序执行了下列完整规格删除；不用数字行号、不 flush、不整体 restore、不切换 netfilter 模式：

```bash
sudo -n iptables-nft -w 5 -D INPUT -i eth0 -s 100.100.2.136/32 -d 172.19.29.17/32 -p udp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-136-udp -j ACCEPT
sudo -n iptables-nft -w 5 -D INPUT -i eth0 -s 100.100.2.136/32 -d 172.19.29.17/32 -p tcp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-136-tcp -j ACCEPT
sudo -n iptables-nft -w 5 -D INPUT -i eth0 -s 100.100.2.138/32 -d 172.19.29.17/32 -p udp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-138-udp -j ACCEPT
sudo -n iptables-nft -w 5 -D INPUT -i eth0 -s 100.100.2.138/32 -d 172.19.29.17/32 -p tcp --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment magicvvu-p81-20261020T0930-138-tcp -j ACCEPT
```

删除前用相同规格 `-C` 核对，避免误删其他规则。删除失败、出现重复或结构变化时停止并重新只读诊断，不批量清理未知规则。

验证回滚：上述标识在 iptables-nft-save/nft 中消失；INPUT 恢复原结构（同时尊重其他操作者的独立变更），原 ts-input DROP 仍在；SSH 新会话成功、三个容器 healthy、双向健康及公网 HTTPS 正常。无需为证明回滚而反复制造 DNS 故障，可少量复核并标明原 VPC DNS 阻断预计恢复；运行时 1.1.1.1 全程保持。

实际回滚状态：**四条全部移除，errors=[]，remaining_marker=false。** 以 `-C` 逐条确认不存在；完整 IPv4 iptables-nft 规则结构（忽略计数及生成时间）与本次操作前完全一致。原 ts-input 内容、运行时 DNS、Funnel JSON 配置及三容器启动时间/健康状态均与基线一致。09:42:42 另一条新 SSH 会话再次核验 iptables-nft 和 nft INPUT：只剩原 jump，没有临时规则。公网 HTTPS 再次 HTTP 200、verify=0。

移除后又对两台 DNS 的 ACME UDP/TCP 各一次，4/4 恢复原来的超时，这是预期的故障回归证据，不是系统 DNS 被切换。没有扩大规则范围，也没有为恢复 DNS 而擅自重加规则。

若 SSH 异常，使用用户预先确认可用的阿里云控制台/VNC 登录原实例，按本次成功插入清单执行精确删除，再复测服务。不能用重启、整体规则恢复或修改安全组替代精确撤销；这些均未授权。

## 8. 阶段 B/C 实测结果与证据

执行时每台 DNS 的 ACME、DeepSeek 域各做 UDP/TCP 3 次，共 24 次，单次超时 2 秒、只尝试一次、逐次间隔 250 ms，没有并发压测。成功判据同时要求 dig exit=0、NOERROR 和完整 A 记录，TCP 实际完成 DNS 查询/应答。未获用户提供的专有内部测试域，因此 **PrivateZone/内部专有域尚未验证**，未自行枚举或以通用域冒充租户私有域验收。

| DNS | 域名 | UDP | TCP | 本次命令墙钟耗时范围 |
|---|---|---|---|---|
| 100.100.2.136 | acme-v02.api.letsencrypt.org | 3/3 | 3/3 | UDP 27–38 ms，TCP 27–32 ms |
| 100.100.2.136 | api.deepseek.com | 3/3 | 3/3 | UDP 27–45 ms，TCP 39–54 ms |
| 100.100.2.138 | acme-v02.api.letsencrypt.org | 3/3 | 3/3 | UDP 16–39 ms，TCP 50–54 ms |
| 100.100.2.138 | api.deepseek.com | 3/3 | 3/3 | UDP 45–58 ms，TCP 43–44 ms |

耗时包含命令进程开销，不冒充纯 DNS 网络往返时间。解析仅验证域名，没有对 DeepSeek 发起付费请求。

09:41:54 四条 ACCEPT 规则的正命中计数：

| 规则后缀 | packets | bytes |
|---|---:|---:|
| 136-udp | 6 | 1044 |
| 136-tcp | 20 | 1832 |
| 138-udp | 6 | 1025 |
| 138-tcp | 21 | 1860 |

UDP 每条计数与其 6 次查询对应；TCP 包含握手/传输/关闭等报文，不应按单个包解释成单次 DNS 查询。原 CGNAT DROP 在整个测试期间持续保留，未更改 Tailscale 防火墙模式。

09:42:08，独立新 SSH 会话确认四条临时规则仍有效；同期本机使用正常 TLS 校验，从公共 Funnel 入口 103.84.155.217 得到 health HTTP 200、verify=0。原 SSH、Docker、tailscaled、resolved 均 active，临时有效期及回滚后 Backend↔Agent 双向 health 均 200，三个容器 healthy、启动时间未变、RestartCount=0。全程未触碰用户数据。

本次基线与“修改后”结果对照：

| 检查项 | 紧邻变更前基线 | 临时规则有效时 | 回滚后 |
|---|---|---|---|
| .136 UDP/TCP | ACME 各 1 次，均超时 | ACME/DeepSeek 各协议 3/3 | ACME 各 1 次，均超时 |
| .138 UDP/TCP | ACME 各 1 次，均超时 | ACME/DeepSeek 各协议 3/3 | ACME 各 1 次，均超时 |
| ACCEPT 规则 | 不存在 | 四条，均正命中 | 四条均不存在 |
| SSH / Docker / Tailscale / HTTPS | 正常 | 正常 | 正常 |
| 系统 eth0 DNS | 1.1.1.1 | 1.1.1.1 | 1.1.1.1 |

本地交付证据：

- `docs/versions/V1-P8.1/temporary-validation-run.py`：本次执行脚本；包含现场断言、逐条新增/核对、finally 精确清理及回滚验证。保存脚本不代表授权未来再次执行。
- `docs/versions/V1-P8.1/temporary-validation-execution.jsonl`：完整基线、24 次查询、命中计数、四次新增/四次删除及完成记录。
- `docs/versions/V1-P8.1/validation-summary.json`：基线 0/4 成功、临时规则 24/24、回滚后 0/4，最终 rules_removed=true、persistent_changes=false。
- `docs/versions/V1-P8.1/after-rollback-snapshot.json`：独立新 SSH 会话的规则、nft、DNS、Funnel、服务和容器结果。

本次操作最终退出码 0，09:42:36 记录 temporary_validation_passed=true。该结论仅表示本阶段最小临时修复和回滚试验成功，不是整体 P8 或生产永久配置 PASS。

## 9. 后续建议与待确认事项

本阶段已完成临时修复、逐协议验证和精确回滚，**建议下一步进入永久方案的设计与审批**，而不是直接切换系统 DNS。后续需解决回包例外在 tailscaled 重启/规则重建后的顺序与恢复、补足私有域核验，并独立审批持久文件、Netplan 应用及受控重启验收。短期 24 次成功不能证明长期或重启后稳定。

尚待额外确认/授权：

1. 永久防火墙/DNS 方案及实施窗口；本次临时验证授权已经用完，不自动转为常驻规则授权。
2. 如要验证 PrivateZone，提供一个可公开记录于报告、无敏感数据的内部测试域名和预期记录；当前明确标记未验证。
3. Backend 安全补丁部署、公网网关切换各自单独审批，不与本次 DNS 试验捆绑。

Backend 安全补丁部署、公网网关切换和永久 DNS 配置留待本阶段结束后分别安排；本轮不实施、不预先取得这些变更的授权。
