# P3 OPEN / DISCARD

状态：PARTIAL（代码、真实PostgreSQL自动化DONE；未部署/未真机）。

扩展原Draft/Commit、DTO、账本约束、事务和operation_id恢复；没有第二套网关。OPEN检查家庭批次/expected_version/家庭可信今天/日期合法及购入顺序/未开封；保留数量单位位置；更新opened_at/version，单事务Opened事件与回执。相同操作返回原回执；另一个重复开封明确无变更拒绝。

DISCARD partial精确扣减；all行锁后同时验证版本及整批量，变化返回冲突；零后DISCARDED；保留批次、Discarded审计与回执，绝不混入Consumed。沿用单位精确换算及6位精度，保留队友的吨/台兼容规则。

迁移20261020_0008只扩展现有约束。临时真实PostgreSQL完成head→0007→head；存在新动作审计时拒绝schema降级，应用回滚应保留增量表约束和全部回执。正式执行前仍需最新备份/实际恢复演练/旧镜像和迁移锁等待评审。**没有迁移正式数据库。**

Android只为OPEN编辑日期；DISCARD提供指定/全部选项，全部数量来自生成时before事实并禁手填，展示原量/丢弃量/预计剩余/终态及真实回执。按钮由后端能力控制。

测试覆盖精确扣减、终态、未来/非法日期、单位/精度/超量、旧版本、all量变化、重复开封、幂等恢复和OPEN/DISCARD真实行锁并发。最终结果见P6。候选源码actions.OPEN/DISCARD=true，线上未开放。
