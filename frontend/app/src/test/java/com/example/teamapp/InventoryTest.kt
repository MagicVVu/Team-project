package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class InventoryTest {
    private val today = LocalDate.of(2026, 10, 13)
    private fun milk(expiry: String = "") = StockItem(name = "纯牛奶", quantity = 1.0, unit = "盒", minimum = 3.0, expiry = expiry)
    @Test fun overlappingStatusesAreIndependent() {
        val s = milk("2026-10-15").status(3, today)
        assertTrue(s.low); assertTrue(s.soon); assertFalse(s.expired); assertEquals(2L, s.days)
    }
    @Test fun expiryDateInclusiveAndExpiredPrioritized() {
        assertTrue(milk("2026-10-13").status(3, today).soon)
        val s = milk("2026-10-12").status(3, today)
        assertTrue(s.low); assertTrue(s.expired); assertFalse(s.soon); assertEquals("已过期", s.label)
    }
    @Test fun unsetExpiryIsNeverConsideredExpired() {
        val s = milk().status(3, today)
        assertNull(s.days); assertFalse(s.expired); assertFalse(s.soon)
    }
    @Test fun thresholdEqualityIsNotLow() { assertFalse(milk().copy(quantity = 3.0).status(3, today).low) }
    @Test fun numericInputsRejectNonFiniteOrNonPositiveValues() {
        listOf("", "-1", "0", "NaN", "Infinity", "1e999").forEach { assertNull(positiveNumber(it)) }
        assertEquals(0.0, nonNegativeNumber("0")!!, 0.0)
        assertEquals(1.5, positiveNumber("1.5")!!, 0.0)
    }
    @Test fun voiceParsesAllItemsAndLeavesMissingInformationEmpty() {
        val drafts = parseVoice("添加两盒纯牛奶，厨房里放了三袋面包")
        assertEquals(2, drafts.size); assertEquals("纯牛奶", drafts[0].name); assertEquals("2", drafts[0].quantity)
        assertEquals("面包", drafts[1].name); assertEquals("厨房", drafts[1].location)
        val missing = parseVoice("添加牛奶").single()
        assertEquals("牛奶", missing.name); assertEquals("", missing.quantity); assertEquals("", missing.unit)
    }
    @Test fun assistantUsesCurrentFactsAndDoesNotGuess() {
        val item = milk()
        assertTrue(answerInventory("需要补什么", listOf(item), 3).contains("补充 2 盒"))
        assertTrue(answerInventory("需要补什么", listOf(item.copy(quantity = 5.0)), 3).contains("没有符合"))
        assertTrue(answerInventory("明天天气", listOf(item), 3).contains("无法确定"))
    }
}
