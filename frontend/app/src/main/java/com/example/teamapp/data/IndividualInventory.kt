package com.example.teamapp.data

import java.math.BigDecimal

/** Convert an intake request or legacy local batch to durable individual records. */
internal fun StockItem.individualItems(): List<StockItem> {
    if (individualRecord) return listOf(this)
    val amount = quantityExact.toBigDecimalOrNull() ?: BigDecimal.valueOf(quantity)
    require(amount >= BigDecimal.ZERO)
    val measured = (InventoryContract.unit(unit) ?: unit) in InventoryContract.measuredUnits || amount.stripTrailingZeros().scale() > 0
    val count = if (measured || amount.signum() == 0) 1 else amount.intValueExact()
    require(count <= 10000) { "单次最多10000件物品，请分次添加" }
    val facts = if (measured) listOf(specification, "${amount.stripTrailingZeros().toPlainString()}$unit").filter { it.isNotBlank() }.distinct().joinToString(" · ") else specification
    return List(count) { index -> copy(
        id = if (index == 0) id else "$id:unit:$index", quantity = if (amount.signum() == 0 || !activeBatch) 0.0 else 1.0,
        quantityExact = "", unit = if (measured) "份" else unit, specification = facts,
        lifecycleStatus = if (amount.signum() == 0 && activeBatch) "FINISHED" else lifecycleStatus,
        individualRecord = true
    ) }
}

internal fun namesShareProduct(first: String, second: String): Boolean {
    val a = first.trim().lowercase(); val b = second.trim().lowercase()
    return a == b || a.windowed(2).any { it in b }
}

/** Local guest mode follows the same display model; cloud membership remains server-owned. */
internal fun localInventoryProducts(items: List<StockItem>): List<CloudProduct> {
    val groups = mutableListOf<MutableList<StockItem>>()
    items.forEach { item ->
        val group = groups.firstOrNull { namesShareProduct(it.first().name, item.name) }
        if (group == null) groups += mutableListOf(item) else group += item
    }
    return groups.map { group ->
        val first = group.first()
        CloudProduct("local:${first.id}", first.name, "", first.unit, first.category, 1, group)
    }
}
