<<<<<<< Updated upstream
# P4 消费与预测

状态：PARTIAL。

新增受认证GET /internal/v1/planning/context，沿用V1 PlanningSnapshot；PostgreSQL独立只读REPEATABLE READ事务内复核成员，读取真实批次、完整已知账本和待购，超契约限额明确失败。内容摘要生成稳定snapshot_id、事件水位和清单版本；as_of独立返回。recorded_at采用实际DraftOperation.committed_at。

当前数据库没有跨批次产品注册表、完整观察日来源、历史纠正/撤销关联、独立采购偏好版本和真实实物盘点凭证。为避免猜测：item_key=真实batch UUID（单批次粒度）；不按名称合并商品或猜待购关联；无法映射的待购令pending_complete=false；coverage=[]、recording_completeness_source=null、stock_verification=null、usable_quantity_verified=false。默认0最低库存不冒充明确用户偏好。

history_complete=true仅表示已知业务账本读全，不表示用户消费完整登记；既有算法由缺观察来源/覆盖正确返回insufficient_data，不把未知日当0，不由库存差额推消费。Discarded/Opened/Moved不计消费。Android展示结构化窗口、单位、数据状态/不足原因及条件预测。

P3/V1算法和14天/5事件/3日期/168小时盘点门槛保持不变。缺真实覆盖时不生成日期。真实家庭的完整预测、商品级聚合、撤销纠正来源仍BLOCKED；必须先设计/记录真实产品映射、完整观察声明和盘点来源，不能伪造数据放行。
=======
# P4 消费与耗尽预测

状态：PARTIAL，未部署。

新增既有 internal/v1/planning/context，沿用服务 token + 用户/家庭授权和 V1 PlanningSnapshot。PostgreSQL 使用独立只读 REPEATABLE READ 快照，事务内重新校验成员。读取真实批次/完整已知账本/待购列表；超过契约上限明确失败，无静默截断。快照 ID、事件水位、购物版本来自实际内容摘要；同内容快照标识稳定，读取时间独立返回。

重要模型缺口：目前数据库只有库存批次，没有跨批次产品注册表、完整观察日期声明、纠正/撤销事件关联、采购周期、真实盘点凭证。为避免伪造，item_key 使用真实 batch UUID（单批次粒度），不按名称猜测同一产品；记录完整性来源为空、coverage 为空、stock_verification 为空。无法绑定的待购项设置 pending_complete=false。运输完整 history_complete=true 只说明已知账本读全，绝不意味着用户完整登记。

既有 P3/V1 算法及 14 天/5事件/3日期/盘点时效门槛保持不变。没有实际完整覆盖时返回 insufficient_data，不生成耗尽日期。Android 新增结构化消费窗口、数量、单位、数据状态/不足原因、条件预测展示。

不从库存差额推断消费，不把 Discarded/Opened/Moved 算作 Consumed。测试见 P6；产品级聚合、历史纠正与可供正式预测的真实覆盖仍 BLOCKED，需团队确定并记录可信产品映射和完整观察/盘点事实，再扩展契约数据来源。不能用一次数据库读取代替用户盘点。
>>>>>>> Stashed changes
