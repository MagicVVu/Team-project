# P2：IP证书与自动续期设计（草案，全部未执行）

## 已核实的官方支持与安装选择

2026-10-21服务器 `snap info certbot` 返回官方已验证发布者Certbot Project，stable 5.8.0；
实际安装版本仍待P3核实。apt缓存2.9.0不满足本任务。优先 `snap install --classic certbot`，
使用 `/snap/bin/certbot` 的明确路径，避免PATH命中旧apt版本；不必额外创建certbot软链接。
Snap完整包及CDN下载尚未验证；失败时停止，不切换非官方脚本安装或降低版本要求。

依据：[Let's Encrypt IP/Webroot说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)、
[Certbot 5.8用户指南及CLI参数](https://eff-certbot.readthedocs.io/en/stable/using.html)、
[Let's Encrypt profiles](https://letsencrypt.org/docs/profiles/)。

参数决策：`certonly`、`--webroot`、`--webroot-path`、`--ip-address 8.134.172.165`，不使用 `-d IP`。
5.8支持 `--required-profile shortlived`；这里选择required而非preferred，使profile不支持时明确失败，
不回退默认profile。官方示例使用preferred，本草案的required行为已通过CLI文档确认。
HTTP-01使用 `--preferred-challenges http`；不使用Nginx插件自动安装IP证书。

## 前置门槛

必须获P3明确批准、用户确认已处理广州服务器的ICP/App备案适用前置条件、重新核对云防火墙，
提供ACME联系邮箱并确认同意CA条款。没有这些确认，不执行下面命令。
不能因为仅一台测试手机或是ACME-only入口，就擅自推定合规前提已满足。

## 顺序与隔离（以下为P3命令草案）

1. 安装Nginx前禁止包自动启动，备份并保护已有policy-rc.d；安装后仅准备HTTP-only配置。
2. 确认Nginx含PCRE、SSL模块，`nginx -t`通过；明确启动HTTP-only会开放公网80，需门槛满足。
3. Webroot根目录 `/var/www/magicvvu-acme`，root拥有，0755；挑战目录同样0755。
   root运行Certbot创建挑战文件，Nginx仅需读取；禁止将目录开放为任意用户可写。
4. 先用无敏感内容的独立探针文件，从服务器外GET
   `http://8.134.172.165/.well-known/acme-challenge/<探针文件名>`，确认200及内容一致。
   `/`、API、目录和其他明文路径应404；验证后只删除这个已记录的探针文件。
5. 检查Staging/正式directory的DNS、默认TLS验证及profiles包含shortlived；GET可做有界重试。
   网络失败不得以 `curl -k`、改hosts、改CA或代理绕过来处理。

Staging使用独立配置/工作/日志目录，不写生产lineage，不被默认生产renew扫描：

```bash
# DRAFT P3 ONLY；acme_email由用户提供，不打印，不提交Git
sudo /snap/bin/certbot --version
sudo /snap/bin/certbot --help all
sudo /snap/bin/certbot certonly --staging --non-interactive --agree-tos \
  --email "${acme_email:?请先提供联系邮箱}" \
  --config-dir /root/magicvvu-acme-staging/config \
  --work-dir /root/magicvvu-acme-staging/work \
  --logs-dir /root/magicvvu-acme-staging/logs \
  --cert-name magicvvu-ip-staging \
  --webroot --webroot-path /var/www/magicvvu-acme \
  --preferred-challenges http --required-profile shortlived \
  --ip-address 8.134.172.165
```

Staging父目录先以root:root 0700创建，纳入备份/新建清单。确认签发成功、IP SAN正确、
日志中HTTP-01成功；只读检查证书，不将其加载到公网443，不用它做Android信任测试。

Staging通过且正式签发获准后：

```bash
# DRAFT P3 ONLY；仍使用HTTP-only站点，不传任何 --nginx 安装参数
sudo /snap/bin/certbot certonly --non-interactive --agree-tos \
  --server https://acme-v02.api.letsencrypt.org/directory \
  --email "${acme_email:?请先提供联系邮箱}" \
  --cert-name magicvvu-ip \
  --webroot --webroot-path /var/www/magicvvu-acme \
  --preferred-challenges http --required-profile shortlived \
  --ip-address 8.134.172.165
```

生产使用默认 `/etc/letsencrypt`。`magicvvu-ip`只是本地lineage名称，不是证书DNS名称。
若该名称意外已存在或命令输出出现 `-0001` 等其他lineage，停止核实，不能盲目启用预设路径。

正式签发成功后才执行：

```bash
# DRAFT P3 ONLY；均为公开证书元数据，不输出privkey
sudo openssl x509 -in /etc/letsencrypt/live/magicvvu-ip/cert.pem \
  -noout -dates -issuer -ext subjectAltName
sudo openssl x509 -in /etc/letsencrypt/live/magicvvu-ip/cert.pem \
  -noout -checkip 8.134.172.165
sudo openssl verify -CApath /etc/ssl/certs \
  -untrusted /etc/letsencrypt/live/magicvvu-ip/chain.pem \
  /etc/letsencrypt/live/magicvvu-ip/cert.pem
```

核对notBefore/notAfter与160小时短期profile，信任链、`IP Address:8.134.172.165` SAN、私钥权限，
以及nginx -t的证书/私钥配对检查。私钥维持root必要读取权限，不为www-data开放私钥；
常规root master启动Nginx，worker无需直接读取私钥。不打印、复制到Git或用chmod 644放宽私钥。
先备份HTTP-only可用配置，再原子替换为最终HTTPS草案对应站点，语法通过才reload。
**这一次reload才会打开443并转发Android API。** HTTP-only中不得提前放入证书引用。

## 续期和reload设计

官方5.8 Snap配方定义 `renew` oneshot和每日两次随机调度：
[Certbot v5.8.0 Snap源码](https://github.com/certbot/certbot/blob/v5.8.0/snap/snapcraft.yaml)。
优先使用安装后实际生成的 `snap.certbot.renew.timer/service`，检查enabled/active、
实际ExecStart、随机窗口与下一次触发，不能把源码配方当作已安装服务状态。

160小时证书在Certbot 5.8中通常在剩余生命周期一半时进入续期窗口；ARI等可能影响实际调度，
由Certbot判断，不写死每隔160小时签发，更不每次强制续期。文档依据见
[续期行为](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)。
两次/日调度需观察其最长实际间隔和失败恢复预算，不据单次成功保证可靠。
若安装后timer未生成、不可启用或调度不满足恢复预算，停止并报告；不叠加第二套cron造成并发。
如需改为专用小时timer，应另行审阅直接执行 `/snap/bin/certbot renew` 的独立service，
处理Snap自己的timer门控和重复调度，不能只随意改Snap timer的OnCalendar。

首次HTTPS正常后，再部署已审阅的 `renewal-deploy-hook.DRAFT.sh` 到
`/etc/letsencrypt/renewal-hooks/deploy/50-magicvvu-nginx`，root:root 0750。
必须在部署副本明确将 `DRAFT_ONLY=1` 改为0；P2原稿保留保护。
脚本仅处理生产lineage，验证IP、有效期及受信链，先 `nginx -t`，成功才reload；
随后用正常TLS验证连接本机443，比较正在服务的证书SHA256与磁盘当前证书，5次有界复查。
不成功时返回非零并写不含请求/凭据的固定日志，不能把Certbot成功等同于Nginx已换证。

```bash
# DRAFT P3 ONLY：目录hook由Certbot发现，无需手改renewal/*.conf
sudo systemctl is-enabled snap.certbot.renew.timer
sudo systemctl is-active snap.certbot.renew.timer
sudo systemctl cat snap.certbot.renew.timer snap.certbot.renew.service
sudo systemctl list-timers --all --no-pager
sudo /snap/bin/certbot renew --cert-name magicvvu-ip --dry-run --run-deploy-hooks
```

若实际存在该timer但未启用，先记录状态并在P3内明确执行
`sudo systemctl enable --now snap.certbot.renew.timer`，再复查；若unit名称/来源不符则停止，不能猜名称。

`--dry-run`通过Staging模拟续期；`--run-deploy-hooks`使成功后测试hook，hook使用当前正式证书，
不把临时Staging证书装入Nginx。模拟通过只能证明流程，不能证明真实新证书轮换已发生。
P3若证书尚未到期，不为凑证据反复force-renew；记录模拟、当前加载指纹，并在首次自然续期后核验新serial/到期时间与加载指纹。
若P3验收要求立即验证真实轮换，需说明消耗及限额后再做一次有目的的正式续期，不能冒充已完成。

## 网络重试、监测与失败处理

- directory探测采用最多3次GET、有界超时和短退避；正式签发/授权失败不循环重新下单。
  确认429/Retry-After或验证错误后停止诊断。[官方限额与重试](https://letsencrypt.org/docs/rate-limits/)。
- 正常renew调度在失败后提供后续尝试；首次失败就应告警并检查DNS、出口TLS、入站80、挑战文件权限、timer、hook和系统时间。
  不通过重启业务容器处理ACME故障。
- `cert-monitor.DRAFT.py` 与service/timer草案提供小时监测：48小时内到期、证书缺失、
  线上/磁盘指纹不符、timer未启用/未活动均失败；全程正常TLS验证。
  部署副本必须解除DRAFT标志；配合检查renew.service的Result/ExecMainStatus和最近执行时间。
- 建议阈值：任何续期/hook失败即处理；剩余48h预警、24h紧急、12h考虑停止API避免过期服务。
  本地journal/failed状态不是远程通知。**告警接收方式仍待用户确认，P2未配置邮箱、Webhook或Codex自动化。**
  P3上线前需要落实用户能收到的故障通知；告警内容只含固定服务状态与到期时间。
- 续期失败且旧证书仍有效时保留运行服务；旧证书失效时停止公网API/恢复HTTP-only挑战入口，
  继续保留业务容器，绝不切换自签名、明文API或忽略TLS错误。

日常检查命令（P3部署后适用）：

```bash
sudo openssl x509 -in /etc/letsencrypt/live/magicvvu-ip/cert.pem -noout -dates -serial
sudo openssl x509 -in /etc/letsencrypt/live/magicvvu-ip/cert.pem -noout -checkend 172800
sudo systemctl show snap.certbot.renew.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp
sudo journalctl -u snap.certbot.renew.service -u magicvvu-cert-monitor.service --since '24 hours ago' --no-pager
curl --connect-timeout 5 --max-time 15 https://8.134.172.165/api/v1/health
openssl s_client -connect 8.134.172.165:443 -verify_ip 8.134.172.165 \
  -verify_return_error -CApath /etc/ssl/certs </dev/null
```

日志只在服务器受限查看，对外分享前脱敏。手机信任链及移动网络连接仍留P5；
本阶段不存在证书到期时间或已启用续期任务可供验收。
