package com.example.teamapp.data

import org.json.JSONObject
import java.util.Locale

/** Dialogue progress is informational; only task state and receipts authorize actions. */
internal object ConversationFeedback {
    fun dialogue(raw: String, locale: String = "zh-CN"): String {
        val metadata = raw.takeIf { it.isNotBlank() }?.let(::JSONObject)?.optJSONObject("dialogue") ?: return ""
        if (locale == "en") return when (metadata.stringOrEmpty("status")) {
            "", "completed" -> ""
            "needs_input" -> "More information is needed. Review the reply and supply the missing details."
            "needs_confirmation" -> "Waiting for your review and confirmation; nothing has been executed."
            "stopped" -> {
                val reason = when (metadata.stringOrEmpty("loop_stop_reason").ifBlank { metadata.stringOrEmpty("stop_reason") }) {
                    "deadline", "timeout", "time_budget_exceeded", "deadline_exceeded", "processing_timeout" -> "the time limit was reached"
                    "repeated_plan", "no_progress" -> "further processing produced no new verified information"
                    "context_limit" -> "the required context exceeds this turn's capacity"
                    "ai_unavailable", "model_error" -> "the AI service is unavailable"
                    else -> "more information or a manual review is required"
                }
                "Stopped: $reason. Verified results are retained; review them before continuing."
            }
            else -> "The processing status is unavailable. The original reply and verified information are retained."
        }
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

    fun recovery(phase: String, hint: String, locale: String = "zh-CN"): String {
        if (locale == "en") return when (phase) {
            "completed" -> ""
            "prepared" -> "Understanding is saved. Recover the original request to continue without another interpretation call."
            "processing" -> "The original message is processing. Check its result later."
            "result_unknown" -> "The outcome is not verified. No automatic model retry will be started."
            else -> "Recovery status is unavailable. Keep the original request and check again later."
        }
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
