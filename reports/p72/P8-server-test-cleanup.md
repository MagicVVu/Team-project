# P8 测试环境清理

状态：BLOCKED。**删除资源0；停止的既有长期测试服务0。**

用户已明确授权清理，但要求资源审计、替代测试、关键业务验收、备份/回滚检查先完成。本地临时真实PostgreSQL替代机制已验证；服务器SSH目前不可用，依赖、最新备份恢复、停止测试影响及正式手机业务验收尚未完成，所以可执行删除白名单仍为空。无法证明安全的对象全部保留。

| 项目 | 首次检查 | 清理后 |
|---|---|---|
| 全部容器 | 16；运行11 | NOT_VERIFIED（未清理，不能推断无外部变更） |
| 正式容器 | backend/agent/db共3，healthy | 本轮未改；当前NOT_VERIFIED |
| 长期测试 | execution3 + P7 rules/model5；另5已退出 | 全部未删除 |
| 网络 | 9，正式starter_default/starter_ai_net | 未删除 |
| 卷 | 11，正式postgres_data/agent_cache | 未删除 |
| 正式入口 | 443→127.0.0.1:8000 | 未改，最新连通失败 |
| 磁盘 | 40G/用7.7G/余30G | 未能重读，无节省空间声明 |

候选TEST_ONLY范围：magicvvu-p7-execution-20261017、magicvvu-p7-test-20261017及其独立容器/卷/网络；必须重新核对完整唯一ID、Compose标签、所有挂载、实际DB连接、systemd/cron/路由、依赖后才转入删除白名单。共享PostgreSQL镜像、Docker、SSH、Tailscale、正式镜像/网络/卷与UNKNOWN资源保留。

未使用prune、down -v、模糊删除、项目根目录递归删除或SQL清库。测试源码/迁移/脚本全部保留。已销毁的仅是本轮本地自建临时PostgreSQL data目录；它不是服务器历史测试环境。

曾尝试上传无凭据源码到/home/admin/magicvvu-p72-validation-20261020，但SSH超时，没有远端成功证据；该暂存目录是否存在UNKNOWN，恢复连接后先检查，不自动删除。

后续：重新审计→正式最新备份及隔离恢复→归档测试历史与原配置→按唯一ID试停独立测试服务→复核正式业务与Funnel→逐项清理已确认资源→保存前后容器/网络/卷/端口/磁盘对照。任何依赖不明或恢复不可靠的目标继续保留。
