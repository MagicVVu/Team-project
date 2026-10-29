package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test

class IndividualInventoryTest {
    @Test fun expansionRetainsTheOriginalIdentityAndUniqueObjectIds() {
        val rows = StockItem(id = "intake", name = "苹果", quantity = 10.0, unit = "个", expiry = "2026-11-01").individualItems()
        assertEquals(10, rows.size)
        assertEquals("intake", rows.first().id)
        assertEquals(10, rows.map { it.id }.toSet().size)
        assertTrue(rows.all { it.quantity == 1.0 && it.expiry == "2026-11-01" && it.individualRecord })
        assertEquals(rows, rows.flatMap { it.individualItems() })
    }
    @Test fun weightsBecomeOnePortionWithSpecification() {
        val row = StockItem(name = "大米", quantity = 2.5, unit = "kg").individualItems().single()
        assertEquals("份", row.unit)
        assertEquals("2.5kg", row.specification)
        assertEquals(1.0, row.quantity, 0.0)
    }
    @Test fun finishedLegacyRecordsStayTerminal() {
        val row = StockItem(name = "苹果", quantity = 0.0, unit = "个").individualItems().single()
        assertFalse(row.activeBatch)
        assertEquals(0.0, row.quantity, 0.0)
    }
    @Test fun receiptValidationRejectsFractionalPiecesAndUnboundedExpansion() {
        assertTrue(InventoryContract.validReceipt("10000", "个"))
        assertFalse(InventoryContract.validReceipt("10001", "个"))
        assertFalse(InventoryContract.validReceipt("1.5", "个"))
        assertTrue(InventoryContract.validReceipt("1.5", "kg"))
        assertFalse(InventoryContract.validReceipt("0", "份"))
    }
    @Test fun productNamesRequireExactOrTwoConsecutiveSharedCharacters() {
        assertTrue(namesShareProduct("苹果", "红苹果"))
        assertTrue(namesShareProduct("A", "a"))
        assertFalse(namesShareProduct("苹果", "芒果"))
        assertFalse(namesShareProduct("苹果", "苹红果"))
    }
    @Test fun requestedVoiceExamplesRetainTheirObjectNamesAndCounts() {
        val apple = parseVoice("我买了10个苹果放在冰箱里").single()
        val redApple = parseVoice("我买了12个红苹果放在冰箱里").single()
        assertEquals("苹果", apple.name)
        assertEquals("10", apple.quantity)
        assertEquals("红苹果", redApple.name)
        assertEquals("12", redApple.quantity)
        assertEquals("冰箱", redApple.location)
    }
}
