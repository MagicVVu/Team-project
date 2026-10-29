package com.example.teamapp.data

import org.json.JSONObject
import java.util.Locale

/** Dialogue progress is informational; only task state and receipts authorize actions. */
internal object ConversationFeedback {
    fun dialogue(raw: String): String {
        val metadata = raw.takeIf { it.isNotBlank() }?.let(::JSONObject)?.optJSONObject("dialogue") ?: return ""
        return when (metadata.stringOrEmpty("status")) {
            "", "completed" -> ""
            "needs_input" -> "需要补充资料，请查看本轮回答后继续补充。"
            "needs_confirmation" -> "等待你核对并确认；尚未执行。"
            "stopped" -> {
                val reason = when (metadata.stringOrEmpty("stop_reason").lowercase(Locale.ROOT)) {
                    "timeout", "time_budget_exceeded", "deadline_exceeded", "processing_timeout" -> "处理超时"
                    "insufficient_data", "insufficient_information", "missing_information", "needs_input" -> "资料不足"
                    "model_call_limit", "max_model_calls", "call_budget_exceeded" -> "已达到本轮处理次数上限"
                    "ai_unavailable" -> "AI 服务暂时不可用"
                    else -> "本轮处理未能继续，具体原因暂无法识别"
                }
                "已停止：$reason。已查到的结果仍保留，请核对后继续。"
            }
            else -> "本轮返回了暂不支持的处理状态，回答和已查到的结果仍保留，请先核对。"
        }
    }

    fun recovery(phase: String, hint: String): String {
        val message = when (phase) {
            "completed" -> ""
            "prepared" -> "理解已保存；点击核实恢复可按原请求继续，不重新理解"
            "processing" -> "原消息仍在处理中，请稍后查询"
            "result_unknown" -> "理解结果尚未核实，不会自动再次调用模型"
            else -> "暂无法识别恢复状态，原请求和已有结果已保留，请稍后核实"
        }
        return listOf(message, hint).filter { it.isNotBlank() }.joinToString("；")
    }
}
