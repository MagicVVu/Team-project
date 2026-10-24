package com.example.teamapp.data

import java.math.BigDecimal

/** Shared wire vocabulary. Unknown containers are never converted into a guessed capacity. */
object InventoryContract {
    val units = listOf("盒", "瓶", "包", "袋", "个", "卷", "片", "吨", "台", "ml", "L", "g", "kg")
    private val aliases = mapOf("毫升" to "ml", "mL" to "ml", "升" to "L", "l" to "L", "克" to "g", "千克" to "kg", "公斤" to "kg")
    fun unit(value: String): String? = value.trim().let { aliases[it] ?: it.takeIf(units::contains) }
    fun category(value: String): String = when(value) {
        "食品", "food" -> "food"
        "日用品", "household" -> "household"
        "药品", "medicine" -> "medicine"
        else -> "unknown"
    }
    fun categoryLabel(value: String): String = when(value) {
        "food" -> "食品"; "household" -> "日用品"; "medicine" -> "药品"; "unknown" -> "其他"; else -> value
    }
    fun amount(value: String, scale: Int = 6, positive: Boolean = false): BigDecimal? =
        value.trim().takeIf { it.matches(Regex("[0-9]+(?:\\.[0-9]+)?")) }?.toBigDecimalOrNull()?.takeIf {
            it >= BigDecimal.ZERO && (!positive || it > BigDecimal.ZERO) &&
                it <= BigDecimal("1000000000") && it.stripTrailingZeros().scale() <= scale
        }
    fun compatible(item: StockItem) = item.name.length <= 80 && unit(item.unit) != null
}
