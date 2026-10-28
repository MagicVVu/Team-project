package com.example.teamapp.data

import org.json.JSONObject
import java.math.BigDecimal

/** Only product_batches defines membership. A ring projection is never a writable batch. */
data class CloudProduct(val id: String, val name: String, val specification: String,
    val baseUnit: String, val category: String, val version: Int, val batches: List<StockItem>) {
    fun ringItem(english: Boolean): StockItem {
        val single = batches.singleOrNull()
        val amounts = batches.map { convertProductQuantity(BigDecimal(it.quantityExact.ifBlank { it.quantity.toString() }), it.unit, baseUnit) }
        val total = if (amounts.any { it == null }) null else amounts.filterNotNull().fold(BigDecimal.ZERO, BigDecimal::add)
        return StockItem(id = "product:$id", name = name, category = category,
            quantity = total?.toDouble() ?: 0.0, quantityExact = total?.stripTrailingZeros()?.toPlainString().orEmpty(),
            unit = baseUnit, location = single?.location ?: if (english) "${batches.size} batches" else "${batches.size} 个库存批次",
            minimum = single?.let { convertProductQuantity(BigDecimal.valueOf(it.minimum), it.unit, baseUnit)?.toDouble() } ?: 0.0,
            expiry = batches.map { it.expiry }.filter { it.isNotBlank() }.minOrNull().orEmpty(),
            image = single?.image.orEmpty(), history = single?.history.orEmpty(),
            purchasedAt = single?.purchasedAt.orEmpty(), openedAt = single?.openedAt.orEmpty(),
            lifecycleStatus = single?.lifecycleStatus ?: if (batches.isNotEmpty() && batches.none { it.activeBatch }) "FINISHED" else "ACTIVE",
            version = version, displayQuantity = if (total == null) { if (english) "Review units" else "数量待核对" } else null)
    }
}

internal fun JSONObject.toCloudProduct() = CloudProduct(getString("product_id"), getString("name"),
    stringOrEmpty("specification"), getString("base_unit"), InventoryContract.categoryLabel(getString("category")),
    getInt("version"), getJSONArray("inventory_items").objects().map { it.toStock() })

internal fun convertProductQuantity(quantity: BigDecimal, from: String, to: String): BigDecimal? {
    if (quantity.signum() == 0) return BigDecimal.ZERO
    val source = InventoryContract.unit(from) ?: from
    val target = InventoryContract.unit(to) ?: to
    if (source == target) return quantity
    val factors = mapOf("ml" to ("volume" to BigDecimal.ONE), "L" to ("volume" to BigDecimal(1000)),
        "g" to ("mass" to BigDecimal.ONE), "kg" to ("mass" to BigDecimal(1000)))
    val a = factors[source] ?: return null
    val b = factors[target] ?: return null
    return if (a.first == b.first) quantity.multiply(a.second).divide(b.second) else null
}
