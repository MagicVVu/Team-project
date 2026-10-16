# V1 completion profile (P6)

启动：python -m uvicorn v1.app:create_app --factory --host 127.0.0.1 --port 8767。

沿用 AI_SERVICE_TOKEN、BACKEND_BASE_URL、BACKEND_TOOL_TOKEN、P3_ENGINE、DEEPSEEK_API_KEY、LLM_MODEL 及共用累计账本，不自动读取 .env。新增代码只读，不保存任务、不确认库存、不撤销事件。Jev 按用户要求暂缓。

保留 /agent/message、/agent/clarification、风险和规划只读接口；新增 /overview/query、/feedback/after-commit、/capabilities/check。正式网关消息和答案字段不变，调用方使用 v1.tasks.TaskClient；旧 interaction/P3 工厂及默认契约不变。

发布规则仅允许 human_review；默认5条 source_check 规则不会被当成人工审核。规划接口兼容旧P3数据，但未提供 stock_verification 时不提供精确耗尽日期/自动采购草稿。库存核对默认最大168小时，是可版本化项目策略，非预测效果实证。

后端尚未提供规划/提交凭证读取时返回明确不可用；契约和协作见 docs/versions/V1-P6。测试夹具与契约导出器不上传服务器。源码同步不切换正式服务。
