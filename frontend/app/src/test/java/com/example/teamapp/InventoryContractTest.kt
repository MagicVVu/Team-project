package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test

class InventoryContractTest {
    @Test fun aliasesNormalizeWithoutGuessingContainers() {
        for ((alias, unit) in mapOf("mL" to "ml", "毫升" to "ml", "l" to "L", "升" to "L", "公斤" to "kg")) assertEquals(unit, InventoryContract.unit(alias))
        assertEquals("件", InventoryContract.unit("件")); assertEquals("份", InventoryContract.unit("份"))
        for (value in listOf("杯", "斤", "罐", "一瓶500毫升")) assertNull(InventoryContract.unit(value))
    }
    @Test fun precisionAndLimitsMatchTheTwoPublicContracts() {
        assertNotNull(InventoryContract.amount("999999999.999999"))
        assertNull(InventoryContract.amount("1.0000001")); assertNull(InventoryContract.amount("1000000000.000001"))
        assertNotNull(InventoryContract.amount("1.001", 3, true)); assertNull(InventoryContract.amount("1.0001", 3, true))
        assertNotNull(InventoryContract.amount("0")); assertNull(InventoryContract.amount("0", positive = true))
        for (value in listOf("NaN", "Infinity", "1e2", "-1")) assertNull(InventoryContract.amount(value))
    }
    @Test fun medicineAndLegacyCategoriesRemainDistinct() {
        assertEquals("medicine", InventoryContract.category("药品"))
        assertEquals("药品", InventoryContract.categoryLabel("medicine"))
        assertEquals("unknown", InventoryContract.category("未识别旧分类"))
        assertEquals("household", InventoryContract.category("日用品"))
    }
    @Test fun terminalBatchNeverAdvertisesActiveOperationsOrLowStock() {
        for (status in listOf("FINISHED", "DISCARDED", "REVERSED")) {
            val item = StockItem(name = "旧批次", quantity = 0.0, unit = "盒", minimum = 10.0, lifecycleStatus = status)
            assertFalse(item.activeBatch); assertFalse(item.status(3).attention); assertEquals("批次已结束", item.status(3).label)
        }
    }
    @Test fun exactServerQuantitySurvivesWithoutBorrowingAStaleCopyValue() {
        val item = StockItem(name = "牛奶", quantity = 1.000001, unit = "L", quantityExact = "1.000001")
        assertEquals("1.000001", item.quantityText)
        assertEquals("2", item.copy(quantity = 2.0).quantityText)
        assertFalse(InventoryContract.compatible(item.copy(name = "很".repeat(81))))
    }
}
