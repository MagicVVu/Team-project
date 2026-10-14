package com.example.teamapp.ui.ring

import com.example.teamapp.data.StockItem
import com.example.teamapp.data.status
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.roundToInt

/** The item count only changes the finite scroll range, never this geometry. */
internal object RingMath {
    const val STEP = 30f
    const val SWEEP = 27f
    const val WINDOW = 2.7f

    fun index(position: Float, count: Int) = if (count == 0) -1 else position.roundToInt().coerceIn(0, count - 1)
    fun visible(position: Float, count: Int): IntRange {
        if (count == 0) return IntRange.EMPTY
        return maxOf(0, floor(position - WINDOW).toInt())..minOf(count - 1, ceil(position + WINDOW).toInt())
    }
    fun angle(index: Int, position: Float) = 180f + (index - position) * STEP
    fun deltaDegrees(from: Float, to: Float): Float = ((to - from + 540f) % 360f) - 180f
    fun drag(position: Float, delta: Float, count: Int): Float {
        if (count <= 1) return 0f
        val proposed = position - delta / STEP
        val end = (count - 1).toFloat()
        return when {
            proposed < 0 -> (proposed * .2f).coerceAtLeast(-.18f)
            proposed > end -> (end + (proposed - end) * .2f).coerceAtMost(end + .18f)
            else -> proposed
        }
    }
    fun selection(previous: List<String>, current: List<String>, selected: String?, filterChanged: Boolean): String? {
        if (current.isEmpty()) return null
        if (selected in current) return selected
        if (filterChanged) return current.first()
        return current[previous.indexOf(selected).coerceAtLeast(0).coerceAtMost(current.lastIndex)]
    }
}

internal enum class RingOrder(val title: String) { STATUS("状态优先"), CATEGORY("类别顺序"), NAME("名称顺序") }

internal fun ringResults(items: List<StockItem>, days: Int, search: String, category: String, attention: Boolean, order: RingOrder): List<StockItem> {
    val matching = items.filter { it.name.contains(search.trim(), true) && (category == "全部" || it.category == category) && (!attention || it.status(days).attention) }
    return when (order) {
        RingOrder.STATUS -> matching.sortedBy { it.status(days).priority }
        RingOrder.CATEGORY -> matching.sortedWith(compareBy<StockItem> { listOf("食品", "日用品", "其他").indexOf(it.category) }.thenBy { it.status(days).priority })
        RingOrder.NAME -> matching.sortedBy { it.name }
    }
}
