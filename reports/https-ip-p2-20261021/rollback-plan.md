# P2：P3配置备份和回滚方案（未执行）

## 备份草案和执行保护

`backup.DRAFT.py` 是服务器root用的P3草案。默认拒绝执行；必须在P3获批后明确传
`--execute-p3-authorized --label <检查点>`。P2只做语法检查，没有在服务器执行它。
它不读取数据库业务记录、不做dump、不接触Docker Volume数据，也不会停止任何容器。

未来用法（不要在P2执行）：

```bash
sudo python3 backup.DRAFT.py --execute-p3-authorized --label before-install
# 安装后、配置修改前再建立after-install；之后before-https、before-renewal各建一个
```

输出仅为 `/root/magicvvu-https-backups/<UTC微秒>-<label>/`。目录root专有0700，
内含 `files/` 原文件（cp -a --parents保存owner/mode/时间/链接）、`before.json`（元数据、
存在性、原服务状态、软件版本、监听、3个容器ID/镜像/端口/重启策略）、
`created-files.txt`、`changes.jsonl` 和成功标记 `COMPLETE`。
`.env`、证书私钥和ACME账号只在root限制目录保留；不导出到电脑/Git，不输出内容。
没有COMPLETE的备份不能作为下一步变更的前提。

修改日志：每次写入前已有检查点，记目标原始哈希/类型/不存在状态；写入成功后记录新哈希/链接目标、时间、所用检查点。
新建清单仅记录**实际创建**的绝对路径，不把所有计划路径当作已创建。每次安装包后的软件新增文件另用dpkg清单记录，
不要将包文件与本任务手工创建文件混为一谈。若原配置或镜像ID与P2基线不同，停止重新审计，不能覆盖他人修改。

## 文件范围

| 原始/拟改路径 | 备份与回滚策略 |
|---|---|
| `deploy/compose.yaml`、`deploy/.env`（项目根 `/srv/magicvvu/magicvvu-starter`） | 只保留原始基线/备份，部署不修改；验收哈希必须与P1/P2一致，不因回滚重建容器 |
| `/usr/sbin/policy-rc.d` | 包安装前记录存在性/权限；仅在原来不存在时临时创建禁止包自动启动的策略；安装后删除需校验仍为本次内容；已有策略则先审阅，不覆盖 |
| `/etc/nginx/` | 安装前记录不存在，安装后首次改配置前整体cp -a快照；恢复时仅替换本次实际改动文件，不清空整个目录 |
| `conf.d/00-magicvvu-common.conf`、`sites-available/magicvvu-api`、`sites-enabled/magicvvu-api`、3个 `snippets/magicvvu-*.conf` | 上述均位于/etc/nginx；记录创建清单/哈希或symlink目标；存在则按相应检查点恢复，不存在则只撤销本任务新增项 |
| `/etc/nginx/sites-enabled/default` | 若安装引入，先记录/备份链接再禁用；恢复默认站点只能在Nginx已停止且不会重新公开默认网页的状态进行 |
| `/etc/logrotate.d/magicvvu-api` | 先备份同名项；仅本次新建则删除它，不触碰其他日志策略 |
| `/var/log/magicvvu-nginx/` | 新建目录和access.log只记创建清单/权限，不把日志当配置备份；停用入口后保留用于审计，不默认删除历史日志 |
| `/var/www/magicvvu-acme/` | 单独备份既有内容（如有），仅清理明确记录的本次探针/挑战文件；不递归删除不明目录 |
| `/etc/letsencrypt/`、`/var/snap/certbot/common/`、`/root/magicvvu-acme-staging/` | 存在时整体安全快照（含archive/live/renewal/accounts及链接）；不默认撤销证书或删除谱系，防止破坏后续恢复 |
| `/etc/letsencrypt/renewal-hooks/deploy/50-magicvvu-nginx` | 首次HTTPS可用后单独快照再安装；回滚恢复前版或移除本次hook，不影响其他证书hook |
| `/usr/local/sbin/magicvvu-cert-monitor`、对应systemd service/timer及enable链接 | 安装前记录，回滚恢复前版/撤销本次任务；证书仍被HTTPS使用时，不能先停续期和监测 |
| Snap续期timer/service（及如有drop-in） | 记录安装前/后实际状态和内容；本方案优先用自带timer，不默认覆盖vendor unit、不增加重复cron |

恢复文件时使用确定的检查点路径和 `cp -a --remove-destination -- <已核对备份文件> <精确目标>`，
目录恢复必须逐项审查；不要用会清理未知文件的rsync --delete、rm -rf或递归覆盖。
符号链接先核对当前仍与变更记录相符，再撤销本任务链接并按备份恢复。
若当前哈希不是“本次写入后哈希”，停止，避免覆盖并发变更。

## 七种故障处置

| 故障 | 处置及恢复验证 |
|---|---|
| Nginx安装失败 | 保留禁止自动启动措施直到确认无80/443监听；检查dpkg状态，停止继续安装/签发；若本次Nginx意外启动且确认未服务其他用途，停止该Nginx。按原始记录恢复临时policy-rc.d，记录包残留。业务Docker不动 |
| HTTP-01失败 | 不签正式证书，不打开443；核对云防火墙、Host、探针路径、文件权限和外部GET。确认本次HTTP-only入口可留作诊断或停止Nginx恢复P1无80/443监听；不改云规则绕过失败 |
| Staging/正式签发失败 | 停止重新下单；分类网络/验证/限额/profile问题，保留受限证据；不装自签名、不加载Staging；保持HTTP-only或关闭入口。第一次没有正式证书时绝不加载443模板 |
| Nginx语法错误 | 不reload；运行进程仍服务之前版本。恢复本次改动的配置文件/链接，重新nginx -t通过才reload。若从未启动则保持停止，不以重启业务容器解决 |
| HTTPS通但API异常 | 先核对loopback health/ready与日志固定标签；保留Bearer/path/query原样。若本机正常而代理异常，恢复上一版已验证入口；首次上线没有可用前版时撤回到HTTP-only（只挑战，无明文API）或停止Nginx |
| 自动续期/hook失败 | 旧证书仍有效则保持服务并诊断，检查renew Result、到期时间、当前/磁盘指纹。修复hook/配置后语法验证；不要每分钟force-renew。即将或已经过期且无法恢复时关闭API，保留HTTP-only验证能力；内网业务继续 |
| 发现内部接口被公开 | 立即关闭本任务公网入口（停止Nginx或撤回已验证HTTP-only），再修正默认拒绝策略、进行所有内部路径及编码变体否定测试；不能只依赖内部token来接受已发生的暴露。检查日志/凭据是否泄露，若需要轮换由用户单独授权；未经允许不重置账号/改业务环境 |

## 首次部署退回P1运行态（未来操作步骤）

1. 核对before-install的COMPLETE、nginx原先不存在/未运行及本次创建清单，确认没有其他人新增Nginx用途。
2. 对本次Nginx `systemctl stop nginx`，验证80/443不监听，再 `systemctl disable nginx` 防止重启误启动；不停止Docker。
3. 撤销仅本任务新建的站点链接；恢复精确的原配置/临时安装策略，保留新证书在root受限目录。
4. 确认Nginx不再依赖本次证书后，才停用本次新增监测或恢复本次变更的续期状态；不影响其他证书调度。
5. 对照容器ID、镜像、端口、unless-stopped，检查3容器Healthy；GET loopback health/ready均200；比对compose/env哈希。
6. 从公网观察22正常、8000/5432/8767不可连接，HTTP/HTTPS无业务入口；云规则本任务未改，无需改回。

此方案恢复的是P1**无公网入口且业务容器健康的运行态**。新安装软件/包管理记录可能保留；
不把这说成字节级系统还原。不自动purge/autoremove、不清理证书/数据库卷。
若用户要求卸载本次新装软件，再对照安装前后清单逐包处理并单独审查依赖。

## P2实际回滚需求

本阶段没有服务器变更，服务器无需回滚。只新增本地报告/草案；没有执行本节任何恢复命令。
