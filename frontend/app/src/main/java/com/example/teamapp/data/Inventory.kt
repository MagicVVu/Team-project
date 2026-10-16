package com.example.teamapp.data

import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.UUID

data class StockItem(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val quantity: Double,
    val unit: String,
    val category: String = "食品",
    val location: String = "厨房",
    val minimum: Double = 0.0,
    val expiry: String = "",
    val image: String = "",
    val history: List<String> = emptyList(),
    val purchasedAt: String = "",
    val version: Int = 1
)

data class Purchase(val itemId: String, val quantity: Double)
data class StockStatus(val low: Boolean, val days: Long?, val soon: Boolean, val expired: Boolean) {
    val attention get() = low || soon || expired
    val label get() = when { expired -> "已过期"; soon -> "临期提醒"; low -> "库存不足"; else -> "状态正常" }
    val priority get() = when { expired -> 0; soon -> 1; low -> 2; else -> 3 }
}

fun StockItem.status(reminderDays: Int, today: LocalDate = LocalDate.now()): StockStatus {
    val days = runCatching { ChronoUnit.DAYS.between(today, LocalDate.parse(expiry)) }.getOrNull()
    return StockStatus(quantity < minimum, days, days != null && days in 0..reminderDays.toLong(), days != null && days < 0)
}

fun Double.display(): String = if (this % 1.0 == 0.0) toLong().toString() else toString()
fun positiveNumber(value: String): Double? = value.toDoubleOrNull()?.takeIf { it.isFinite() && it > 0 }
fun nonNegativeNumber(value: String): Double? = value.toDoubleOrNull()?.takeIf { it.isFinite() && it >= 0 }

data class VoiceDraft(val name: String, val quantity: String, val unit: String, val location: String)

/** Conservative parser: missing quantities or units remain empty for user confirmation. */
fun parseVoice(text: String): List<VoiceDraft> {
    val digits = mapOf("一" to "1", "二" to "2", "两" to "2", "三" to "3", "四" to "4", "五" to "5", "六" to "6", "七" to "7", "八" to "8", "九" to "9", "十" to "10")
    return text.split(Regex("[，,、；;。]|以及|还有|和")).filter { it.isNotBlank() }.map { sentence ->
        val number = Regex("([0-9]+(?:\\.[0-9]+)?|[一二两三四五六七八九十])\\s*([个盒袋瓶包杯斤升枚卷罐])").find(sentence)
        val location = listOf("冰箱", "厨房", "储物柜", "阳台").firstOrNull { sentence.contains(it) }.orEmpty()
        var name = sentence.replace(Regex("添加|放了|买了|买|有|放在|放到|里|请|帮我"), "")
        if (location.isNotEmpty()) name = name.replace(location, "")
        if (number != null) name = name.replace(number.value, "")
        VoiceDraft(name.trim(), number?.groupValues?.get(1)?.let { digits[it] ?: it }.orEmpty(), number?.groupValues?.get(2).orEmpty(), location)
    }
}

/** Local facts only. This service can later be replaced by the team's Agent API. */
fun answerInventory(question: String, items: List<StockItem>, reminderDays: Int): String {
    if (items.isEmpty()) return "还没有记录物品。先添加并确认库存，我才能根据真实记录回答。"
    val matched = items.filter { question.contains(it.name) }
    val selected = when {
        matched.isNotEmpty() -> matched
        question.contains("过期") || question.contains("临期") -> items.filter { it.status(reminderDays).let { s -> s.soon || s.expired } }
        question.contains("补") || question.contains("采购") || question.contains("不够") -> items.filter { it.status(reminderDays).low }
        question.contains("库存") || question.contains("家里") || question.contains("有什么") -> items
        else -> return "本地库存助手暂时无法确定这个问题。你可以询问物品名称、哪些快过期了，或需要补什么。我不会根据猜测修改库存。"
    }
    if (selected.isEmpty()) return "根据当前登记的库存，没有符合这次查询的物品。"
    return selected.joinToString("\n\n") { item ->
        val s = item.status(reminderDays)
        buildString {
            append("${item.name}：${item.quantity.display()} ${item.unit}，存放在${item.location}。")
            if (s.low) append("低于最低库存 ${item.minimum.display()} ${item.unit}，建议补充 ${(item.minimum - item.quantity).display()} ${item.unit}。")
            when { s.expired -> append("登记有效期 ${item.expiry}，已过期，请核对并处理。"); s.soon -> append("登记有效期 ${item.expiry}，剩余 ${s.days} 天。"); item.expiry.isBlank() -> append("未设置有效期。"); else -> append("有效期 ${item.expiry}。") }
        }
    } + "\n\n以上依据当前已确认记录；补货需你确认加入清单。"
}
