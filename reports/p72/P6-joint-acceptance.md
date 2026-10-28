# P6 联合验收

状态：PARTIAL。自动化DONE；真实模型/正式账号/手机NOT_VERIFIED。

## 新基线最终证据

| 范围 | 结果 | 证据 |
|---|---|---|
| 后端完整套件，真实PostgreSQL17.11 | 120 passed；0 skipped；exit0 | evidence/P6-postgres-local.json |
| PostgreSQL迁移演练 | head→0007→head，全部exit0 | 同上migration |
| AI完整套件，锁定依赖+Windows时区数据 | 688 passed | evidence/P6-agent-migrated.log |
| Android JVM单元测试 | 26通过，0失败 | evidence/P6-android-unit-summary.json |
| 正式HTTPS Release候选构建 | BUILD SUCCESSFUL | evidence/P6-android-final.log |
| 正式登录/选家庭/DeepSeek/手机恢复 | NOT_VERIFIED | 未提供受控账号及实际手机操作 |
| 最新正式HTTPS、SSH | BLOCKED | evidence/P1-public-checks.json、P0-ssh-recheck.log |

重置前的119后端/674AI等旧日志仅历史诊断，不作为新基线的最终通过证据。最初AI失败由依赖版本差异引起，锁定依赖后又补齐Windows IANA tzdata；没有改导出契约掩盖差异。Windows pg_ctl继承PIPE导致第一次临时运行等待，已停止、删除旧集群并改用文件收集输出；最终运行成功。

## 可复现隔离方案

无需服务器长期测试环境，不连接正式数据库。便携运行时来自[PostgreSQL官方Windows下载入口](https://www.postgresql.org/download/windows/)所链接的[EDB binaries](https://www.enterprisedb.com/download-postgresql-binaries)。下载URL及本轮观察SHA256固定在tools/p72_prepare_postgres.py，缓存不进Git。

```powershell
.venv/Scripts/python.exe tools/p72_prepare_postgres.py
.venv/Scripts/python.exe tools/p72_local_postgres_tests.py
$env:PYTHONPATH=(Join-Path (Get-Location) 'agent')
.cache/p72-agent-venv/Scripts/python.exe -m pytest agent/tests -q --tb=short
```

AI独立环境安装：Python3.12 venv → pip install -r agent/requirements.lock.txt → Windows补tzdata==2026.5。后端用既有requirements-dev.txt（本地已满足）。完整包版本与源码摘要另存evidence。

临时脚本每次新建.cache/p72-local-postgres-*、独立密码、只监听127.0.0.1随机端口；不安装系统服务。PG测试保持精确测试DB名保护；本地路径还核对SHOW data_directory。finally停止并在验证绝对路径后仅删除本轮临时data目录。最终postgres_stopped=true、cluster_removed=true。无正式家庭写入、无模型付费调用。

## 关键请求与已验证断言

- 原任务澄清：POST clarifications/{task_id}，revision与允许answers；真实P7既有续接与Kotlin纯解析分别测试，不把手机持久化当作已真机验证。
- 引用：原句“它在什么地方”，携带source_task_id/revision/batch_id；先以真实业务MOVE将合成批次从冰箱移至书房，再读得书房/version2。引擎调用计数与runtime.model_calls均0；原文空格不裁剪。同键请求只调用一次上游。
- OPEN：commit返回committed；库存5盒→5盒、位置不变、version1→2、Opened(quantity=null)一条；重放回执相同，另键重复开封无第二次变更。
- DISCARD partial：5盒丢2→3盒ACTIVE；all：5→0/DISCARDED；Discarded审计与库存同事务。过量/非法单位/精度/旧版本/整批量变化拒绝。
- 并发：真实PostgreSQL覆盖原operation_id竞争、同批次不同草稿、取消竞争，以及OPEN/DISCARD同批次竞争；一条变更成功，竞争者冲突，不静默覆盖。
- 规划：真实已登记Consumed读取、scope隔离、快照变更、未知待购映射不猜、观察覆盖缺失、预测无日期。P3算法既有充分/不足/纠正净额等场景在AI套件验证，当前后端尚无真实纠正/覆盖来源。

上述是自动化请求/回执/数据库断言摘要，不是正式用户业务回放。最终PGJSON保存实际测试输出、迁移日志及清理结果；没有伪造线上成功回执。

未完成：手机Activity/进程重建、前端场景端到端、移动网络、团队签名、真实DeepSeek调用；自动补货服务器重验尚未实现。不能把单元测试和ASGI联合测试等同完整手机验收。
