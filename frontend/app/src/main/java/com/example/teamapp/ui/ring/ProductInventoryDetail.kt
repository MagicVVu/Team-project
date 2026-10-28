package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings

/** Server batches, including terminal records. Never creates per-piece preview records. */
@Composable
internal fun ProductInventoryDetail(product: CloudProduct, action: (StockItem, String) -> Unit) {
    val s = rememberUiStrings()
    val summary = product.ringItem(s.english)
    CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onSurface) {
    LazyColumn(Modifier.fillMaxSize().testTag("product-inventory-detail"),
        contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text(product.name, style = MaterialTheme.typography.headlineSmall)
            if (product.specification.isNotBlank()) Text(product.specification)
            Text(s.label(product.category), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("${summary.quantityText} ${product.baseUnit}", style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary)
            Text(if (s.english) "Total of all linked batches; expiry uses the earliest recorded date." else "数量为全部关联批次合计，有效期取已登记日期中最早的一天。",
                style = MaterialTheme.typography.bodySmall)
            Text(if (s.english) "${product.batches.size} linked batches" else "关联库存批次 ${product.batches.size} 条")
        }
        if (product.batches.isEmpty()) item {
            Text(if (s.english) "No inventory batches linked to this product." else "此商品还没有关联的库存批次。")
        }
        items(product.batches, key = { it.id }) { batch ->
            OutlinedCard(Modifier.fillMaxWidth().testTag("product-batch-${batch.id}")) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(batch.name, style = MaterialTheme.typography.titleMedium)
                    Text("${batch.quantityText} ${batch.unit}", color = MaterialTheme.colorScheme.primary)
                    Text((if (s.english) "Minimum stock: " else "最低库存：") + "${batch.minimum.display()} ${batch.unit}")
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
                    Text((if (s.english) "Batch ID: " else "批次编号：") + batch.id,
                        style = MaterialTheme.typography.bodySmall)
                    if (batch.activeBatch) {
                        TextButton(onClick = { action(batch, "编辑物品") }) { Text(if (s.english) "Edit this batch" else "编辑此批次") }
                        TextButton(onClick = { action(batch, "资料与盘点") }) { Text(if (s.english) "Batch facts and verification" else "此批次资料与盘点") }
                        TextButton(onClick = { action(batch, "批次操作") }) { Text(if (s.english) "Ask about this batch" else "询问此批次") }
                    }
                }
            }
        }
    }
    }
}
