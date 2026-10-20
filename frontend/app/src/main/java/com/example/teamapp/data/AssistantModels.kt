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
    val failureCode: String = ""
) {
    val taskJson get() = JSONObject(task)
    val draftJson get() = JSONObject(draft)
    val executionJson get() = JSONObject(execution)
    val result get() = taskJson.optJSONObject("result") ?: JSONObject()
    val command get() = draftJson.optJSONObject("draft") ?: result.optJSONObject("draft") ?: JSONObject()
    val taskId get() = taskJson.stringOrEmpty("task_id")
    val draftId get() = taskJson.stringOrEmpty("draft_id").ifBlank { executionJson.stringOrEmpty("draft_id") }
    val operationId get() = if (commitBody.isBlank()) "" else JSONObject(commitBody).getString("operation_id")
    val taskRevision get() = taskJson.optInt("revision")
    val draftRevision get() = draftJson.optInt("revision")
    val taskStatus get() = taskJson.stringOrEmpty("status")
    val executionStatus get() = executionJson.stringOrEmpty("status")
    val errorCode get() = failureCode.ifBlank { executionJson.stringOrEmpty("reason_code").ifBlank { result.stringOrEmpty("error_code") } }
    val action get() = command.stringOrEmpty("action")
    val reply get() = result.stringOrEmpty("reply")
    val preview get() = draftJson.optJSONObject("preview") ?: result.optJSONObject("preview") ?: JSONObject()
    val allowedFields get() = result.optJSONObject("clarification")?.optJSONArray("allowed_fields")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()
    val candidates get() = result.optJSONArray("candidates")?.objects().orEmpty()
    val editableFields get() = executionJson.optJSONArray("editable_fields")?.let { a ->
        (0 until a.length()).map { a.getString(it) }.filter { it in AgentExecutionPolicy.editable[action].orEmpty() }
    }.orEmpty()
    fun toJson() = JSONObject().put("request_id", requestId).put("request_body", requestBody).put("task", task)
        .put("draft", draft).put("execution", execution).put("commit_body", commitBody).put("clarification_body", clarificationBody)
        .put("cancel_body", cancelBody).put("edits", JSONObject(edits)).put("state", state.name).put("notice", notice)
        .put("receipt", receipt).put("refresh_needed", refreshNeeded).put("failure_code", failureCode)
    companion object {
        fun fromJson(j: JSONObject) = AssistantEntry(j.getString("request_id"), j.getString("request_body"), j.getString("task"),
            j.getString("draft"), j.getString("execution"), j.optString("commit_body"), j.optString("clarification_body"), j.optString("cancel_body"),
            j.optJSONObject("edits")?.let { v -> v.keys().asSequence().associateWith { v.getString(it) } }.orEmpty(),
            AssistantStatus.valueOf(j.getString("state")), j.optString("notice"), j.optString("receipt"), j.optBoolean("refresh_needed"), j.optString("failure_code"))
    }
}
