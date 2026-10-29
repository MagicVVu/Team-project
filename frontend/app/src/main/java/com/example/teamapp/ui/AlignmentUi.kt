package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.ui.i18n.UiStrings
import com.example.teamapp.ui.i18n.rememberUiStrings

internal fun UiStrings.tr(chinese: String, english: String) = if (this.english) english else chinese

@Composable
internal fun AlignmentCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
internal fun ContractChoice(label: String, options: List<Triple<String, String, String>>, value: String, change: (String) -> Unit) {
    val s = rememberUiStrings()
    val labels = options.map { s.tr(it.second, it.third) }
    Choice(label, labels, options.firstOrNull { it.first == value }?.let { s.tr(it.second, it.third) }.orEmpty()) { selected ->
        change(options[labels.indexOf(selected)].first)
    }
}

internal fun alignmentReason(code: String, english: Boolean): String {
    val planning = mapOf(
        "PRODUCT_USABLE_QUANTITY_UNKNOWN" to ("可用量尚未核实" to "Usable quantity is unknown"),
        "PRODUCT_COVERAGE_UNKNOWN" to ("商品缺少完整消费记录范围" to "Product consumption coverage is unknown"),
        "PRODUCT_PREFERENCES_NOT_AGGREGATED" to ("各批次补货偏好尚未汇总" to "Batch restock preferences are not aggregated"),
        "PRODUCT_UNIT_CONFLICT" to ("批次单位不能可靠换算，总量未知" to "Batch units conflict; total quantity is unknown"),
        "PRODUCT_EXPIRY_UNKNOWN" to ("部分批次缺少到期日期" to "Some batch expiry dates are unknown"),
        "PRODUCT_EXPIRED_BATCH_PRESENT" to ("包含已过标示日期的批次" to "Some batches are past their label dates"),
        "PRODUCT_TERMINAL_BATCH_PRESENT" to ("包含已用完或已丢弃等非活动批次" to "Some batches are no longer active"),
        "PENDING_ASSOCIATION_UNKNOWN" to ("待购来源不完整，待购量不能当成零" to "Pending sources are incomplete; quantity is not zero"),
        "PROCUREMENT_SOURCE_REQUIRED" to ("请先明确采购对应的真实批次" to "Select a real procurement source batch"),
        "HUMAN_RULE_REVIEW_REQUIRED" to ("缺少已审核的规划规则" to "Reviewed planning rules are missing"),
        "RISK_RULE_REVIEW_REQUIRED" to ("风险规则尚需人工审核" to "Risk rules require review"),
        "AUTOMATIC_PLANNING_NOT_APPROVED" to ("自动补货提交尚未开放" to "Automatic restock submission is unavailable"),
        "CONSUMPTION_COVERAGE_UNKNOWN" to ("消费记录覆盖范围未知" to "Consumption coverage is unknown"),
        "STOCK_VERIFICATION_REQUIRED" to ("请先核对实际库存" to "Verify actual stock first"),
        "STOCK_VERIFICATION_STALE" to ("库存核对已过期，请重新盘点" to "Stock verification expired; count again"),
        "HISTORY_TRANSPORT_INCOMPLETE" to ("历史记录未读取完整" to "History was not fully read"),
        "EVENT_UNIT_CONFLICT" to ("消费记录单位不兼容" to "Consumption event units are incompatible"),
        "PENDING_UNIT_CONFLICT" to ("待购数量单位不兼容" to "Pending quantity units are incompatible"),
        "inventory_versions" to ("库存数量或状态已有变化" to "Stock quantity or status changed"),
        "facts_versions" to ("物品资料已有更新" to "Item facts changed"),
        "product_versions" to ("商品关联已有更新" to "Product links changed"),
        "event_watermark" to ("消费等流水记录已有更新" to "Inventory ledger events changed"),
        "shopping_version" to ("待购清单已有变化" to "Pending purchases changed"),
        "risk_rules" to ("计算使用的规则已有变化" to "Calculation rules changed"),
        "snapshot_id" to ("计算时的数据已更新" to "The calculation snapshot changed"),
        "BASIS_MISSING_OR_UNSUPPORTED" to ("缺少可核对的原建议依据" to "Original suggestion basis is unavailable"),
        "PROCUREMENT_SOURCE_INVALID_OR_CHANGED" to ("原采购来源已变化，请重新选择" to "Procurement source changed; select it again"),
        "PRODUCT_IDENTITY_REQUIRED" to ("请先明确商品与批次关联" to "Confirm product and batch links first"),
        "CONSUMPTION_COVERAGE_INCOMPLETE" to ("消费记录的观察范围尚不完整" to "Consumption observation coverage is incomplete")
    )
    planning[code]?.let { return if (english) it.second else it.first }
    if (!english) return com.example.teamapp.data.ChatMessages.reason(code, code)
    return when(code) {
        "STOCK_COUNT_MISMATCH" -> "The count differs from current stock. Correct stock, refresh, then explicitly verify again."
        "PLANNING_FACTS_VERSION_CONFLICT", "INVENTORY_VERSION_CONFLICT" -> "This record changed. Read the latest version and review your entries before saving again."
        "COVERAGE_DAY_OUT_OF_RANGE" -> "Only completed household calendar dates can be recorded; today and future dates are excluded."
        "COVERAGE_LIMIT_EXCEEDED" -> "Record at most 366 dates per request and 3660 dates in total."
        "LABEL_DATE_REQUIRED" -> "Set the package date before confirming the label context."
        "OPENED_STATE_CONFLICT" -> "This batch is already opened. Its recorded opening cannot be denied."
        "HOUSEHOLD_TIMEZONE_MISMATCH" -> "The household timezone changed. Refresh dates before submitting."
        "OPERATION_ID_CONFLICT" -> "The original operation has different content. Keep the original request and verify its result."
        else -> code
    }
}
