# P3 OPEN / DISCARD

<<<<<<< Updated upstream
状态：PARTIAL（代码、真实PostgreSQL自动化DONE；未部署/未真机）。

扩展原Draft/Commit、DTO、账本约束、事务和operation_id恢复；没有第二套网关。OPEN检查家庭批次/expected_version/家庭可信今天/日期合法及购入顺序/未开封；保留数量单位位置；更新opened_at/version，单事务Opened事件与回执。相同操作返回原回执；另一个重复开封明确无变更拒绝。

DISCARD partial精确扣减；all行锁后同时验证版本及整批量，变化返回冲突；零后DISCARDED；保留批次、Discarded审计与回执，绝不混入Consumed。沿用单位精确换算及6位精度，保留队友的吨/台兼容规则。

迁移20261020_0008只扩展现有约束。临时真实PostgreSQL完成head→0007→head；存在新动作审计时拒绝schema降级，应用回滚应保留增量表约束和全部回执。正式执行前仍需最新备份/实际恢复演练/旧镜像和迁移锁等待评审。**没有迁移正式数据库。**

Android只为OPEN编辑日期；DISCARD提供指定/全部选项，全部数量来自生成时before事实并禁手填，展示原量/丢弃量/预计剩余/终态及真实回执。按钮由后端能力控制。

测试覆盖精确扣减、终态、未来/非法日期、单位/精度/超量、旧版本、all量变化、重复开封、幂等恢复和OPEN/DISCARD真实行锁并发。最终结果见P6。候选源码actions.OPEN/DISCARD=true，线上未开放。
=======
状态：PARTIAL。原 Draft/Commit 事务内扩展，无第二套执行网关；未部署、正式能力未开放。

OPEN 校验真实家庭批次、expected_version、日期（家庭时区不得未来、不得早于购入）、未开封；保留数量单位位置，更新 opened_at/version，写 Opened 事件与原操作回执。同 operation_id 恢复不再执行，其他 operation_id 再开封明确拒绝。

DISCARD 支持 partial/all；原有精确单位换算和六位精度检查，行锁 + expected_version；all 要求提交量与当前整批量完全相等，变化需重新核对。数量为零后 DISCARDED；保留记录；事件为 Discarded，不混入 Consumed。

迁移 `20261020_0008_open_discard.py` 扩展既有约束，无清空、无初始化；存在 OPEN/DISCARD 回执时拒绝 schema downgrade，应用回滚应保留增量 schema 和审计。生产执行前仍需最新备份/恢复演练、旧镜像、迁移时锁等待检查。未执行生产迁移。

Android 复用既有动态表单、批次版本/原量/预计剩余、操作凭证与回执恢复；OPEN 无数量表单，DISCARD 显示模式。按钮继续服从实际服务器 capability。

本地命令与输出见 evidence/P3-execution-test.log：11 passed，1 skipped（真实 PostgreSQL 并发另验）。包括 future/无效日期、超量/精度/单位、all 数量变化、旧版本、重复开封、幂等/真实事件。生产和真机 NOT_VERIFIED。
>>>>>>> Stashed changes
