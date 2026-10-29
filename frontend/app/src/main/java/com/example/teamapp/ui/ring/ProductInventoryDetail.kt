package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings

/** Every row has a durable server identity and represents one physical object. */
@Composable
internal fun ProductInventoryDetail(product: CloudProduct, cloudMode: Boolean = true, action: (StockItem, String) -> Unit) {
    val s = rememberUiStrings()
    val summary = product.ringItem(s.english)
    var showEnded by remember(product.id) { mutableStateOf(false) }
    val endedCount = product.batches.size - product.count
    val records = if (showEnded) product.batches else product.activeItems
    CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onSurface) {
    LazyColumn(Modifier.fillMaxSize().testTag("product-inventory-detail"),
        contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text(product.name, style = MaterialTheme.typography.headlineSmall)
            if (product.specification.isNotBlank()) Text(product.specification)
            Text(s.label(product.category), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(summary.stockCountText, style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary)
            Text(if (s.english) "Each row is one item. Open, edit or use each item separately." else "每行代表一件物品，可分别编辑、开封或消耗。",
                style = MaterialTheme.typography.bodySmall)
            if (endedCount > 0) TextButton(onClick = { showEnded = !showEnded }, modifier = Modifier.testTag("product-show-ended")) {
                Text(if (showEnded) { if (s.english) "Hide ended items" else "隐藏已结束物品" }
                    else { if (s.english) "Show $endedCount ended items" else "查看${endedCount}件已结束物品" })
            }
        }
        if (records.isEmpty()) item {
            Text(if (s.english) "No items currently in stock." else "当前没有在库物品。")
        }
        items(records, key = { it.id }) { batch ->
            OutlinedCard(Modifier.fillMaxWidth().testTag("product-batch-${batch.id}")) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(batch.name, style = MaterialTheme.typography.titleMedium)
                    if (batch.specification.isNotBlank()) Text(batch.specification, color = MaterialTheme.colorScheme.primary)
                    Text((if (s.english) "Location: " else "位置：") + batch.location)
                    Text((if (s.english) "Expiry: " else "有效期：") + batch.expiry.ifBlank { if (s.english) "Not recorded" else "未登记" })
                    Text((if (s.english) "Received: " else "购入日期：") + batch.purchasedAt.ifBlank { if (s.english) "Not recorded" else "未登记" })
                    Text((if (s.english) "Opened: " else "开封日期：") + batch.openedAt.ifBlank { if (s.english) "Not recorded" else "未登记" })
                    Text((if (s.english) "Status: " else "状态：") + when (batch.lifecycleStatus) {
                        "ACTIVE" -> if (s.english) "In stock" else "在库"
                        "FINISHED" -> if (s.english) "Finished" else "已用完"
                        "DISCARDED" -> if (s.english) "Discarded" else "已丢弃"
                        "REVERSED" -> if (s.english) "Reversed" else "已撤销"
                        else -> batch.lifecycleStatus
                    })
                    if (batch.activeBatch) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { action(batch, "编辑物品") }) { Text(if (s.english) "Edit" else "编辑") }
                            TextButton(onClick = { action(batch, "消耗库存") }, modifier = Modifier.testTag("consume-item-${batch.id}")) { Text(if (s.english) "Use this item" else "消耗这件") }
                            if (cloudMode) TextButton(onClick = { action(batch, "批次操作") }) { Text(if (s.english) "More" else "更多") }
                        }
                    }
                }
            }
        }
    }
    }
}
