package com.example.teamapp.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.example.teamapp.ui.i18n.rememberUiStrings
import java.time.LocalDate
import java.time.YearMonth

/** Explicit weekday labels avoid narrow Chinese weekday truncation on older Android ICU. */
@Composable
internal fun CoverageDateDialog(today: LocalDate, current: String, dismiss: () -> Unit, selected: (LocalDate) -> Unit) {
    val s = rememberUiStrings()
    val initial = remember(current) { runCatching { LocalDate.parse(current) }.getOrNull()?.takeIf { it < today } }
    var month by remember { mutableStateOf(YearMonth.from(initial ?: today)) }
    var selection by remember { mutableStateOf(initial) }
    val colors = MaterialTheme.colorScheme
    AlertDialog(onDismissRequest = dismiss,
        title = { Text(s.tr("选择已结束日期", "Choose a completed date")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { month = month.minusMonths(1) }) { Text(s.tr("上月", "Previous")) }
                    Text(month.toString(), modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                    TextButton(onClick = { month = month.plusMonths(1) }, enabled = month < YearMonth.from(today)) { Text(s.tr("下月", "Next")) }
                }
                Row(Modifier.fillMaxWidth()) {
                    val labels = if (s.english) listOf("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa") else listOf("日", "一", "二", "三", "四", "五", "六")
                    labels.forEachIndexed { index, label -> Text(label, modifier = Modifier.weight(1f).testTag("coverage-weekday-$index"),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center, style = MaterialTheme.typography.labelMedium) }
                }
                val leading = month.atDay(1).dayOfWeek.value % 7
                val weeks = (leading + month.lengthOfMonth() + 6) / 7
                repeat(weeks) { week ->
                    Row(Modifier.fillMaxWidth()) {
                        repeat(7) { weekday ->
                            val day = week * 7 + weekday - leading + 1
                            if (day !in 1..month.lengthOfMonth()) Spacer(Modifier.weight(1f).height(40.dp))
                            else {
                                val date = month.atDay(day)
                                OutlinedButton(onClick = { selection = date }, enabled = date < today,
                                    modifier = Modifier.weight(1f).height(40.dp).testTag("coverage-day-$date").semantics { contentDescription = date.toString() },
                                    contentPadding = PaddingValues(0.dp), shape = CircleShape,
                                    border = if (selection == date) BorderStroke(1.dp, colors.primary) else null,
                                    colors = ButtonDefaults.outlinedButtonColors(containerColor = if (selection == date) colors.primaryContainer else colors.surface)) {
                                    Text(day.toString(), style = MaterialTheme.typography.bodyMedium)
                                }
                            }
                        }
                    }
                }
                Text(selection?.toString() ?: s.tr("今天和未来不可登记完整记录。", "Today and future dates cannot be marked complete."), style = MaterialTheme.typography.bodySmall)
            }
        }, confirmButton = { TextButton(onClick = { selection?.let(selected) }, enabled = selection != null) { Text(s.tr("选择日期", "Select date")) } },
        dismissButton = { TextButton(onClick = dismiss) { Text(s.tr("取消", "Cancel")) } })
}
