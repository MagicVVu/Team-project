# P4 消费与预测

状态：PARTIAL。

新增受认证GET /internal/v1/planning/context，沿用V1 PlanningSnapshot；PostgreSQL独立只读REPEATABLE READ事务内复核成员，读取真实批次、完整已知账本和待购，超契约限额明确失败。内容摘要生成稳定snapshot_id、事件水位和清单版本；as_of独立返回。recorded_at采用实际DraftOperation.committed_at。

当前数据库没有跨批次产品注册表、完整观察日来源、历史纠正/撤销关联、独立采购偏好版本和真实实物盘点凭证。为避免猜测：item_key=真实batch UUID（单批次粒度）；不按名称合并商品或猜待购关联；无法映射的待购令pending_complete=false；coverage=[]、recording_completeness_source=null、stock_verification=null、usable_quantity_verified=false。默认0最低库存不冒充明确用户偏好。

history_complete=true仅表示已知业务账本读全，不表示用户消费完整登记；既有算法由缺观察来源/覆盖正确返回insufficient_data，不把未知日当0，不由库存差额推消费。Discarded/Opened/Moved不计消费。Android展示结构化窗口、单位、数据状态/不足原因及条件预测。

P3/V1算法和14天/5事件/3日期/168小时盘点门槛保持不变。缺真实覆盖时不生成日期。真实家庭的完整预测、商品级聚合、撤销纠正来源仍BLOCKED；必须先设计/记录真实产品映射、完整观察声明和盘点来源，不能伪造数据放行。
