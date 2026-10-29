package com.example.teamapp.data

import org.json.JSONObject

enum class AssistantStatus(val label: String) {
    PROCESSING("正在处理"), CLARIFICATION("需要澄清"), PENDING("待确认"), SUBMITTING("正在提交"),
    COMMITTED("已执行"), CANCELLED("已取消"), EXPIRED("已过期"), CONFLICT("版本冲突"),
    UNKNOWN("结果待核实"), UNSUPPORTED("暂不支持"), FAILED("执行失败"), ANSWERED("已回答")
}

/** Public payloads retain provenance. Business state and receipt never come from reply text. */
data class AssistantEntry(
    val requestId: String, val requestBody: String,
    val task: String = "{}", val draft: String = "{}", val execution: String = "{}",
    val commitBody: String = "", val clarificationBody: String = "", val cancelBody: String = "",
    val edits: Map<String, String> = emptyMap(), val state: AssistantStatus = AssistantStatus.PROCESSING,
    val notice: String = "", val receipt: String = "", val refreshNeeded: Boolean = false,
    val failureCode: String = "",
    val conversationBody: String = "", val conversationResolved: Boolean = false,
    val conversationSession: String = "", val controlBody: String = "",
    val conversationReply: String = "", val checkedPreview: String = "", val transportMode: String = "legacy",
    val referenceClearBody: String = "", val referenceCleared: Boolean = false,
    val conversationResponse: String = "", val historical: Boolean = false, val conversationScopeId: String = "",
    val planningReview: String = "",
    val messageRejected: Boolean = false,
    val conversationRecovery: String = ""
) {
    val taskJson get() = JSONObject(task)
    val draftJson get() = JSONObject(draft)
    val executionJson get() = JSONObject(execution)
    val result get() = taskJson.optJSONObject("result") ?: JSONObject()
    val structuredResults get() = AssistantResults.collect(result, conversationResponse)
    val dialogueNotice get() = ConversationFeedback.dialogue(conversationResponse)
    val recoveryNotice get(): String {
        if (conversationRecovery.isBlank()) return ""
        val recovery = JSONObject(conversationRecovery)
        if (conversationResolved && recovery.optString("phase") != "completed") return ""
        return ConversationFeedback.recovery(recovery.stringOrEmpty("phase"), recovery.stringOrEmpty("recovery_hint"))
    }
    val automaticPlan get() = result.optJSONObject("planning_basis") != null ||
        result.stringOrEmpty("quantity_source") == "planning_calculation" || result.stringOrEmpty("intent") == "SUGGEST_PURCHASE"
    val command get() = if (checkedPreview.isNotBlank()) JSONObject(checkedPreview).getJSONObject("command") else draftJson.optJSONObject("draft") ?: result.optJSONObject("draft") ?: JSONObject()
    val taskId get() = taskJson.stringOrEmpty("task_id")
    val draftId get() = taskJson.stringOrEmpty("draft_id").ifBlank { executionJson.stringOrEmpty("draft_id") }
    val operationId get() = if (commitBody.isBlank()) "" else JSONObject(commitBody).getString("operation_id")
    val taskRevision get() = taskJson.optInt("revision")
    val draftRevision get() = draftJson.optInt("revision")
    val taskStatus get() = taskJson.stringOrEmpty("status")
    val clarificationExpired get() = taskStatus == "needs_clarification" && runCatching {
        !java.time.OffsetDateTime.parse(taskJson.getString("expires_at")).toInstant().isAfter(java.time.Instant.now())
    }.getOrDefault(true)
    val executionStatus get() = executionJson.stringOrEmpty("status")
    val errorCode get() = failureCode.ifBlank { executionJson.stringOrEmpty("reason_code").ifBlank { result.stringOrEmpty("error_code") } }
    val action get() = command.stringOrEmpty("action")
    val reply get() = conversationReply.ifBlank { result.stringOrEmpty("reply") }
    val preview get() = if (checkedPreview.isNotBlank()) JSONObject(checkedPreview) else draftJson.optJSONObject("preview") ?: result.optJSONObject("preview") ?: JSONObject()
    val allowedFields get() = result.optJSONObject("clarification")?.optJSONArray("allowed_fields")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()
    val candidates get() = result.optJSONArray("candidates")?.objects().orEmpty()
    val editableFields get() = executionJson.optJSONArray("editable_fields")?.let { a ->
        (0 until a.length()).map { a.getString(it) }.filter { it in AgentExecutionPolicy.editable[action].orEmpty() }
    }.orEmpty()
    fun toJson() = JSONObject().put("request_id", requestId).put("request_body", requestBody).put("task", task)
        .put("draft", draft).put("execution", execution).put("commit_body", commitBody).put("clarification_body", clarificationBody)
        .put("cancel_body", cancelBody).put("edits", JSONObject(edits)).put("state", state.name).put("notice", notice)
        .put("receipt", receipt).put("refresh_needed", refreshNeeded).put("failure_code", failureCode)
        .put("conversation_body", conversationBody).put("conversation_resolved", conversationResolved)
        .put("conversation_session", conversationSession).put("control_body", controlBody)
        .put("conversation_reply", conversationReply).put("checked_preview", checkedPreview)
        .put("transport_mode", transportMode)
        .put("reference_clear_body", referenceClearBody).put("reference_cleared", referenceCleared)
        .put("conversation_response", conversationResponse).put("historical", historical)
        .put("conversation_scope_id", conversationScopeId)
        .put("planning_review", planningReview)
        .put("message_rejected", messageRejected).put("conversation_recovery", conversationRecovery)
    companion object {
        fun fromJson(j: JSONObject) = AssistantEntry(j.getString("request_id"), j.getString("request_body"), j.getString("task"),
            j.getString("draft"), j.getString("execution"), j.optString("commit_body"), j.optString("clarification_body"), j.optString("cancel_body"),
            j.optJSONObject("edits")?.let { v -> v.keys().asSequence().associateWith { v.getString(it) } }.orEmpty(),
            AssistantStatus.valueOf(j.getString("state")), j.optString("notice"), j.optString("receipt"), j.optBoolean("refresh_needed"), j.optString("failure_code"),
            j.optString("conversation_body"), j.optBoolean("conversation_resolved"), j.optString("conversation_session"), j.optString("control_body"),
            j.optString("conversation_reply"), j.optString("checked_preview"), j.optString("transport_mode", "legacy"),
            j.optString("reference_clear_body"), j.optBoolean("reference_cleared"),
            j.optString("conversation_response"), j.optBoolean("historical"), j.optString("conversation_scope_id"), j.optString("planning_review"),
            j.optBoolean("message_rejected"), j.optString("conversation_recovery"))
    }
}
