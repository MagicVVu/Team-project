package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test

class CloudProductTest {
    private fun item(id: String, name: String = "苹果", status: String = "ACTIVE", expiry: String = "") =
        StockItem(id = id, name = name, quantity = if (status == "ACTIVE") 1.0 else 0.0,
            unit = "个", lifecycleStatus = status, expiry = expiry, individualRecord = true)
    private fun product(vararg items: StockItem) = CloudProduct("apple", "苹果", "", "个", "食品", 1, items.toList())

    @Test fun appleIntakesHaveTwentyTwoDurableRowsAndOneRingEntry() {
        val first = List(10) { item("apple-$it") }
        val second = List(12) { item("red-apple-$it", "红苹果") }
        val p = product(*(first + second).toTypedArray())
        assertEquals(22, p.count)
        assertEquals("*22", p.ringItem(false).stockCountText)
        assertEquals(10, p.activeItems.count { it.name == "苹果" })
        assertEquals(12, p.activeItems.count { it.name == "红苹果" })
        assertEquals(22, p.activeItems.map { it.id }.toSet().size)
    }
    @Test fun oneConsumedObjectReducesCountByOneAndRetainsItsHistory() {
        val p = product(item("a"), item("b"), item("used", status = "FINISHED"), item("discarded", status = "DISCARDED"))
        assertEquals(2, p.count)
        assertEquals(4, p.batches.size)
        assertEquals("2", p.ringItem(false).quantityText)
    }
    @Test fun terminalExpiryDoesNotChangeCurrentProductExpiry() {
        val p = product(item("current", expiry = "2026-11-02"), item("ended", status = "FINISHED", expiry = "2026-10-01"))
        assertEquals("2026-11-02", p.ringItem(false).expiry)
    }
    @Test fun differentPackageSizesAreStillIndividualObjects() {
        val a = item("small").copy(unit = "瓶", specification = "250ml")
        val b = item("large").copy(unit = "盒", specification = "1L")
        assertEquals("*2", product(a, b).ringItem(true).stockCountText)
        assertEquals("250ml", product(a, b).batches.first().specification)
    }
    @Test fun emptyProductHasZeroCount() {
        assertEquals("*0", product().ringItem(false).stockCountText)
        assertFalse(product().ringItem(false).activeBatch)
    }
    @Test fun localGuestIntakesGroupAndPreserveOriginalNames() {
        val first = StockItem(id = "first", name = "苹果", quantity = 10.0, unit = "个").individualItems()
        val second = StockItem(id = "second", name = "红苹果", quantity = 12.0, unit = "个").individualItems()
        val p = localInventoryProducts(first + second).single()
        assertEquals("苹果", p.name)
        assertEquals(22, p.count)
        assertEquals(12, p.batches.count { it.name == "红苹果" })
    }
}
