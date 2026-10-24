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
