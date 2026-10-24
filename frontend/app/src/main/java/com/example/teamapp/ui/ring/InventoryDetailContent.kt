package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.display
import com.example.teamapp.data.activeBatch
import com.example.teamapp.data.InventoryContract
import com.example.teamapp.ui.tr
import com.example.teamapp.ui.Photo
import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.ui.reasons

/** Presentation only: all mutations and delete confirmation use the existing Detail host. */
@Composable
internal fun InventoryDetailContent(
    store: InventoryStore, item: StockItem, open: (String) -> Unit, delete: () -> Unit,
    reveal: (Int) -> Modifier
) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp, vertical = 8.dp)
        .testTag("inventory-detail-content"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(reveal(0).fillMaxWidth().testTag("inventory-detail-identity"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            RingItemIllustration(item, Modifier.size(56.dp))
            Column(Modifier.weight(1f)) {
                Text(item.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.testTag("inventory-detail-name"))
                Text(strings.label(item.category), style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
            }
        }
        Column(reveal(1).fillMaxWidth().testTag("inventory-detail-stock"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${item.quantity.display()} ${item.unit}", style = MaterialTheme.typography.headlineLarge, color = colors.primary,
                modifier = Modifier.testTag("inventory-detail-quantity"))
            Text("${strings.get(R.string.ui_minimum_stock)}${if (strings.english) ": " else "："}${item.minimum.display()} ${item.unit}",
                style = MaterialTheme.typography.bodyMedium)
            Surface(color = colors.secondaryContainer, shape = MaterialTheme.shapes.medium) {
                Text(reasons(item, store.reminderDays, concise = true, strings = strings),
                    style = MaterialTheme.typography.bodyMedium, modifier = Modifier.fillMaxWidth().padding(12.dp))
            }
        }
        Column(reveal(2).fillMaxWidth().testTag("inventory-detail-facts"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(strings.get(R.string.ui_location_3), style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
            Text(item.location.ifBlank { strings.get(R.string.ui_not_set) })
            Text(strings.get(R.string.ui_expires, item.expiry.ifBlank { strings.get(R.string.ui_not_set) }), style = MaterialTheme.typography.bodyMedium)
            if (store.cloud.signedIn) {
                Text(strings.tr("开封日期：", "Opened: ") + item.openedAt.ifBlank { strings.tr("未登记", "Not recorded") })
                Text(strings.tr("批次状态：", "Batch status: ") + item.lifecycleStatus)
                Text(strings.tr("登记日期与库存阈值提醒不等同于安全结论。", "Registered dates and stock thresholds do not establish safety."), style = MaterialTheme.typography.bodySmall)
                if (!InventoryContract.compatible(item)) Text(strings.tr("旧记录需要核对名称或单位后才能使用 AI。", "Review this legacy name or unit before using AI."), color = colors.error)
            }
            Photo(item.image)
        }
        Column(reveal(3).fillMaxWidth().testTag("inventory-detail-actions"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { open("编辑物品") }, modifier = Modifier.fillMaxWidth().testTag("inventory-detail-edit")) { Text(strings.get(R.string.ui_edit)) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { open("增加库存") }, enabled = item.activeBatch, modifier = Modifier.weight(1f)) { Text(strings.get(R.string.ui_add_stock)) }
                OutlinedButton(onClick = { open("消耗库存") }, enabled = item.activeBatch, modifier = Modifier.weight(1f)) { Text(strings.get(R.string.ui_use_stock)) }
            }
            if (store.cloud.signedIn) {
                OutlinedButton(onClick = { open("资料与盘点") }, modifier = Modifier.fillMaxWidth().testTag("inventory-planning-facts")) { Text(strings.tr("资料与盘点", "Facts & stock verification")) }
                OutlinedButton(onClick = { open("批次操作") }, modifier = Modifier.fillMaxWidth().testTag("inventory-batch-actions")) { Text(strings.tr("开封、丢弃与询问这批", "Open, discard & ask about this batch")) }
                OutlinedButton(onClick = { open("消费流水") }, modifier = Modifier.fillMaxWidth()) { Text(strings.tr("真实消费流水", "Consumption ledger")) }
                TextButton(onClick = { open("盘点修正") }) { Text(strings.tr("盘点修正数量（不计消费）", "Correct count (not consumption)")) }
            }
            Button(onClick = { open(if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") },
                modifier = Modifier.fillMaxWidth()) { Text(strings.get(R.string.ui_add_to_list___adjust)) }
            Text(strings.get(R.string.ui_quantity_history), fontWeight = FontWeight.SemiBold)
            item.history.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
            TextButton(onClick = delete) { Text(strings.get(R.string.ui_delete_item), color = colors.error) }
        }
    }
}
