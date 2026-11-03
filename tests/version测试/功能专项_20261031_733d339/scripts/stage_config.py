"""Version numbers identify feature ownership, not twenty isolated applications."""
STAGES=[
('P0','基础操作',['新增与采购草稿','库存与位置查询','确认前不写入'],['test_contract','test_evaluation']),
('P1','生命周期',['开封与移动','整件消耗与丢弃','缺字段和对象选择'],['test_p1']),
('P2','风险判断',['标签期限与保存条件','未知信息降级','规则来源与审核边界'],['test_p2','test_p2_integration','test_rule_review_preparation']),
('P3','统计预测',['有效消费与去重更正','日均和耗尽日期','待购扣减与补货公式'],['test_p3']),
('P4','历史缺陷',['中文数字与品牌','日期和查询范围','多操作与异常输出'],['test_p4','test_model_failures']),
('P5','确认文字',['编辑后的最终文字','未确认零调用','否定口误取消和任务协议'],['test_interaction']),
('P6','位置摘要与反馈',['按位置反查和明确用完','首页按需摘要','真实回执与操作后反馈'],['test_v1']),
('P6.1','运行配置',['隐藏密钥与安全加载','缺配置和认证边界','配置就绪不冒充在线验证'],['test_runtime_config']),
('P7','引用与续接',['可信对象引用','澄清路由和任务修订','跨家庭和过期保护'],['test_conversation']),
('P7.1','配置和入口收尾',['显式运行入口','配置解析一致性','离线能力与部署记录分开'],['test_runtime_config']),
('P7.2','单位与接入契约',['吨台等单位兼容','AI和后端单位对应','迁移和PG并发不冒充离线通过'],['test_unit_compatibility']),
('P7.3','业务字段约束',['常见位置表达','位置长度与采购精度','澄清续接和缺数据提示'],['test_p73_local','test_p7_location_query']),
('P7.4','费率与预算',['旧费率核验日期兼容','预算保护仍保留','发布记录仅追溯'],['test_pricing_policy']),
('P8','聊天任务控制',['任务解释','草稿修改和取消','等待和请求恢复'],['test_p8_chat']),
('P8.1','范围和来源修复',['指定对象查询与全部用完','单位和采购来源','归档与降级反馈'],['test_local_chain_repairs']),
('P8.2','当前会话记忆',['可信近期历史','对象追问和新会话','任务状态与恢复'],['test_session_memory']),
('P8.3','规划来源',['显式商品聚合和事件语义','待购三态与当前数据限制','精确basis和只读重验'],['test_p83_planning']),
('P8.4','自然语义',['自然任务理解','否定假设和改口','只读和草稿边界'],['test_p84_dialogue']),
('P8.5','旧话题续接',['会话片段与话题检索','旧任务续接和事实刷新','原引用有效期不延长'],['test_p85_memory','test_p85_archive','test_p85_semantics']),
('P8.6','自主循环',['实际可超过两次调用','错误反馈与停止机制','逐件库存和跨协议恢复'],['test_autonomous','test_autonomous_physical'])]
VERSION_OF={module:v for v,_,_,modules in STAGES for module in modules}
VERSION_OF['test_runtime_config']='P6.1'
SUPPORT={'test_session_memory':'P8.2','test_p83_ai_planning_contract':'P8.3','test_autonomous_adaptation':'P8.6','test_physical_inventory':'P8.6','test_inventory_cleanup':'P8.6','test_unitless_inventory':'P8.6','test_unit_compatibility':'P7.2','test_p85_dialogue':'P8.5','test_p85_archive_persistence':'P8.5','test_backend_p4_planning':'P8.3','test_backend_p3_open_discard':'P1','test_backend_p2_conversation':'P7','test_v09_execution':'P7','test_v06_agent_gateway':'P5'}
