package com.example.teamapp.data

import java.math.BigDecimal
import java.time.LocalDate

/** Client validation assists the form; the backend remains authoritative. */
object AgentExecutionPolicy {
    val editable = mapOf(
        "ADD" to listOf("name", "quantity", "unit", "location", "purchased_at", "label_expiry"),
        "MOVE" to listOf("to_location"), "CONSUME" to listOf("quantity", "unit"),
        "PLAN_ADD" to listOf("quantity", "unit")
    )
    fun validate(action: String, values: Map<String, String>, allowed: List<String>) {
        require(action in editable) { "当前版本暂不支持自动执行此动作" }
        require(values.keys.all { it in editable.getValue(action) && it in allowed }) { "字段不允许编辑" }
        values["quantity"]?.let {
            val n = it.toBigDecimalOrNull()
            val precision = if (action == "PLAN_ADD") 3 else 6
            require(n != null && n > BigDecimal.ZERO && n <= BigDecimal("1000000000") && n.stripTrailingZeros().scale() <= precision) { "数量必须为正数，库存最多六位、采购最多三位小数" }
        }
        for (field in listOf("location", "to_location")) values[field]?.let {
            require(it.isNotBlank() && it.codePointCount(0, it.length) <= 100) { "位置必填且最多 100 字，不会自动截断" }
        }
        values["name"]?.let { require(it.isNotBlank() && it.codePointCount(0, it.length) <= 200) { "物品名称必填且最多 200 字" } }
        values["unit"]?.let { require(it.isNotBlank()) { "单位必填" } }
<<<<<<< HEAD
<<<<<<< HEAD
        if (action == "OPEN") require(!LocalDate.parse(values.getValue("opened_at")).isAfter(LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")))) { "开封日期不能在未来" }
<<<<<<< Updated upstream
        if (action == "DISCARD") require(values["discard_mode"] in setOf("partial", "all")) { "请选择丢弃模式" }
=======
        if (action == "DISCARD") require(values["discard_mode"] in setOf("partial", "all")) { "丢弃模式必须是 partial 或 all" }
>>>>>>> Stashed changes
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
        val dates = listOf("purchased_at", "label_expiry").map { key -> values[key]?.takeIf { it.isNotBlank() }?.let { LocalDate.parse(it) } }
        require(dates[0] == null || dates[1] == null || !dates[1]!!.isBefore(dates[0])) { "有效期不能早于购入日期" }
    }
}
