package com.example.teamapp.ui.ring

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.Photo
import com.example.teamapp.ui.i18n.rememberUiStrings

/** The animated host and existing edit/consume/delete flows retain their ownership. */
@Composable
internal fun InventoryDetailContent(
    store: InventoryStore, item: StockItem, open: (String) -> Unit, delete: () -> Unit,
    reveal: (Int) -> Modifier
) {
    val s = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val scope = store.inventoryPreviewScope
    val preview = store.inventoryPreviews.preview(scope, item)
    val listState = rememberLazyListState()
    var firstAdded by remember(scope, item.id) { mutableIntStateOf(-1) }
    LaunchedEffect(firstAdded) {
        if (firstAdded >= 0) listState.animateScrollToItem(3 + firstAdded)
    }
    var receiving by remember(scope, item.id) { mutableStateOf(false) }
    var history by remember(scope, item.id) { mutableStateOf(false) }

    LazyColumn(Modifier.fillMaxSize().testTag("inventory-detail-content"), state = listState,
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item(key = "identity") {
            Row(reveal(0).fillMaxWidth().testTag("inventory-detail-identity"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                RingItemIllustration(item, Modifier.size(48.dp))
                Column(Modifier.weight(1f)) {
                    Text(item.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.testTag("inventory-detail-name"))
                    Text(s.label(item.category), style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                }
                FilledTonalButton(onClick = { receiving = true }, enabled = item.activeBatch && item.unit == preview.baseline.unit,
                    colors = ButtonDefaults.filledTonalButtonColors(containerColor = colors.primaryContainer, contentColor = colors.onPrimaryContainer),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    modifier = Modifier.testTag("inventory-detail-receive")) { Text(s.get(R.string.ui_preview_receive)) }
            }
        }
        item(key = "summary") {
            Column(reveal(1).fillMaxWidth().testTag("inventory-detail-stock"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(s.get(R.string.ui_preview_current), style = MaterialTheme.typography.labelLarge, color = colors.onSurfaceVariant)
                Text("${preview.total.previewText()} ${preview.baseline.unit}", style = MaterialTheme.typography.headlineMedium,
                    color = colors.primary, modifier = Modifier.testTag("inventory-detail-quantity"))
                Text(s.get(if (store.cloud.signedIn) R.string.ui_preview_server_stock else R.string.ui_preview_saved_stock,
                    item.quantityText, item.unit), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant,
                    modifier = Modifier.testTag("inventory-detail-saved-quantity"))
                Text(s.get(R.string.ui_preview_session_note), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                if (preview.originalChanged(item)) Text(s.get(if (item.unit == preview.baseline.unit) R.string.ui_preview_changed else R.string.ui_preview_unit_changed), style = MaterialTheme.typography.bodySmall,
                    color = colors.error, modifier = Modifier.testTag("inventory-preview-changed"))
                Text(s.get(R.string.ui_minimum_stock) + (if (s.english) ": " else "：") + "${item.minimum.display()} ${item.unit}",
                    style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
        }
        item(key = "records-heading") {
            Column(reveal(2).testTag("inventory-detail-facts"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(s.get(if (preview.individual) R.string.ui_preview_pieces else R.string.ui_preview_batches),
                    style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                if (!preview.individual) Text(s.get(R.string.ui_preview_aggregate_note),
                    style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
        }
        if (preview.records.isEmpty()) item(key = "empty") {
            Surface(reveal(2).fillMaxWidth(), shape = MaterialTheme.shapes.large, color = colors.surfaceVariant.copy(alpha = .4f)) {
                Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(s.get(R.string.ui_preview_empty), style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = { receiving = true }, enabled = item.activeBatch,
                        modifier = Modifier.testTag("inventory-detail-empty-receive")) { Text(s.get(R.string.ui_preview_receive)) }
                }
            }
        }
        itemsIndexed(preview.records, key = { _, record -> record.id }) { index, record ->
            Surface(reveal(2).fillMaxWidth().testTag("inventory-preview-record-${index + 1}"),
                shape = MaterialTheme.shapes.large, color = colors.surfaceVariant.copy(alpha = .35f),
                border = BorderStroke(1.dp, colors.outlineVariant.copy(alpha = .6f))) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(s.get(if (preview.individual) R.string.ui_preview_piece_title else R.string.ui_preview_batch_title,
                        item.name, index + 1), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
                    if (!preview.individual) Text("${record.quantity.previewText()} ${preview.baseline.unit}", color = colors.primary)
                    Text(s.get(R.string.ui_preview_location, record.location.ifBlank { s.get(R.string.ui_not_set) }),
                        style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                    Text(s.get(R.string.ui_preview_expiry, record.expiryDate ?: s.get(R.string.ui_not_set)),
                        style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                    Text(s.get(R.string.ui_preview_opened, record.openedAt ?: s.get(R.string.ui_preview_not_recorded)),
                        style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                }
            }
        }
        item(key = "actions") {
            Column(reveal(3).fillMaxWidth().testTag("inventory-detail-actions"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HorizontalDivider()
                Photo(item.image)
                Text(s.get(R.string.ui_preview_actions_note), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { open("编辑物品") }, modifier = Modifier.weight(1f).testTag("inventory-detail-edit")) { Text(s.get(R.string.ui_edit)) }
                    OutlinedButton(onClick = { open("消耗库存") }, enabled = item.activeBatch,
                        modifier = Modifier.weight(1f).testTag("inventory-detail-consume")) { Text(s.get(R.string.ui_use_stock)) }
                }
                TextButton(onClick = { history = !history }, modifier = Modifier.testTag("inventory-detail-history")) { Text(s.get(R.string.ui_quantity_history)) }
                if (history) item.history.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                TextButton(onClick = delete, modifier = Modifier.testTag("inventory-detail-delete")) { Text(s.get(R.string.ui_delete_item), color = colors.error) }
            }
        }
    }
    if (receiving) InventoryReceiveDialog(store, item, dismiss = { receiving = false }, received = { firstAdded = preview.records.size })
}
