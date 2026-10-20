# P5 自动补货

状态：BLOCKED；手动PLAN_ADD回归保留。

真实规划读取和Android结构化recommendations展示已接入；建议展示量/单位/库存/待购/依据/计算时间，明确“尚未加入清单”。复用现有P3算法，没有更换为另一种阈值采购流程。

缺产品级可信映射、采购周期及独立偏好版本、可用库存核对来源、完整观察事实。现有所有购物写路径也没有统一的商品集合锁，简单比较快照后插入会留下其他成员并发新增待购的窗口。

所以 automatic_planning_commit=false、manual_plan_only=true；带planning_basis/planning_calculation/SUGGEST_PURCHASE的草稿仍由服务器拒绝自动执行，Android不开放确认。未通过删除planning_basis、名字匹配、伪造库存/观察日来绕过。没有自动加入待购、采购、支付或入库。

剩余实现：持久产品/批次/待购关联、独立偏好版本、可核实观察/盘点数据录入来源；全部库存/清单/偏好写路径采用一致锁序；确认时在事务内重读并比较item/batch/preference/shopping版本、水位、快照时效及原建议，任何变化重新核对。完成真实PostgreSQL并发及手机验收后才开放能力。当前不把这些尚未实现部分写为DONE。
