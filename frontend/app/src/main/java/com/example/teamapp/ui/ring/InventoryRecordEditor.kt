package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.Choice
import com.example.teamapp.ui.i18n.rememberUiStrings

/** Edits the selected preview record only. No parent item save or location persistence. */
@Composable
internal fun InventoryRecordEditor(store: InventoryStore, item: StockItem, record: InventoryPreviewRecord,
    number: Int, dismiss: () -> Unit) {
    val s = rememberUiStrings()
    val scope = store.inventoryPreviewScope
    val focus = LocalFocusManager.current
    var location by rememberSaveable(scope, item.id, record.id) { mutableStateOf(record.location) }
    var expiry by rememberSaveable(scope, item.id, record.id) { mutableStateOf(record.expiryDate) }
    var opened by rememberSaveable(scope, item.id, record.id) { mutableStateOf(record.openedAt) }
    var dateField by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf(false) }
    Dialog(onDismissRequest = dismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(16.dp), contentAlignment = Alignment.Center) {
            Surface(Modifier.widthIn(max = 560.dp).fillMaxWidth().heightIn(max = maxHeight).testTag("inventory-preview-record-editor"),
                shape = MaterialTheme.shapes.extraLarge) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(s.get(R.string.ui_preview_edit_record), style = MaterialTheme.typography.titleLarge)
                    Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(s.get(R.string.ui_preview_piece_title, item.name, number), style = MaterialTheme.typography.titleMedium)
                        Box(Modifier.testTag("inventory-preview-record-location")) {
                            Choice(s.get(R.string.ui_location), store.locations, location) { location = it }
                        }
                        OutlinedButton(onClick = { focus.clearFocus(); dateField = "expiry" }, modifier = Modifier.fillMaxWidth().testTag("inventory-preview-record-expiry")) {
                            Text(s.get(R.string.ui_preview_expiry, expiry ?: s.get(R.string.ui_not_set)))
                        }
                        TextButton(onClick = { expiry = null }, modifier = Modifier.testTag("inventory-preview-record-clear-expiry")) { Text(s.get(R.string.ui_preview_no_expiry)) }
                        OutlinedButton(onClick = { focus.clearFocus(); dateField = "opened" }, modifier = Modifier.fillMaxWidth().testTag("inventory-preview-record-opened")) {
                            Text(s.get(R.string.ui_preview_opened, opened ?: s.get(R.string.ui_preview_not_recorded)))
                        }
                        TextButton(onClick = { opened = null }, modifier = Modifier.testTag("inventory-preview-record-clear-opened")) { Text(s.get(R.string.ui_preview_clear_opened)) }
                        Text(s.get(R.string.ui_preview_session_note), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (failed) Text(s.get(R.string.ui_preview_record_error), color = MaterialTheme.colorScheme.error)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = dismiss, modifier = Modifier.weight(1f).testTag("inventory-preview-record-cancel")) { Text(s.get(R.string.ui_cancel)) }
                        Button(onClick = {
                            if (store.inventoryPreviews.updateRecord(scope, item.id, record.id, location, expiry, opened)) dismiss() else failed = true
                        }, enabled = location.isNotBlank(), modifier = Modifier.weight(1f).testTag("inventory-preview-record-save")) { Text(s.get(R.string.ui_save_changes)) }
                    }
                }
            }
        }
    }
    dateField?.let { field ->
        InventoryExpiryDateDialog(if (field == "expiry") expiry else opened, dismiss = { dateField = null },
            fieldLabel = s.get(if (field == "expiry") R.string.ui_preview_expiry_label else R.string.ui_preview_opened_label)) {
            if (field == "expiry") expiry = it.toString() else opened = it.toString()
            dateField = null
        }
    }
}
