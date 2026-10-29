package com.example.teamapp.data

import java.math.BigDecimal
import java.time.LocalDate

/** Legacy local demo model. Cloud drafts are server-owned AssistantEntry payloads. */
data class AgentCommand(
    val action: String,
    val name: String,
    val quantity: String,
    val unit: String,
    val batchId: String? = null,
    val expectedVersion: Int? = null,
    val location: String = "",
    val purchasedAt: String = "",
    val labelExpiry: String = ""
)

data class AgentMutation(val items: List<StockItem>, val purchases: List<Purchase>, val itemId: String)

private val aliases = mapOf("毫升" to "ml", "mL" to "ml", "升" to "L", "l" to "L", "克" to "g", "千克" to "kg", "公斤" to "kg")
private val supportedUnits = setOf("盒", "瓶", "包", "袋", "个", "卷", "片", "份", "件", "ml", "L", "g", "kg")
private fun canonicalUnit(unit: String): String = (aliases[unit] ?: unit).also { require(it in supportedUnits) { "单位不支持，请选择盒、瓶、包、袋、个、卷、片、ml、L、g、kg" } }
private fun converted(value: BigDecimal, from: String, to: String): BigDecimal {
    val source = canonicalUnit(from); val target = canonicalUnit(to)
    if (source == target) return value
    val scales = mapOf("ml" to ("volume" to BigDecimal.ONE), "L" to ("volume" to BigDecimal(1000)), "g" to ("mass" to BigDecimal.ONE), "kg" to ("mass" to BigDecimal(1000)))
    val a = scales[source]; val b = scales[target]
    require(a != null && b != null && a.first == b.first) { "单位不兼容，不能猜测容器容量" }
    return value * a.second / b.second
}

/** All checks also run on the device immediately before the confirmed write. */
@Deprecated("仅供本地演示；云端草稿必须通过 AssistantStore 和后端事务确认")
fun applyAgentCommand(items: List<StockItem>, purchases: List<Purchase>, command: AgentCommand): AgentMutation {
    val name = command.name.trim()
    require(name.isNotEmpty() && name.length <= 80) { "请填写有效的物品名称" }
    val quantity = command.quantity.toBigDecimalOrNull()
    require(quantity != null && quantity > BigDecimal.ZERO && quantity <= BigDecimal("1000000000") && quantity.stripTrailingZeros().scale() <= 6) { "数量须为正数，最多六位小数且不超过 10 亿" }
    val unit = canonicalUnit(command.unit)
    require(command.location.length <= 120) { "位置最多 120 字" }
    val purchased = command.purchasedAt.takeIf { it.isNotBlank() }?.let { LocalDate.parse(it) }
    val expiry = command.labelExpiry.takeIf { it.isNotBlank() }?.let { LocalDate.parse(it) }
    require(purchased == null || expiry == null || !expiry.isBefore(purchased)) { "有效期早于购入日期，请核对" }
    when (command.action) {
        "ADD" -> {
            require(command.batchId == null && command.expectedVersion == null) { "新增不能覆盖原有批次" }
            val item = StockItem(name = name, quantity = quantity.toDouble(), unit = unit, location = command.location.ifBlank { "待定位" }, expiry = command.labelExpiry, purchasedAt = command.purchasedAt)
            return AgentMutation(items + item.individualItems(), purchases, item.id)
        }
        "CONSUME" -> {
            val item = items.singleOrNull { it.id == command.batchId } ?: error("物品已不存在，请重新核对")
            require(item.name == name) { "名称与选中批次不一致" }
            val amount = converted(quantity, unit, item.unit)
            val remaining = BigDecimal.valueOf(item.quantity) - amount
            require(remaining >= BigDecimal.ZERO) { "消耗数量不能超过库存" }
            require(!item.individualRecord || amount == BigDecimal.ONE) { "每次只可消耗这件物品" }
            return AgentMutation(items.map { if (it.id == item.id) it.copy(quantity = remaining.toDouble(), lifecycleStatus = if (remaining.signum() == 0) "FINISHED" else "ACTIVE") else it }, purchases, item.id)
        }
        "PLAN_ADD" -> {
            require(command.batchId == null && command.expectedVersion == null)
            val item = items.singleOrNull { it.name == name } ?: error("请选择唯一的已登记物品加入采购清单")
            val amount = converted(quantity, unit, item.unit).toDouble()
            return AgentMutation(items, purchases.filterNot { it.itemId == item.id } + Purchase(item.id, amount), item.id)
        }
        else -> error("不支持这个库存动作")
    }
}
