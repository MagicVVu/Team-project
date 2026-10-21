# MagicVVu 公网 HTTPS IP 接入：P1 只读检查报告

审计时间：2026-10-21 15:09–15:13，Asia/Shanghai（证据使用 UTC）。

## 结论与阶段边界

**P1 只读审计完成。现有业务服务健康，当前没有公网 HTTPS API 入口。未进入 P2/P3/P4/P5。**

通过现有 SSH alias `magicvvu` 连接 `admin@8.134.172.165`，强制校验既有主机密钥，禁止自动更新 known_hosts。主机名 `iZ7xvftxzwe1mwbso1ovyyZ`，Ubuntu 24.04.5 LTS，项目目录存在。无密码、Token、私钥、环境变量值出现在报告或证据中；Compose 的插值结果只在远端内存中筛选，未导出完整配置。

未安装软件、创建服务器配置或备份、启用监听、注册 ACME 账号、请求 Staging/正式证书、修改防火墙/SSH/业务数据、重启或停止容器。SSH、健康检查和只读查询可能产生系统正常的访问日志及缓存；没有主动更改部署配置。

合规前置条件仍待用户向阿里云确认。单台手机内部测试不能据此推定免除 ICP/App 备案义务。用户明确确认合规条件已处理前，不启用公网 API、不正式签发证书；P2 若获批也受此约束。

## 十项检查结果

| 检查 | 当前实测结果 | 后续影响 |
|---|---|---|
| 1. Nginx | PATH 和 dpkg 均未发现安装；服务 inactive/dead；未发现 `/etc/nginx/nginx.conf` 及常规配置文件 | 无现存 Nginx 配置需要迁移；目前无法运行 `nginx -t` |
| 2. Certbot | PATH、dpkg、Snap 均未发现已安装 Certbot | 尚无可用的本机 Certbot 版本 |
| 3. 可信来源 | snap/snapd 2.76.3，socket enabled/active；无已安装 snap；`snap info certbot` 成功，发布者 Certbot Project（已验证），stable **5.8.0** | 当前 apt 缓存 Certbot 候选 **2.9.0-1**，不符合本任务 >=5.4；不采用它申请 IP 证书。Snap 元数据可达不等于已验证完整安装包/CDN下载 |
| 4. 80/443 | `ss` 无 IPv4/IPv6 监听；开发电脑公网 TCP 连接均被拒绝 | 当前无 HTTP/HTTPS 服务；不能据此证明阿里云规则已放行 |
| 5. Compose | 运行态和指定 compose/env 解析结果一致：Backend `127.0.0.1:8000→8000`；Agent/DB 无宿主机端口发布；三者 `unless-stopped` | 原有网络满足本机反代架构，无需修改 Compose |
| 6. Backend 本机 API | `GET /api/v1/health` HTTP 200，status=ok、version=0.9.0、isolated_test=false；`GET /api/v1/ready` HTTP 200，database=ok | 已验证 `127.0.0.1:8000` 可用 |
| 7. 证书与续期 | 常规 `/etc/letsencrypt`、`/var/snap/certbot/common`、root/home ACME 路径等未发现证书部署；systemd timers/unit-files、cron 和本地 unit 扫描未发现 Certbot/ACME 续期任务 | 当前无可报告的 HTTPS 证书有效期、续期 timer 或 reload hook；未执行续期模拟 |
| 8. 资源 | 内核可见内存 **1613 MiB**，available **989 MiB**；swap 2047 MiB，使用 0；根盘 40G，空闲 **30G**，使用21%；inode使用7%；低负载 | 当前资源足以准备轻量 Nginx/Certbot；非并发负载测试结论。实际可见内存低于标称2GiB，以上为实测 |
| 9. 服务健康 | Docker active/running、enabled；Backend/Agent/PostgreSQL running/healthy，重启计数均0；DB `pg_isready` 接受连接 | 不需要触碰现有容器；历史测试容器存在但已退出，未清理 |
| 10. 验证网络 | DNS可用；Staging ACME 两次 HTTPS 200、TLS验证通过；正式 ACME 首次 TLS连接超时，后续两次200、TLS验证通过；Snap Store、Ubuntu HTTPS站点和配置中的阿里云apt镜像可达；NTP已同步 | 存在瞬时网络不稳定证据；不能保证签发/续期可靠。P3前需再次核查，不在P1尝试挑战验证 |

健康接口执行前，已读取**当前部署容器**中的对应函数源码：health 返回状态；ready 只执行 `SELECT 1`。本次未调用登录、注册、库存写入、AI消息/草稿提交等业务API。Agent 健康结论来自 Docker health 状态，未调用 AI 推理功能；库存与 AI 完整业务回归留待授权阶段。

## 容器、网络与公网端口

| 服务 | 当前镜像 | 网络 | 重启策略 | 健康 |
|---|---|---|---|---|
| Backend | `magicvvu/backend:p72-units-736c2299edda` | default + ai_net | unless-stopped | healthy |
| AI Agent | `magicvvu/agent:p72-units-755c1561abc8` | ai_net | unless-stopped | healthy |
| PostgreSQL | `public.ecr.aws/docker/library/postgres:17` | default | unless-stopped | healthy |

Docker 29.9.0，Compose v5.6.0。数据库现有卷为 `magicvvu-starter_postgres_data`；本任务不修改、不删除、不恢复覆盖该卷。Agent 现有缓存卷和宿主机绑定目录也保持原状。

| 端口 | 宿主机实测 | 开发电脑公网 TCP 实测 |
|---|---|---|
| 22 | `0.0.0.0:22`、`[::]:22`，sshd | 成功，SSH可用 |
| 80 | 未监听 | Connection refused |
| 443 | 未监听 | Connection refused |
| 8000 | 仅 `127.0.0.1:8000` | 5秒超时，不可连接 |
| 5432 | 无宿主机监听/发布 | 5秒超时，不可连接 |
| 8767 | 无宿主机监听/发布 | 5秒超时，不可连接 |

UFW inactive。iptables 有 Docker规则，包含针对非loopback进入 `127.0.0.1:8000` 的 DROP，DNAT目标限定127.0.0.1。未修改这些规则。上述公网结果只代表本次开发电脑网络这一观察点，不替代移动数据网络验收，也不等价于云端防火墙策略证明。

**阿里云轻量防火墙当前规则未独立复核**：本次使用SSH，未取得云控制面只读会话/API。用户提供的22/80/443放行信息仍属历史输入。后续启用HTTP-01前需要核对控制台；本次没有登录控制台或修改云规则。

## 后续配置应考虑的已发现事项（仅规划）

- 当前部署代码发现 `/internal/v1/operations/{operation_id}`，后续 Nginx 应优先阻断整个 `/internal/`，并核对 docs/openapi/debug/metrics 等路由；不能使用无条件透传全部路径的配置。路由元数据包含 router 局部路径，不能直接作为完整公开路径白名单，P2需拼接prefix并核对。
- 部署Backend的 `app` 源码扫描未发现 `StreamingResponse`、`text/event-stream`、`WebSocket` 字面标记；Agent网关发现 `httpx.Timeout(13.0, connect=3.0)`。这是静态扫描，不是对动态行为和全部Agent内部依赖的证明。P2仍需复核AI请求链后确定超时、缓冲和请求体限制。
- 不能在没有有效证书文件时启用引用 `fullchain.pem/privkey.pem` 的443配置。准备阶段可以生成本地草案和本机验证方案；合规门槛未满足时不能由草案转为公网API。
- 当前没有可检查的Nginx访问日志。后续日志格式应避免请求体、Authorization、Cookie、完整带query的请求行及敏感Token；采用不含query的URI等必要字段。
- Let's Encrypt 官方文档确认 webroot IP证书需要Certbot >=5.4，参数为 `--ip-address` 和 `shortlived` profile；证书有效期160小时。需要手动装载及成功续期后先 `nginx -t` 再reload。P1仅核实资料与网络，没有执行申请。[Certbot IP证书官方说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)、[证书profile官方说明](https://letsencrypt.org/docs/profiles/)。

## 配置备份及恢复方案（尚未执行）

所有服务器写入均待对应阶段获批后进行。未来每次修改前，以UTC时间创建 `/root/magicvvu-https-backups/<UTC>/`，root:root、0700；用 `cp -a --parents` 保留文件、链接、owner、mode。受限目录内保存 `sha256sum`、文件存在/不存在清单、服务原始enabled/active状态、软件安装前版本和本阶段新增文件清单。`.env` 备份仅留服务器root受限目录，不传回电脑、不提交Git、不打印内容。若发现原文件较P1基线变化，重新审计并备份当时版本，不覆盖他人改动。

| 文件/目录 | P1状态与未来计划 | 恢复方式 |
|---|---|---|
| `/srv/magicvvu/magicvvu-starter/deploy/compose.yaml` | 存在，root:root 0660；本任务预计无需修改，仅纳入基线备份 | 若确被本任务修改，才按备份恢复文件；不得因此运行down/up或重建容器 |
| `/srv/magicvvu/magicvvu-starter/deploy/.env` | 存在，uid/gid1000，0660；预计无需修改，仅安全备份 | 如确被本任务修改，保留owner/mode恢复；不输出敏感内容、不自动重启业务 |
| `/etc/nginx/nginx.conf` | 目前不存在；安装后、首次修改前重新做完整基线备份 | 恢复安装后已验证基线，或在卸载入口前停用本次新增站点；不盲目覆盖整目录 |
| `/etc/nginx/sites-available/magicvvu-api` 及对应 `sites-enabled` 链接 | 拟新增，准确名称待P2 | 删除仅本次新增的文件/链接；若同名项后来存在，先备份再决定，不覆盖 |
| `/etc/nginx/sites-enabled/default` | 当前无配置；软件安装可能引入，需先记录 | 按本次修改前链接/存在性恢复；不能因安装而意外暴露默认站点 |
| `/etc/nginx/snippets/magicvvu-api-proxy.conf`、`/etc/logrotate.d/magicvvu-api` | 可能新增；是否需要待P2 | 仅恢复/移除本次文件，不影响系统其他配置 |
| `/var/www/magicvvu-acme/.well-known/acme-challenge/` | 拟新增验证目录，P1未创建 | 清理仅本次创建的挑战文件/目录；无业务文件可删 |
| `/etc/letsencrypt/`、`/var/snap/certbot/common/` | 当前不存在；P3安装/签发/续期配置会产生 | 首次不存在也要记入清单；后续修改前备份整个证书谱系、账号/续期配置及链接，root受限保存；不删除已有谱系或吊销证书作为默认回滚 |
| `/etc/letsencrypt/renewal-hooks/deploy/*` | 拟新增reload hook | 恢复旧hook或删除本次新hook；只在语法验证通过后reload |
| `/etc/systemd/system/<实际续期unit>` 与enable链接 | 当前无证书续期任务；若使用Snap自带timer，以安装后实测unit为准 | 记录原始状态，停用/恢复仅本任务新增或修改的调度；有有效HTTPS依赖时不得先停续期 |

已记录compose/env的元数据和SHA256于 `P1-server-audit.json`，不把哈希当作文件备份。P1没有创建服务器端真实备份，也没有数据库dump或恢复演练；这不是后续改变数据库的授权。

后续故障回滚顺序：

1. 保留Backend、Agent、PostgreSQL及其卷运行；不运行 `docker compose down`、不重建、不清卷、不重启服务器。
2. 有前一版可用Nginx配置时，精确恢复本次改动的文件/链接，执行 `sudo nginx -t`；成功后 `sudo systemctl reload nginx`。若语法不通过，不reload，保留当前运行进程并报告。
3. 本次P1原始状态为没有Nginx服务；若首次部署失败且没有前一版可用入口，停用本任务新增Nginx入口/服务，恢复到80/443不监听。不要为此停止任何业务容器，也不为回滚自动卸载或purge软件。
4. Nginx不再依赖本次证书后，才恢复/停用本次新增调度与hook；证书私钥和ACME账号保留在root受限目录，不提交Git、不对外展示。
5. `ss -lntp`、筛选后的Docker端口与健康状态、两个已确认只读健康GET复验，确认127.0.0.1:8000可用，5432/8767无发布，输出故障原因及恢复结果。

## 重要已执行命令

以下列出主要命令族；实际审计脚本随报告提供。原始 `docker inspect` 和完整插值Compose结果只在远端进程内处理，证据仅保留允许字段，不直接输出所有内容。

```text
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no ... magicvvu
sudo -n python3 -                        # 脚本经stdin执行，未写入服务器
ss -lntup
systemctl show docker/nginx/snapd/snapd.socket ...
dpkg-query -W ...; apt-cache policy nginx certbot snapd
snap list; snap version; snap info certbot; snap changes
docker --version; docker compose version
docker inspect ...                      # 仅输出健康、端口、重启策略等允许字段
docker compose --env-file .../deploy/.env -f .../deploy/compose.yaml config --format json
docker stats --no-stream; docker system df
docker exec ...backend-1 python -c ...   # 读取当前源码并做AST检查，不导入运行app
GET http://127.0.0.1:8000/api/v1/health
GET http://127.0.0.1:8000/api/v1/ready
docker exec magicvvu-starter-db-1 pg_isready -h 127.0.0.1 -p 5432
free -m; df -h; df -i; timedatectl show ...
systemctl list-timers --all; systemctl list-unit-files
ufw status verbose; iptables-save; ip6tables -S INPUT
getent ahostsv4 <ACME/Snap/Ubuntu主机名>
curl --noproxy '*' --connect-timeout 5 --max-time 10/12 ... <公开ACME directory等URL>
```

所有HTTPS网络探测保留默认TLS验证；没有 `-k`、没有降级ACME到HTTP。阿里云apt镜像的HTTP GET仅检查现有源Release文件可达，未下载/安装软件，也不能将其 `tls_verify=0` 解释成使用了TLS。

## 本地交付、未完成项与验收状态

仅新增本地目录 `reports/https-ip-p1-20261021/` 下文件，未改现有业务代码或配置，未提交Git：

- `P1-report.md`：本报告。
- `audit_readonly.py`、`verify_readonly.py`：经SSH stdin执行的只读审计脚本。
- `P1-server-audit.json`：系统、容器、端口、软件、证书和首次网络审计。
- `P1-verification.json`：健康接口、官方Snap元数据、ACME复测和最后容器健康。
- `P1-public-ports.json`：开发电脑公网TCP探测，明确标注非Android移动数据测试。

HTTPS入口：未启用。证书到期/自动续期：尚无证书或任务。Android真机/断电脑/业务写入/用户隔离验收：P1未执行，不能宣称完成。服务器重启：未执行，后续仍需单独批准。

待解决：合规前置条件确认；云防火墙当前规则复核；ACME正式端点间歇性连接超时；Snap完整软件包下载与安装可用性；P2内部路由阻断及AI链路配置复核；P3证书和自动续期部署；P4/P5客户端与真机验收。

**本阶段到此停止，等待用户明确批准P2。批准P2不自动批准P3/P4/P5，也不替代合规前置确认。**
