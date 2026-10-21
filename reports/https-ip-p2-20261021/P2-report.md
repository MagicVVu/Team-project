# MagicVVu 公网HTTPS IP接入：P2离线准备验收报告

日期：2026-10-21，Asia/Shanghai。运行环境检查约15:20–15:38，最终健康证据时间15:38:18。

**P2离线准备已完成；没有安装、启动或部署任何服务器入口，没有进入P3/P4/P5。**
本目录全部Nginx配置、安装步骤、备份、hook及systemd文件均为未来P3草案。
服务器继续保持P1无公网HTTP/HTTPS API入口的运行态。合规前置条件仍未确认。

## 1. 本阶段做了什么

- 阅读P1报告及对应证据，重新通过SSH校验当前状态。使用已有主机密钥、BatchMode、StrictHostKeyChecking=yes、UpdateHostKeys=no。
- 从**当前运行镜像**只读读取Backend 19份、Agent 70份Python源码，记录原始SHA256，过滤凭据字面量；未读取/导出环境文件内容或私钥。
- 解析实际main/router prefix组合，与loopback取得的运行OpenAPI比对：**38个API操作完全一致**。
- 核查会话认证、家庭/用户权限、内部服务认证和AI调用链；只读交叉核对Android main代码需要的API，未改Android。
- 生成30个“Method＋完整路径”白名单、两阶段Nginx配置、日志轮转、配置备份草案、证书/续期/监测及7种故障回滚方案。
- 本地静态验证通过；远端通过stdin做 `bash -n` 语法解析（不执行hook、不写服务器文件）。

## 2. 当前服务器状态及P1差异

| 项目 | P2复核 |
|---|---|
| Backend | `magicvvu/backend:p72-units-736c2299edda`，Healthy，127.0.0.1:8000→8000，unless-stopped |
| Agent | `magicvvu/agent:p72-units-755c1561abc8`，Healthy，8767仅容器内部，unless-stopped |
| Database | PostgreSQL17，Healthy，5432无宿主机发布，unless-stopped |
| Docker | active/running，enabled |
| `/api/v1/health` | 200，version=0.9.0，isolated_test=false |
| `/api/v1/ready` | 200，database=ok |
| 内网依赖 | Backend→`http://agent:8767`；Agent→`http://backend:8000`，均只输出scheme/host/port，不输出Token |
| Nginx / Certbot | 均仍未安装；80/443仍无监听；没有/etc/letsencrypt证书目录 |
| 软件渠道 | 官方Snap stable仍为5.8.0；未下载/安装软件 |
| 配置基线 | Compose/env哈希与P1完全一致；三容器镜像/绑定/重启策略无已发现变化 |
| 云防火墙 | 当前控制台规则仍未独立复核；本阶段未修改 |

安全端口结论来自当前宿主机监听和Docker发布配置：8000只在loopback，5432/8767没有发布。
P1公网TCP结果只作历史对照；本阶段没有新增真实手机/移动数据端口验收，不冒充完整公网安全证明。
资源容量引用P1快照，P2未做负载测试；不把“健康”解释成完整库存/AI业务回归通过。

## 3. 路由和安全审计结果

完整逐条清单：[route-security-audit.md](route-security-audit.md)，含method、完整路径、认证、功能、
Android决策、内部标记、AI标记、拟定超时和实际部署源码行号。

未来拟公开的30个操作涵盖：health；现有账号登录/登出、当前用户读取/名称修改；家庭创建/列表/重命名、成员/邀请/加入；
库存列表/添加/修改/调整/软删除；采购条目列表/添加/修改/删除/购买入库；AI消息/补充/任务/草稿；
执行能力、草稿执行状态/确认/取消以及本人操作回执。
后端Bearer、会话撤销/到期、家庭角色、成员关系、用户隔离与版本/幂等逻辑全部保留。
家庭库存原本按家庭共享，不误称同家庭成员也互相隔离。

必须阻断的已注册内部GET：

- `/internal/v1/inventory/search`
- `/internal/v1/inventory/batches/{batch_id}`
- `/internal/v1/operations/{operation_id}`

额外默认阻断 `/internal` 全部子路径、`/docs`、`/docs/oauth2-redirect`、`/redoc`、
`/openapi.json`、`/debug`、`/metrics`、`/admin`和未知路径/方法。
当前docs/redoc/openapi在loopback真实返回200，不能从环境开关或工作区新代码推断它们在线上已经关闭。

暂不公开且明确待确认：注册（开关当前关闭，未验证手机号注册）、ready（主机检查）、
reference-messages（保留接口固定503）、shopping-list元信息（无当前main调用）、consumption-events（仅测试调用）。
因此，**不声称注册或所有未来功能都能直接使用本白名单**；确认需要后只能逐条审查增加。

## 4. Nginx草案及参数

最终模板：[nginx-magicvvu-api.conf](nginx-magicvvu-api.conf)。它需要本目录common/map/snippet伴随文件，
不能单文件直接启用。初始模板：[nginx-magicvvu-http-only.conf](nginx-magicvvu-http-only.conf)。

| 项目 | 草案决策 |
|---|---|
| 代理目标 | 固定 `http://127.0.0.1:8000`，不改Compose、不重写API路径、保留query和Bearer |
| 默认拒绝 | 用大小写敏感的正则匹配Method＋Nginx规范化URI；30个操作外返回404；不使用宽泛API全放行 |
| TLS | TLS1.2/1.3；只引用生产lineage `magicvvu-ip`；无自签名/忽略证书验证方案 |
| 80 | 仅合法HTTP-01挑战文件GET/HEAD，其他404；不代理明文API、不重定向携带密码的请求 |
| 443 | 生产证书确认存在/可信后才装载最终站点；保留80挑战入口供续期 |
| 超时 | 上游连接3s、发送15s、普通读取20s、AI相关读取30s；不是全请求墙钟保证 |
| 请求体/缓冲 | 64KiB；请求缓冲开启（内存缓冲64KiB），响应缓冲关闭，代理响应不落临时文件；无已发现上传API |
| 中断与重试 | 客户端断开关闭上游连接；关闭代理自动重试。已提交业务不能假定自动回滚，仍按原操作ID恢复 |
| 头部 | 重新生成Forwarded相关头，清空外部内部身份头；不替客户端伪造认证 |
| 限流 | 登录每IP5次/分钟、全局10次/分钟，突发3；普通API每IP10次/秒突发30；总并发16；429 |
| 日志 | 仅时间、请求ID、固定方法/路由标签、状态、耗时、字节；无URI/Query/Header/Body/用户标识；原生请求error日志丢弃，防止错误消息带原始URI |
| 轮转 | 专属 `/var/log/magicvvu-nginx/access.log`，daily、7份、10M触发条件、压缩；P3检查logrotate调度，maxsize仅在调度运行时判断，不是实时硬上限 |

当前AI链路有：Agent operation总预算10s、模型非流式且10s墙钟约束、内网工具读取5s，
Backend网关连接3s及httpx分阶段13s；还存在数据库/序列化开销，不能把13s直接作为全链路上限。
Android当前读取20s可能先于Nginx AI30s超时，P4应专门审查。

请求级Nginx error日志丢弃是有意的隐私取舍，保留脱敏access状态/耗时和服务启动诊断；
若以后需要错误细节，必须先实现脱敏，不临时开启debug收集真实凭据。
Backend原有访问日志另有记录URL/query的可能，P2未改变它；凭据不得放URL，分享日志前需脱敏。

## 5. 证书、续期与访问限制

[certificate-plan.md](certificate-plan.md)给出已核实的准确参数、Staging隔离目录、正式lineage、
IP SAN/链/有效期校验、生产hook、自带timer检查、dry-run与加载指纹验证及故障阈值。
官方5.8支持IP＋webroot及required shortlived；证书160小时。默认保留Snap自带两次/日调度，
安装后必须实查enabled/active及实际行为；模拟续期不能冒充真实新证书轮换。

P1正式ACME曾出现TLS握手超时，后续成功不证明长期可靠。设计有界GET重试、下单失败停止诊断、
到期48h/24h/12h阈值、小时监测及hook指纹核验；故障通知渠道仍待用户确定，尚无已启用告警。
本阶段HTTPS状态：**未启用**；证书有效期：**不存在**；自动续期：**尚未部署**。

[access-control-options.md](access-control-options.md)对比A/B/C，推荐C的轻量形式：
独立测试账号＋既有Bearer＋HTTPS＋精确路由＋登录限流＋注册关闭。
它不会只允许该账号或绑定这一台设备；其他现有有效账号仍可登录。
动态手机出口/CGNAT使白名单不稳定，且IP不是设备身份，不默认实施；更严格mTLS留待另行批准。

## 6. 本阶段验证与证据

| 验证 | 结果/限制 |
|---|---|
| 运行schema vs 部署AST | 38个操作集合一致，含完整prefix |
| 白名单覆盖 | 30个拟公开操作命中；3内部＋5暂不公开操作不命中 |
| 否定样例 | 28种方法/内部/文档/未知/编码路径样例通过Python静态模型检查 |
| 日志及阶段静态检查 | 未引用危险日志变量；HTTP-only无proxy/TLS/443；固定loopback上游及关闭自动重放 |
| Python草案 | AST语法检查通过；未执行服务器备份/监测 |
| Shell hook | `bash -n`通过，仅语法解析，无hook执行或reload |
| 真正Nginx验证 | **未执行nginx -t**，因为未安装Nginx；实际PCRE/URI规范化/代理/限流/日志行为待P3 |
| 业务与手机 | 未登录写入、未调用AI推理、未改库存、未做Android真机/断电脑/重启验收 |

静态URI模型不等于Nginx，部署后必须使用真实Nginx做编码/路径/方法否定测试。
日志和hook安全设计还需P3动态验证，不将“草案已生成”描述成“线上安全已验收”。

关键证据：`P2-runtime-audit.json`、`P2-runtime-routes.json`、`P2-health-entrypoints.json`、
`P2-final-health.json`、`route-inventory.json`、`P2-offline-validation.json`、`P2-shell-validation.json`。

## 7. 修改文件、重要命令与回滚

本阶段仅新增本地 `reports/https-ip-p2-20261021/`：本报告、用户要求的另外5份文件、
访问限制对比、配置伴随文件、只读采集/本地生成与验证脚本、P3备份/hook/监测草案、证据及脱敏运行源码快照。
没有修改现有Backend/Agent/Database/Android/Compose/env或Git分支；没有提交Git。

重要已执行命令族：SSH `sudo -n python3 -`（只读stdin脚本）、筛选Docker inspect、
`ss -lntp`、`systemctl show/list-timers`、dpkg-query、snap info、文件元数据/哈希、
`docker exec ... python -B -c`读取源码、loopback健康/schema/docs/未认证users-me GET、
Agent内网health GET、本地 `build_route_policy.py`/`validate_offline.py`、stdin `bash -n`。
运行时没有导入应用模块，没有执行P3命令或backup/hook/monitor草案。

备份与七类回滚见 [rollback-plan.md](rollback-plan.md)：root限制目录保存权限/owner/链接/存在性与服务基线，
按精确变更清单恢复Nginx，通过nginx -t才reload；首次失败无可用入口前版时关闭本任务Nginx，恢复P1无80/443入口，
继续保留三个业务容器和数据卷。软件包痕迹可能保留，不宣称字节级系统还原。
P2无服务器改动，因此本阶段不需要服务器回滚。

## 8. 十项验收问题与P3门槛

| 问题 | 答案 |
|---|---|
| 1. 需要公开哪些API？ | 当前App调用证据支持的30个操作，详见完整路由表 |
| 2. 禁止哪些内部API？ | 3个内部GET及整个internal；文档/调试/管理/未知路径一律拒绝 |
| 3. Nginx是否准备完成？ | 离线草案及伴随文件完成；真实nginx -t、TLS和转发验证未执行 |
| 4. Docker架构要改吗？ | 不需要，不改端口、网络、业务代码和数据库权限 |
| 5. 如何申请续期？ | 官方Snap，IP＋webroot＋required shortlived，Staging隔离后正式签发，自带timer＋语法验证reload hook＋加载指纹检查 |
| 6. 哪些步骤开放公网？ | P3启动HTTP-only首次开放80；正式证书后reload最终模板开放443/API；P2无此操作 |
| 7. 失败如何回P1？ | 按检查点恢复或关闭本任务Nginx入口，核对3容器及loopback健康/端口/配置哈希，不重建不清卷 |
| 8. P3需提前确认？ | 单独批准、合规已处理、云防火墙当前规则、ACME邮箱/条款、测试账号、白名单例外和告警渠道 |
| 9. 尚存安全风险？ | 当前登录无已接入账号级限流、移动出口共享、其他合法账号仍可登录、网络间歇性、告警未落实、动态验证未做；详见审计 |
| 10. 可进入P3吗？ | **离线技术准备可提交P3审阅；尚不具备无条件直接上线的前提。** 门槛确认且P3明确批准后才执行；安装后验证失败则停止 |

另两个已识别的业务限制必须保留：当前Android debug构建要求isolated_test=true，而服务器为false，
仅换Base URL仍会在写操作前（包括登录）被阻止，需P4专门测试构建方案，不改服务器生产隔离标志；
Agent存在可选planning/context依赖而当前Backend未注册，按代码会降级，P2不补业务代码、不声称完整AI规划通过。

**本阶段停止，等待用户审批P3。P3审批不包含P4/P5或服务器重启授权。**
