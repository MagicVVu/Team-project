package com.example.teamapp.data

object ChatMessages {
    fun reason(code: String, fallback: String = "请核对当前任务后继续"): String = when (code) {
        "STOCK_COUNT_MISMATCH" -> "盘点数量与当前库存不同，请先盘点修正、刷新，再由你重新确认盘点。"
        "PLANNING_FACTS_VERSION_CONFLICT" -> "资料已被更新，输入仍保留。请读取最新版本并复核，不会自动覆盖。"
        "COVERAGE_DAY_OUT_OF_RANGE" -> "只能核对家庭时区中已经结束的日期，今天与未来不能提交。"
        "COVERAGE_LIMIT_EXCEEDED" -> "每次最多核对 366 天，累计最多 3660 天。"
        "LABEL_DATE_REQUIRED" -> "请先填写包装标签日期，再核实标签适用条件。"
        "OPENED_STATE_CONFLICT" -> "该批次已有开封日期，不能否认已开封。"
        "HOUSEHOLD_TIMEZONE_MISMATCH" -> "家庭时区已变化，请刷新并重新核对日期。"
        "OPERATION_ID_CONFLICT" -> "原操作 ID 对应不同内容，请保留原请求并核实，勿重复新建。"
        "CHAT_GREETING" -> "你好，可以继续补充当前任务，或问我能做什么。"
        "CHAT_HELP" -> "可以查库存和位置，整理库存或采购草稿。补充当前缺少的信息后，我会继续；需要实际操作时仍请你确认。"
        "CHAT_THANKS" -> "不客气。可以继续当前任务，或说“开始新任务”。"
        "AMBIGUOUS_SUPPLEMENT" -> "暂时无法确定要补充哪个字段，请按下面的提示填写。"
        "INVALID_CANDIDATE", "CANDIDATES_CHANGED" -> "候选批次不存在或已经变化，请核对最新列表后重新选择。"
        "REFERENCE_REQUIRED" -> "请先选择一个批次，或写明物品名称。"
        "REFERENCE_EXPIRED", "REFERENCE_SOURCE_CHANGED", "REFERENCE_TERMINAL" -> "上次选择已失效，请重新查询或选择批次。"
        "INVALID_DATE", "OPEN_DATE_IN_FUTURE" -> "请填写有效日期；开封日期不能晚于家庭当地的今天。"
        "TASK_REVISION_CONFLICT", "TASK_SNAPSHOT_CHANGED", "TASK_SELECTOR_REQUIRED", "CLARIFICATION_CONFLICT", "INVENTORY_VERSION_CONFLICT" -> "任务或库存已变化，请先恢复并核对最新信息。"
        "REPLY_ADAPTER_UNAVAILABLE", "TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE" -> "当前服务尚未启用这种连续对话，请使用候选按钮或补充表单。"
        "PLANNING_CONTEXT_UNAVAILABLE" -> "统计和预测所需资料尚未接通，暂时无法提供可靠结果；仍可查询库存。"
        "AI_OUTCOME_UNKNOWN" -> "这条消息的理解结果待核实，不会自动重新调用模型。请先恢复原任务。"
        "REQUEST_ID_CONFLICT" -> "这条请求与原请求不一致，已停止重试，请保留记录并核对。"
        "PROTECTED_OR_UNKNOWN_FIELD" -> "这项内容不允许直接修改，请核对草稿；切换动作、物品或模式需要新任务。"
        "ACTION_NOT_EXECUTABLE", "PLANNING_REVALIDATION_UNAVAILABLE" -> "当前服务尚不支持执行这项操作，草稿尚未写入。"
        "DRAFT_ALREADY_COMMITTED" -> "这份草稿已有执行结果，请恢复原回执，不要再次操作。"
        "DRAFT_ALREADY_DECIDED" -> "这份草稿已执行或取消，不能继续修改，请恢复记录或开始新任务。"
        "DRAFT_EDIT_REQUIRES_FORM" -> "请在当前待确认草稿中修改；已执行的记录不能直接改写。"
        "DRAFT_CANCEL_REQUIRES_CONFIRMATION" -> "请核对这份草稿的执行状态，并使用取消草稿按钮；取消草稿不会撤销已执行操作。"
        "CONVERSATION_SESSION_EXPIRED", "CONVERSATION_BINDING_CHANGED", "CONVERSATION_SUPERSEDED" -> "登录、家庭或活动任务已变化，请重新选择当前任务。"
        else -> fallback
    }
}
