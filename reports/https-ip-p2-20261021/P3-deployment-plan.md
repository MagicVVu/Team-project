# P3具体操作计划（草案；P2中全部未执行）

## 开始前必须具备

- 用户明确批准P3并确认广州服务器ICP/App备案适用前置条件已处理。P2批准不包含这些授权。
- 用户重新确认阿里云轻量防火墙的22/80/443及来源规则，8000/5432/8767不放行；需要改云规则则另行授权。
- 提供ACME联系邮箱并确认CA条款；确认使用既有专用测试账号，账号没有则单独授权测试账号准备，不擅自注册/重置。
- 同意当前精确白名单30个操作；注册、ready、reference-messages、shopping-list元信息、consumption-events暂不公开。
- 确认续期故障通知接收方式。只写服务器journal不能保证用户及时收到告警。
- Android调试目标策略与服务器isolated_test=false冲突留P4按专门构建解决，不在P3改服务器隔离标志或业务代码。

## 0. 复核与配置备份

只读复核3个镜像ID/容器ID、health、loopback、8000绑定、80/443、软件安装状态、compose/env哈希。
有变化则停止审查，不将P2草案盲目应用到新状态。
将**经过复核的配置/脚本白名单**传入服务器root专属准备目录，校验本地SHA256；不上传运行源码快照或任何私钥。
执行 `backup.DRAFT.py --execute-p3-authorized --label before-install`，检查COMPLETE和清单；
当前业务数据不备份、不修改，不能将配置备份误当数据库恢复点。

## 1. 安装软件，但先不开放入口

1. 核对 `/usr/sbin/policy-rc.d` 是否存在；有既有策略则停止审阅，不覆盖。
   原来不存在时，经备份后临时以root 0755创建返回101的policy-rc.d，阻止包安装自动启动服务。
   该窗口可能影响同次包操作的其他服务，因此不并行执行其他系统维护。
2. `sudo apt-get update`，然后 `sudo env NEEDRESTART_MODE=l apt-get install --no-install-recommends nginx`。
   不做全系统upgrade，审查包事务不得升级/重启Docker或业务服务；若拟涉及则停止。
3. `systemctl is-active nginx`、`ss -lntp`确认没有意外启动；安装引入default站点先记录后撤销enabled链接。
   安装后的Nginx先保持disabled/inactive。核对临时policy仍为本次内容，恢复其原始不存在状态。
4. `sudo snap install --classic certbot`；检查 `/snap/bin/certbot --version` >=5.4（期望5.8.0）和 `--help all` 中所用参数。
   软件安装会改变运行环境，须在P3中明确执行并记录，不能在P2提前做。
5. 建立after-install检查点；记录Snap实际timer/service、版本、nginx `-V`及完整include关系，注意不要导出敏感配置。

## 2. 安装HTTP-only配置并验证（首次开放80）

| 本地草案 | 未来服务器目标 |
|---|---|
| `nginx-http-common.conf` | `/etc/nginx/conf.d/00-magicvvu-common.conf`（http上下文） |
| `nginx-route-map.conf` | `/etc/nginx/snippets/magicvvu-route-map.conf`（只能在map内include） |
| `nginx-http01-server.conf` | `/etc/nginx/snippets/magicvvu-http01-server.conf`（http上下文server） |
| `nginx-proxy-common.conf` | `/etc/nginx/snippets/magicvvu-proxy-common.conf`（location上下文） |
| `nginx-magicvvu-http-only.conf` | `/etc/nginx/sites-available/magicvvu-api`（初次内容） |
| 同名站点软链接 | `/etc/nginx/sites-enabled/magicvvu-api` |
| `logrotate-magicvvu-api.conf` | `/etc/logrotate.d/magicvvu-api` |

检查所有同名目标不存在或已被备份，配置root:root 0644，链接记录原目标。
新建 `/var/log/magicvvu-nginx`（root:adm 0755）、access.log（www-data:adm 0640），
以及root拥有的0755 Webroot/挑战目录；逐一登记新建清单。
专用日志目录避免Ubuntu默认 `/var/log/nginx/*.log` 轮转规则重叠，仍需核查所有现存规则。

HTTP-only没有proxy_pass和TLS证书引用。执行 `sudo nginx -t`，成功后再 `sudo systemctl start nginx`；
此时才真正开放80。验证无443监听，HTTP API均404、仅合法挑战文件GET/HEAD可读。
从公网网络而非loopback验证独立探针200和内容；阿里云多视角HTTP-01能否成功以Staging结果为准。
任何失败按rollback-plan停止，不临时把8000对外发布。

## 3. Staging、正式签发

按 `certificate-plan.md` 的准确参数，先检查ACME directory/profiles、做Staging、检查IP SAN；
通过后申请生产lineage `magicvvu-ip`。Staging保持root独立目录，永不加载到443。
检查正式证书的IP SAN、链、notBefore/notAfter和私钥权限；签发失败停止，不改架构。

## 4. 启用正式HTTPS（首次开放API）

建立before-https备份；确认正式 `/etc/letsencrypt/live/magicvvu-ip/fullchain.pem` 和privkey都存在。
用 `nginx-magicvvu-api.conf` 原子替换**同一**site目标，不能同时启用HTTP-only和最终模板以免重复default_server。
先在目标目录创建已登记的临时文件，核对owner/mode，再同文件系统rename切换；
若 `nginx -t` 失败，恢复HTTP-only磁盘配置，不reload。
语法通过后 `systemctl reload nginx`；此操作开放443并开始公网API代理，必须记录准确时刻。

未来验证：

```bash
# DRAFT P3 ONLY，全部保留默认TLS验证
curl --connect-timeout 5 --max-time 15 https://8.134.172.165/api/v1/health
curl --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}\n' https://8.134.172.165/api/v1/users/me
# 预期：health 200，users/me无凭据401；以下路径预期404且不转发
curl --path-as-is -o /dev/null -w '%{http_code}\n' https://8.134.172.165/internal/v1/inventory/search
curl --path-as-is -o /dev/null -w '%{http_code}\n' https://8.134.172.165/internal/v1/operations/00000000-0000-0000-0000-000000000000
curl --path-as-is -o /dev/null -w '%{http_code}\n' https://8.134.172.165/%69nternal/v1/inventory/search
curl --path-as-is -o /dev/null -w '%{http_code}\n' https://8.134.172.165/api/v1/../internal/v1/inventory/search
curl -o /dev/null -w '%{http_code}\n' https://8.134.172.165/docs
curl -o /dev/null -w '%{http_code}\n' https://8.134.172.165/redoc
curl -o /dev/null -w '%{http_code}\n' https://8.134.172.165/openapi.json
```

继续验证未知路径/方法、ready/debug/metrics/admin及其变体默认拒绝；
UUID占位符必须用合成UUID，不查询真实他人数据。限流用无业务副作用的请求或本机隔离配置验证，
不得通过反复真实登录制造会话或改账号。`logrotate -d /etc/logrotate.d/magicvvu-api`只做调试检查。
检查Nginx实际生效的access格式只有固定路由标签/状态/耗时等；server error_log必须为/dev/null，
禁用debug；用合成非秘密哨兵验证URI、query、Authorization、Cookie、body未进入Nginx日志。
Backend现有访问日志另有记录URI/query的可能，不擅自改业务配置，分享前脱敏；App不得把凭据放URL。

## 5. 自动续期和监测

建立before-renewal备份；安装解除DRAFT保护的生产hook副本并核验路径/权限。
检查自带timer确实enabled/active，不新增重复cron；执行受控 `renew --dry-run --run-deploy-hooks`。
用正式证书信任验证及加载指纹确认hook效果。安排首次自然续期后验证serial/有效期变化与加载的新指纹，
不得把dry-run描述为“已换成新的正式证书”。
按certificate-plan落实小时监测和告警渠道；验证timer缺失、证书临近到期、reload失败等合成故障能产生可接收告警。
故障演练不得损坏真实证书；用离线样本/独立测试配置，不把过期证书装到公网。

监测实际安装步骤（P3才执行）：将审阅后 `DRAFT_ONLY=False` 的监测脚本副本安装为
`/usr/local/sbin/magicvvu-cert-monitor`，root:root 0750；将两个monitor unit草案去除文件名的
`.DRAFT`后安装到 `/etc/systemd/system/`，root:root 0644，并记录创建清单。
执行 `systemctl daemon-reload`、`systemctl enable --now magicvvu-cert-monitor.timer`、
`systemctl start magicvvu-cert-monitor.service` 后检查Result及journal。
生产续期timer按实际unit核实后启用；监测timer和续期timer是不同任务，不是重复签发调度。
告警通道必须另有用户接收端并做合成告警验证，不能将“监测service失败”说成用户已收到通知。

## 6. 阶段交付及停止点

再次核对服务健康、Compose/env哈希、容器ID/镜像/绑定，外部8000/5432/8767不可连接；
记录HTTPS、证书时间/链/IP SAN、timer、dry-run、指纹、日志、安全否定测试、备份位置及未完成项。
P3只完成基础设施和只读验证；P4客户端修改、P5真实手机写入验收分别另批。
不部署正式App，不做真实业务写入，不重启服务器（重启需要单独明确授权）。
