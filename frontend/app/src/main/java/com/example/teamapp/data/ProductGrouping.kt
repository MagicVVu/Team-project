package com.example.teamapp.data

import org.json.JSONObject
import java.util.UUID

/** Server-issued candidates carry the versions reviewed by the user. */
data class ProductGroupingMatch(val inventoryItemId: String, val name: String, val inventoryVersion: Int,
    val productId: String?, val productVersion: Int?, val productName: String = "") {
    fun decision() = JSONObject().put("mode", "existing")
        .put("candidate_inventory_item_id", inventoryItemId).put("expected_inventory_version", inventoryVersion)
        .apply { if (productId != null) put("expected_product_version", requireNotNull(productVersion)) }
}

data class ProductGroupingReview(val scope: String, val item: StockItem, val candidates: List<ProductGroupingMatch>)

/** An unknown result is recovered with the original body, never a newly edited form. */
data class ProductGroupingWrite(val scope: String, val body: String, val image: String) {
    val itemId get() = JSONObject(body).getString("id")
    val name get() = JSONObject(body).getString("name")
}

internal fun JSONObject.toProductGroupingMatch(): ProductGroupingMatch {
    val inventoryId = UUID.fromString(getString("inventory_item_id")).toString()
    val productId = stringOrEmpty("product_id").takeIf { it.isNotBlank() }?.let { UUID.fromString(it).toString() }
    val inventoryVersion = getInt("inventory_version").also { require(it >= 1) }
    val productVersion = if (productId != null) getInt("product_version").also { require(it >= 1) } else null
    return ProductGroupingMatch(inventoryId, getString("name"), inventoryVersion, productId, productVersion, stringOrEmpty("product_name"))
}

internal fun groupedInventoryBody(item: StockItem, match: ProductGroupingMatch?) = item.toCloudJson()
    .put("quantity", item.quantityExact.ifBlank { java.math.BigDecimal.valueOf(item.quantity).toPlainString() })
    .apply { if (match != null) put("product_grouping", match.decision()) }
