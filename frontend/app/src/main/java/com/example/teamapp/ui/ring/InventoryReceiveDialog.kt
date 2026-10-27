package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import java.time.LocalDate
import java.util.UUID

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun InventoryReceiveDialog(store: InventoryStore, item: StockItem, dismiss: () -> Unit, received: () -> Unit = {}) {
    val s = rememberUiStrings()
    val scope = store.inventoryPreviewScope
    val focus = LocalFocusManager.current
    var quantity by rememberSaveable(scope, item.id) { mutableStateOf("") }
    var expiry by rememberSaveable(scope, item.id) { mutableStateOf<String?>(null) }
    var picking by rememberSaveable(scope, item.id) { mutableStateOf(false) }
    var submitted by remember(scope, item.id) { mutableStateOf(false) }
    val batchId = rememberSaveable(scope, item.id) { UUID.randomUUID().toString() }
    val preview = store.inventoryPreviews.preview(scope, item)
    val amount = store.inventoryPreviews.amount(item, quantity, preview)
    val validExpiry = expiry == null || runCatching { LocalDate.parse(expiry) }.isSuccess
    val valid = amount != null && validExpiry && item.activeBatch && !submitted

    Dialog(onDismissRequest = dismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(16.dp), contentAlignment = Alignment.Center) {
            Surface(Modifier.widthIn(max = 560.dp).fillMaxWidth().heightIn(max = maxHeight).testTag("inventory-receive-dialog"),
                shape = MaterialTheme.shapes.extraLarge, color = MaterialTheme.colorScheme.surface) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(s.get(R.string.ui_add_stock), style = MaterialTheme.typography.titleLarge)
                    Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(item.name, style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(quantity, { quantity = it }, singleLine = true,
                            label = { Text(s.get(R.string.ui_preview_receive_quantity)) },
                            suffix = { Text(item.unit) },
                            keyboardOptions = KeyboardOptions(keyboardType = if (item.hasPieceUnit()) KeyboardType.Number else KeyboardType.Decimal),
                            isError = quantity.isNotEmpty() && amount == null,
                            supportingText = { Text(s.get(if (item.hasPieceUnit()) R.string.ui_preview_integer_hint else R.string.ui_preview_decimal_hint)) },
                            modifier = Modifier.fillMaxWidth().testTag("inventory-receive-quantity"))
                        if (preview.individual) Text(s.get(R.string.ui_preview_limit, InventoryPreviewStore.MAX_PIECES), style = MaterialTheme.typography.bodySmall)
                        Text(s.get(R.string.ui_preview_expiry, expiry ?: s.get(R.string.ui_not_set)), modifier = Modifier.testTag("inventory-receive-expiry"))
                        OutlinedButton(onClick = { focus.clearFocus(); picking = true }, modifier = Modifier.fillMaxWidth().testTag("inventory-receive-pick-date")) {
                            Text(s.get(R.string.ui_preview_choose_date))
                        }
                        TextButton(onClick = { expiry = null }, modifier = Modifier.testTag("inventory-receive-clear-date")) { Text(s.get(R.string.ui_preview_no_expiry)) }
                        Text(s.get(R.string.ui_preview_session_note), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = dismiss, modifier = Modifier.weight(1f).testTag("inventory-receive-cancel")) { Text(s.get(R.string.ui_cancel)) }
                        Button(onClick = {
                            if (!submitted && valid) {
                                submitted = true
                                if (store.inventoryPreviews.receive(scope, item, quantity, expiry?.let(LocalDate::parse), batchId)) {
                                    focus.clearFocus()
                                    received()
                                    dismiss()
                                } else submitted = false
                            }
                        }, enabled = valid, modifier = Modifier.weight(1f).testTag("inventory-receive-confirm")) { Text(s.get(R.string.ui_preview_confirm)) }
                    }
                }
            }
        }
    }
    if (picking) InventoryExpiryDateDialog(expiry, dismiss = { picking = false }) {
        expiry = it.toString()
        picking = false
    }
}

/** Uses the existing CoverageDateDialog calendar style, with optional unrestricted expiry. */
@Composable
private fun InventoryExpiryDateDialog(current: String?, dismiss: () -> Unit, selected: (LocalDate) -> Unit) {
    val s = rememberUiStrings()
    val initial = remember(current) { current?.let(LocalDate::parse) }
    var month by remember { mutableStateOf(java.time.YearMonth.from(initial ?: LocalDate.now())) }
    // Viewing today's calendar never assigns today's expiry.
    var selection by remember { mutableStateOf(initial) }
    val colors = MaterialTheme.colorScheme
    AlertDialog(onDismissRequest = dismiss,
        title = { Text(s.get(R.string.ui_preview_choose_date)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { month = month.minusMonths(1) }, modifier = Modifier.testTag("inventory-expiry-previous")) { Text(s.get(R.string.ui_preview_previous_month)) }
                    Text(month.toString(), modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                    TextButton(onClick = { month = month.plusMonths(1) }, modifier = Modifier.testTag("inventory-expiry-next")) { Text(s.get(R.string.ui_preview_next_month)) }
                }
                Row(Modifier.fillMaxWidth()) {
                    s.get(R.string.ui_preview_weekdays).split(",").forEach { label ->
                        Text(label, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
                val leading = month.atDay(1).dayOfWeek.value % 7
                repeat((leading + month.lengthOfMonth() + 6) / 7) { week ->
                    Row(Modifier.fillMaxWidth()) {
                        repeat(7) { weekday ->
                            val day = week * 7 + weekday - leading + 1
                            if (day !in 1..month.lengthOfMonth()) Spacer(Modifier.weight(1f).height(40.dp))
                            else {
                                val date = month.atDay(day)
                                OutlinedButton(onClick = { selection = date }, modifier = Modifier.weight(1f).height(40.dp)
                                    .testTag("inventory-expiry-$date"), contentPadding = PaddingValues(0.dp),
                                    shape = androidx.compose.foundation.shape.CircleShape,
                                    border = if (selection == date) androidx.compose.foundation.BorderStroke(1.dp, colors.primary) else null,
                                    colors = ButtonDefaults.outlinedButtonColors(containerColor = if (selection == date) colors.primaryContainer else colors.surface)) {
                                    Text(day.toString(), style = MaterialTheme.typography.bodyMedium)
                                }
                            }
                        }
                    }
                }
                Text(s.get(R.string.ui_preview_expiry, selection?.toString() ?: s.get(R.string.ui_not_set)), style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(onClick = { selection?.let(selected) }, enabled = selection != null,
            modifier = Modifier.testTag("inventory-receive-date-confirm")) { Text(s.get(R.string.ui_preview_choose_date)) } },
        dismissButton = { TextButton(onClick = dismiss) { Text(s.get(R.string.ui_cancel)) } })
}
