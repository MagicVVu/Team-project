package com.example.teamapp.data

import java.time.LocalDate

/** Literal supplements only; the caller supplies candidates from one saved revision. */
object ClarificationReplies {
    private val numbers = mapOf("一" to 1, "二" to 2, "两" to 2, "三" to 3, "四" to 4, "五" to 5, "六" to 6, "七" to 7, "八" to 8, "九" to 9, "十" to 10)
    fun resolve(text: String, allowed: Set<String>, candidates: List<String>, selected: String? = null): Map<String, String>? {
        val input = text.trim().trimEnd('。', '！', '!')
        val ordinal = Regex("(?:选|选择|我要)?第([一二两三四五六七八九十0-9]+)(?:个|批|项)(?:吧)?").matchEntire(input)
        if (ordinal != null) {
            val number = ordinal.groupValues[1].toIntOrNull() ?: numbers[ordinal.groupValues[1]]
            if ("batch_id" !in allowed || number == null || candidates.distinct().size != candidates.size) return null
            return candidates.getOrNull(number - 1)?.takeIf { it.isNotBlank() }?.let { mapOf("batch_id" to it) }
        }
        if (input in setOf("这一批", "这批", "这个", "它")) return selected?.takeIf { "batch_id" in allowed && it in candidates }?.let { mapOf("batch_id" to it) }
        if (input in setOf("今天", "昨天") || Regex("\\d{4}-\\d{2}-\\d{2}").matches(input)) {
            val dates = allowed.intersect(setOf("purchased_at", "label_expiry", "opened_at"))
            if (dates.size != 1 || (input !in setOf("今天", "昨天") && runCatching { LocalDate.parse(input) }.isFailure)) return null
            return mapOf(dates.single() to input)
        }
        val amount = Regex("([0-9]+(?:\\.[0-9]+)?|[一二两三四五六七八九十])\\s*(盒|瓶|包|袋|个|件|卷|罐|支|枚|片|杯|份|台|吨|千克|公斤|毫升|克|升|kg|g|ml|mL|L)").matchEntire(input)
        if (amount != null && setOf("quantity", "unit").all { it in allowed }) {
            val value = amount.groupValues[1].toBigDecimalOrNull() ?: numbers[amount.groupValues[1]]?.toBigDecimal() ?: return null
            if (value.signum() <= 0) return null
            return mapOf("quantity" to value.toPlainString(), "unit" to amount.groupValues[2])
        }
        if ("quantity" in allowed && Regex("[0-9]+(?:\\.[0-9]+)?").matches(input) && input.toBigDecimal().signum() > 0) return mapOf("quantity" to input)
        return null
    }
}
