package com.example.teamapp.ui.ring

import androidx.compose.animation.core.tween
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
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.Photo
import com.example.teamapp.ui.i18n.rememberUiStrings

/** The host still owns global edit/shopping/delete routes and its expansion animation. */
@Composable
internal fun InventoryDetailContent(
    store: InventoryStore, item: StockItem, open: (String) -> Unit, delete: () -> Unit,
    reveal: (Int) -> Modifier
) {
    key(store, store.inventoryPreviewScope, item.id) {
        InventoryDetailBody(store, item, open, delete, reveal)
    }
}

@Composable
private fun InventoryDetailBody(store: InventoryStore, item: StockItem, open: (String) -> Unit,
    delete: () -> Unit, reveal: (Int) -> Modifier) {
    val s = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val scope = store.inventoryPreviewScope
    val preview = store.inventoryPreviews.preview(scope, item)
    val listState = rememberLazyListState()
    var firstAddedId by remember { mutableStateOf<String?>(null) }
    var expandedId by remember { mutableStateOf<String?>(null) }
    var editingId by remember { mutableStateOf<String?>(null) }
    var receiving by remember { mutableStateOf(false) }
    LaunchedEffect(firstAddedId) {
        val index = preview.records.indexOfFirst { it.id == firstAddedId }
        if (index >= 0) listState.animateScrollToItem(3 + index)
    }
    LaunchedEffect(preview.records.map { it.id }) {
        if (preview.records.none { it.id == expandedId }) expandedId = null
        if (preview.records.none { it.id == editingId }) editingId = null
    }
    fun receive() { expandedId = null; receiving = true }

    LazyColumn(Modifier.fillMaxSize().testTag("inventory-detail-content"), state = listState,
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 8.dp)) {
        item(key = "identity") {
            Row(reveal(0).fillMaxWidth().padding(bottom = 12.dp).testTag("inventory-detail-identity"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                RingItemIllustration(item, Modifier.size(48.dp))
                Column(Modifier.weight(1f)) {
                    Text(item.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold, color = colors.onSurface,
                        modifier = Modifier.testTag("inventory-detail-name"))
                    Text(s.label(item.category), style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                }
                FilledTonalButton(onClick = { expandedId = null; open("编辑物品") },
                    colors = ButtonDefaults.filledTonalButtonColors(containerColor = colors.primaryContainer, contentColor = colors.onPrimaryContainer),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    modifier = Modifier.testTag("inventory-detail-edit")) { Text(s.get(R.string.ui_edit)) }
            }
        }
        item(key = "summary") {
            Column(reveal(1).fillMaxWidth().padding(bottom = 12.dp).testTag("inventory-detail-stock"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(s.get(R.string.ui_preview_current), style = MaterialTheme.typography.labelLarge, color = colors.onSurfaceVariant)
                Text("${preview.total.previewText()} ${preview.baseline.unit}", style = MaterialTheme.typography.headlineMedium,
                    color = colors.primary, modifier = Modifier.testTag("inventory-detail-quantity"))
                Text(s.get(if (store.cloud.signedIn) R.string.ui_preview_server_stock else R.string.ui_preview_saved_stock,
                    item.quantityText, item.unit), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant,
                    modifier = Modifier.testTag("inventory-detail-saved-quantity"))
                Text(s.get(R.string.ui_preview_session_note), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                if (preview.originalChanged(item)) Text(s.get(if (item.unit == preview.baseline.unit) R.string.ui_preview_changed else R.string.ui_preview_unit_changed),
                    style = MaterialTheme.typography.bodySmall, color = colors.error, modifier = Modifier.testTag("inventory-preview-changed"))
                Text(s.get(R.string.ui_minimum_stock) + (if (s.english) ": " else "：") + "${item.minimum.display()} ${item.unit}",
                    style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
        }
        item(key = "records-heading") {
            Column(reveal(2).padding(bottom = 12.dp).testTag("inventory-detail-facts"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(s.get(if (preview.individual) R.string.ui_preview_pieces else R.string.ui_preview_batches),
                    style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                Text(s.get(if (preview.individual) R.string.ui_preview_swipe_hint else R.string.ui_preview_aggregate_note),
                    style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
        }
        if (preview.records.isEmpty()) item(key = "empty") {
            Surface(reveal(2).fillMaxWidth().padding(bottom = 12.dp), shape = MaterialTheme.shapes.large, color = colors.surfaceVariant.copy(alpha = .4f)) {
                Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(s.get(R.string.ui_preview_empty), style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = ::receive, enabled = item.activeBatch && item.unit == preview.baseline.unit,
                        modifier = Modifier.testTag("inventory-detail-empty-receive")) { Text(s.get(R.string.ui_preview_receive)) }
                }
            }
        }
        itemsIndexed(preview.records, key = { _, record -> record.id }) { index, record ->
            InventoryPreviewRow(item, record, index + 1, preview.individual, preview.baseline.unit,
                expanded = expandedId == record.id,
                setExpanded = { expanded -> if (expanded) expandedId = record.id else if (expandedId == record.id) expandedId = null },
                edit = { editingId = record.id },
                opened = { store.inventoryPreviews.markOpened(scope, item.id, record.id) },
                consumed = { store.inventoryPreviews.consumeRecord(scope, item.id, record.id) },
                modifier = Modifier.animateItem(fadeInSpec = null, fadeOutSpec = null, placementSpec = tween(240, easing = AppMotion.easing)).then(reveal(2)))
        }
        item(key = "actions") {
            Column(reveal(3).fillMaxWidth().testTag("inventory-detail-actions"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (item.image.isNotBlank()) Photo(item.image)
                Button(onClick = ::receive, enabled = item.activeBatch && item.unit == preview.baseline.unit,
                    modifier = Modifier.fillMaxWidth().testTag("inventory-detail-receive")) { Text(s.get(R.string.ui_preview_receive)) }
                OutlinedButton(onClick = {
                    expandedId = null
                    open(if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单")
                }, modifier = Modifier.fillMaxWidth().testTag("inventory-detail-shopping")) { Text(s.get(R.string.ui_preview_shopping)) }
                TextButton(onClick = { expandedId = null; delete() }, modifier = Modifier.testTag("inventory-detail-delete")) { Text(s.get(R.string.ui_delete_item), color = colors.error) }
            }
        }
    }
    if (receiving) InventoryReceiveDialog(store, item, dismiss = { receiving = false }, received = {
        firstAddedId = store.inventoryPreviews.preview(scope, item).records.getOrNull(preview.records.size)?.id
    })
    preview.records.firstOrNull { it.id == editingId }?.let { record ->
        InventoryRecordEditor(store, item, record, preview.records.indexOf(record) + 1, dismiss = { editingId = null; expandedId = null })
    }
}
