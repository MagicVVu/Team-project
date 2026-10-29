package com.example.teamapp.data

import org.json.JSONObject
import java.math.BigDecimal

/** Membership comes from the server. A ring projection is never a writable object. */
data class CloudProduct(val id: String, val name: String, val specification: String,
    val baseUnit: String, val category: String, val version: Int, val batches: List<StockItem>) {
    val activeItems get() = batches.filter { it.activeBatch }
    val count get() = activeItems.size
    fun ringItem(english: Boolean): StockItem {
        val current = activeItems
        val single = current.singleOrNull()
        return StockItem(id = "product:$id", name = name, category = category,
            quantity = count.toDouble(), quantityExact = count.toString(),
            unit = "个", location = single?.location ?: if (english) "$count individual items" else "$count 件在库物品",
            minimum = current.maxOfOrNull { it.minimum } ?: 0.0,
            expiry = current.map { it.expiry }.filter { it.isNotBlank() }.minOrNull().orEmpty(),
            image = single?.image.orEmpty(), history = single?.history.orEmpty(),
            purchasedAt = single?.purchasedAt.orEmpty(), openedAt = single?.openedAt.orEmpty(),
            lifecycleStatus = if (current.isEmpty()) "FINISHED" else "ACTIVE",
            version = version, specification = specification)
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
