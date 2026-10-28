package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test

class CloudProductTest {
    private fun batch(id: String, quantity: String, unit: String, status: String = "ACTIVE", expiry: String = "") =
        StockItem(id = id, name = "Same name", quantity = quantity.toDouble(), quantityExact = quantity,
            unit = unit, lifecycleStatus = status, expiry = expiry)
    private fun product(id: String, unit: String, vararg batches: StockItem) =
        CloudProduct(id, "Same name", "", unit, "食品", 1, batches.toList())

    @Test fun identitiesStaySeparateEvenWhenNamesMatch() {
        assertNotEquals(product("one", "盒").ringItem(false).id, product("two", "盒").ringItem(false).id)
    }
    @Test fun totalsConvertKnownUnitsExactlyAndRetainEndedBatches() {
        val p = product("milk", "L", batch("a", "0.1", "L", expiry = "2026-11-02"),
            batch("b", "250", "ml", expiry = "2026-11-01"), batch("c", "5", "L", "DISCARDED", expiry = "2026-10-01"))
        assertEquals("5.35", p.ringItem(false).quantityText)
        assertEquals("2026-10-01", p.ringItem(false).expiry)
        assertEquals(3, p.batches.size)
    }
    @Test fun incompatibleContainersNeverInventAZeroTotalOrCapacity() {
        val p = product("milk", "L", batch("a", "2", "盒"), batch("b", "1", "L"))
        assertEquals("数量待核对", p.ringItem(false).quantityText)
        assertEquals("Review units", p.ringItem(true).quantityText)
    }
    @Test fun emptyProductsRemainVisibleWithZeroStock() {
        assertEquals("0", product("empty", "盒").ringItem(false).quantityText)
    }
    @Test fun singleBatchRetainsItsOriginalFactsAndZeroNeedsNoCapacityGuess() {
        val b = batch("single", "2", "盒", expiry = "2026-12-01").copy(location = "储物柜", minimum = 3.0,
            purchasedAt = "2026-10-28", openedAt = "2026-10-28")
        val ring = product("single", "盒", b).ringItem(false)
        assertEquals(b.location, ring.location)
        assertEquals(b.minimum, ring.minimum, 0.0)
        assertEquals(b.purchasedAt, ring.purchasedAt)
        assertEquals(b.openedAt, ring.openedAt)
        assertEquals("1", product("mixed", "L", batch("a", "0", "盒", "FINISHED"), batch("b", "1", "L")).ringItem(false).quantityText)
    }
}
