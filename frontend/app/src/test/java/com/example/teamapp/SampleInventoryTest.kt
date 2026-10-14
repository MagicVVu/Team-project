package com.example.teamapp

import com.example.teamapp.data.sampleInventory
import com.example.teamapp.data.status
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class SampleInventoryTest {
    @Test fun fifteenDistinctItemsCoverCategoriesAndStatuses() {
        val today = LocalDate.of(2026, 10, 14)
        val items = sampleInventory(today)
        assertEquals(15, items.size)
        assertEquals(15, items.map { it.id }.distinct().size)
        assertEquals(15, items.map { it.name }.distinct().size)
        assertEquals(mapOf("食品" to 5, "日用品" to 5, "其他" to 5), items.groupingBy { it.category }.eachCount())
        assertEquals(setOf("已过期", "临期提醒", "库存不足", "状态正常"), items.map { it.status(3, today).label }.toSet())
        assertTrue(items.all { it.quantity > 0 && it.unit.isNotBlank() && it.location.isNotBlank() })
    }
}
