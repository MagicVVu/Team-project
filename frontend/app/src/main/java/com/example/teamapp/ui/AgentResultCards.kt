package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import org.json.JSONObject

/** Values are server facts, never estimates derived from reply text or missing values. */
@Composable
internal fun AgentResultCards(result: JSONObject, facts: (String, String) -> Unit, events: (String) -> Unit) {
    val s = rememberUiStrings()
    fun rows(key: String) = result.optJSONArray(key)?.objects().orEmpty()
    fun missing(value: String) = value.ifBlank { s.tr("未知 / 尚不足以判断", "Unknown / insufficient data") }
    fun status(value: String) = when(value) {
        "available", "complete" -> s.tr("资料可用", "Available")
        "partial" -> s.tr("部分可用", "Partially available")
        "unavailable" -> s.tr("暂不可用", "Unavailable")
        "estimated" -> s.tr("有条件的参考估计", "Conditional estimate")
        "suggested" -> s.tr("建议待复核", "Suggestion for review")
        "covered" -> s.tr("已覆盖目标", "Target covered")
        "current_zero" -> s.tr("登记库存为零", "Recorded stock is zero")
        "no_recorded_consumption" -> s.tr("缺少已记录消费", "No recorded consumption")
        "needs_review", "insufficient_data", "unknown" -> s.tr("资料不足，需核对", "Insufficient data; review required")
        else -> missing(value)
    }
    fun sectionFor(fields: List<String>): String {
        val names = fields.joinToString(" ").lowercase()
        return when {
            "stock_verification" in names || "stock_count" in names -> "stock_verification"
            "coverage" in names || "record" in names || "observ" in names -> "coverage"
            listOf("minimum", "preference", "pack_size", "lead_days", "order_unit").any { it in names } -> "preferences"
            else -> "risk_facts"
        }
    }
    @Composable fun reasons(row: JSONObject) {
        val codes = row.optJSONArray("reason_codes")
        if (codes != null && codes.length() > 0) Text(s.tr("原因：", "Reasons: ") + (0 until codes.length()).joinToString { alignmentReason(codes.getString(it), s.english) }, style = MaterialTheme.typography.bodySmall)
    }
    Column(Modifier.fillMaxWidth().testTag("ai-structured-results"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        rows("sections").forEach { row -> AlignmentCard(if (row.optString("name") == "risk") s.tr("风险资料分区", "Risk section") else s.tr("规划资料分区", "Planning section")) {
            Text(status(row.optString("status")))
            Text(s.tr("读取时间：", "As of: ") + missing(row.stringOrEmpty("evaluated_at")), style = MaterialTheme.typography.bodySmall)
            if (row.stringOrEmpty("snapshot_id").isNotBlank()) Text(s.tr("快照：", "Snapshot: ") + row.getString("snapshot_id"), style = MaterialTheme.typography.labelSmall)
            reasons(row)
        } }
        rows("consumption_summary").forEach { row -> AlignmentCard(s.tr("已记录消费 · ", "Recorded consumption · ") + row.stringOrEmpty("name")) {
            Text(missing(row.stringOrEmpty("effective_quantity")) + " " + row.stringOrEmpty("unit"), style = MaterialTheme.typography.titleLarge)
            Text("${row.stringOrEmpty("window_start")} → ${row.stringOrEmpty("window_end_exclusive")} " + s.tr("（不含结束日）", "(end exclusive)"))
            Text(s.tr("有效事件 ${row.stringOrEmpty("effective_events")} 次 · 观察 ${row.stringOrEmpty("observed_days")} 天 · 消费分布 ${row.stringOrEmpty("consumption_dates")} 天", "${row.stringOrEmpty("effective_events")} effective events · ${row.stringOrEmpty("observed_days")} observed days · ${row.stringOrEmpty("consumption_dates")} consumption dates"))
            Text(status(row.optString("status"))); reasons(row)
            TextButton(onClick = { events("") }) { Text(s.tr("核对真实消费流水", "Review consumption ledger")) }
        } }
        rows("forecast").forEach { row -> AlignmentCard(s.tr("耗尽参考 · ", "Stock forecast · ") + row.stringOrEmpty("name")) {
            Text(status(row.optString("status")))
            Text(s.tr("登记库存：", "Recorded stock: ") + missing(row.stringOrEmpty("current_stock")) + " " + row.stringOrEmpty("unit"))
            Text(s.tr("日均记录消费：", "Daily recorded consumption: ") + missing(row.stringOrEmpty("daily_recorded_consumption")))
            Text(s.tr("参考剩余天数：", "Reference days remaining: ") + missing(row.stringOrEmpty("remaining_days")))
            Text(s.tr("参考日期：", "Reference date: ") + missing(row.stringOrEmpty("reference_date")))
            Text(row.stringOrEmpty("conditions"), style = MaterialTheme.typography.bodySmall)
            row.optJSONObject("summary")?.let { summary ->
                Text(s.tr("记录依据：完整观察 ${missing(summary.stringOrEmpty("observed_days"))}/14 天；有效消费 ${missing(summary.stringOrEmpty("effective_events"))}/5 次，分布 ${missing(summary.stringOrEmpty("consumption_dates"))}/3 天。",
                    "Recorded basis: ${missing(summary.stringOrEmpty("observed_days"))}/14 observed days; ${missing(summary.stringOrEmpty("effective_events"))}/5 effective events across ${missing(summary.stringOrEmpty("consumption_dates"))}/3 dates."), style = MaterialTheme.typography.bodySmall)
            }
            Text(s.tr("通常需至少 14 个连续完整日、5 次有效消费（跨至少 3 天）及有效库存盘点。不能预测不等于库存充足。", "Usually requires 14 complete consecutive days, 5 valid events across 3 dates and fresh stock verification. An unavailable forecast does not mean sufficient stock."), style = MaterialTheme.typography.bodySmall)
            reasons(row)
            TextButton(onClick = { facts("", "coverage") }) { Text(s.tr("核对记录与盘点资料", "Review recording & count facts")) }
        } }
        rows("recommendations").forEach { row -> AlignmentCard(s.tr("本次 AI 补货建议 · ", "AI restock suggestion · ") + row.stringOrEmpty("name")) {
            Text(status(row.optString("status")))
            listOf("current_stock" to s.tr("当前量", "Current"), "pending_quantity" to s.tr("待购量", "Pending"), "target_stock" to s.tr("目标量", "Target"), "suggested_quantity" to s.tr("建议量", "Suggested")).forEach { (key, label) ->
                Text("$label: ${missing(row.stringOrEmpty(key))} ${row.stringOrEmpty("unit")}")
            }
            Text(s.tr("依据：", "Basis: ") + when(row.stringOrEmpty("source")) { "minimum_stock" -> s.tr("最低库存", "Minimum stock"); "recorded_history" -> s.tr("已记录消费历史", "Recorded history"); else -> s.tr("待核对", "Needs review") })
            reasons(row)
            Text(s.tr("当前服务不支持计算建议直接提交。请在采购清单独立核对并明确输入手动采购数量。", "Calculated suggestions cannot be committed directly. Review and enter an explicit manual quantity in Shopping."), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { facts("", "preferences") }) { Text(s.tr("核对补货偏好", "Review restock preferences")) }
        } }
        rows("risks").forEach { row -> AlignmentCard(s.tr("风险资料 · ", "Risk facts · ") + row.stringOrEmpty("name")) {
            Text(if (row.optString("level") == "unknown") s.tr("未知，不能判断为安全", "Unknown; not a safety assurance") else row.stringOrEmpty("level"))
            Text(if (row.optBoolean("attention")) s.tr("需要关注", "Needs attention") else s.tr("未触发当前规则的关注标记，不表示安全", "No attention flag under current rules; this does not establish safety"))
            Text(row.stringOrEmpty("recommended_action")); reasons(row)
            row.optJSONArray("evidence")?.objects()?.forEach { evidence ->
                Text(evidence.stringOrEmpty("explanation"), style = MaterialTheme.typography.bodySmall)
                evidence.optJSONObject("source")?.let { Text(it.stringOrEmpty("ref"), style = MaterialTheme.typography.labelSmall) }
            }
            row.optJSONArray("missing_information")?.let { Text(s.tr("缺少资料：", "Missing facts: ") + it.toString(), style = MaterialTheme.typography.bodySmall) }
            Text(if (row.optBoolean("source_human_reviewed")) s.tr("来源已人工审核；结论仍受事实与规则限制", "Sources reviewed; conclusions remain limited by facts and rules") else s.tr("当前缺少已审核来源，不能给出专业安全结论", "Reviewed sources are unavailable; no professional safety conclusion"), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { facts(row.stringOrEmpty("batch_id"), "risk_facts") }) { Text(s.tr("补充这批的标签与储存资料", "Review this batch's label & storage")) }
        } }
        rows("guidance").forEach { row -> AlignmentCard(s.tr("补录任务", "Facts to review")) {
            row.optJSONArray("instructions")?.let { array -> repeat(array.length()) { Text(array.getString(it)) } }
            val fields = row.optJSONArray("missing_fields")?.let { values -> (0 until values.length()).map { values.getString(it) } }.orEmpty()
            TextButton(onClick = { facts(row.stringOrEmpty("batch_id"), sectionFor(fields)) }) { Text(s.tr("选择批次并补录", "Select batch & review facts")) }
        } }
        result.optJSONArray("data_gaps")?.takeIf { it.length() > 0 }?.let { gaps ->
            AlignmentCard(s.tr("资料缺口", "Data gaps")) { repeat(gaps.length()) { Text(gaps.getString(it)) } }
        }
        if (result.optBoolean("truncated")) Text(s.tr("仅展示部分结果；符合条件总数：", "Partial results only; total matching: ") + result.stringOrEmpty("total_count").ifBlank { s.tr("未知", "unknown") }, color = MaterialTheme.colorScheme.primary)
    }
}
