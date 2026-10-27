package com.example.teamapp

import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class InventoryPreviewTest {
    private val item = StockItem(id = "melon", name = "西瓜", quantity = 2.0, unit = "个",
        location = "冰箱", expiry = "2026-10-26", openedAt = "2026-10-20")
    private val previews = InventoryPreviewStore()
    private fun snapshot() = previews.preview("local", item)

    @Test fun initializesRealPiecesOnlyAndKeepsStableIdentity() {
        val first = snapshot()
        assertTrue(first.individual)
        assertEquals(2, first.records.size)
        assertEquals(2, first.records.map { it.id }.distinct().size)
        first.records.forEach {
            assertEquals(item.id, it.itemId)
            assertEquals("冰箱", it.location)
            assertEquals("2026-10-26", it.expiryDate)
            assertEquals("2026-10-20", it.openedAt)
        }
        repeat(5) { assertSame(first, snapshot()) }
        assertTrue(previews.preview("local", item.copy(id = "empty", quantity = 0.0)).records.isEmpty())
    }

    @Test fun receiptAddsThreePiecesToSameItemAndIsIdempotent() {
        val originalIds = snapshot().records.map { it.id }
        val date = LocalDate.parse("2026-11-15")
        assertTrue(previews.receive("local", item, "3", date, "receipt-a"))
        assertFalse(previews.receive("local", item, "3", date, "receipt-a"))
        val result = snapshot()
        assertEquals("5", result.total.previewText())
        assertEquals(originalIds, result.records.take(2).map { it.id })
        assertEquals(5, result.records.map { it.id }.distinct().size)
        result.records.drop(2).forEach {
            assertEquals(item.id, it.itemId)
            assertEquals("冰箱", it.location)
            assertEquals("2026-11-15", it.expiryDate)
            assertNull(it.openedAt)
        }
        assertEquals(2.0, item.quantity, 0.0)
        assertEquals("2026-10-26", item.expiry)
    }

    @Test fun separateReceiptsRetainDatesAndMissingDatesStayMissing() {
        val empty = item.copy(quantity = 0.0)
        previews.receive("local", empty, "2", LocalDate.parse("2026-11-10"), "a")
        previews.receive("local", empty, "3", LocalDate.parse("2026-11-20"), "b")
        val records = previews.preview("local", empty).records
        assertEquals(List(2) { "2026-11-10" } + List(3) { "2026-11-20" }, records.map { it.expiryDate })
        previews.receive("local", empty, "1", null, "c")
        assertNull(previews.preview("local", empty).records.last().expiryDate)
        assertNull(previews.preview("local", empty).records.last().openedAt)
    }

    @Test fun invalidPieceInputsNeverMutatePreview() {
        val before = snapshot()
        for (input in listOf("", " ", "0", "-1", "abc", "NaN", "Infinity", "1e2", "2.5", "2.0", "10001")) {
            assertNull("Invalid input $input", previews.amount(item, input, before))
            assertFalse(previews.receive("local", item, input, null, input))
        }
        assertSame(before, snapshot())
    }

    @Test fun quantitiesAreIsolatedByItemAndAccountHousehold() {
        previews.receive("user-a|home-a", item, "3", null, "a")
        assertEquals("5", previews.preview("user-a|home-a", item).total.previewText())
        for (scope in listOf("local", "user-b|home-a", "user-a|home-b")) {
            assertEquals("2", previews.preview(scope, item).total.previewText())
        }
        assertEquals("2", previews.preview("user-a|home-a", item.copy(id = "other")).total.previewText())
        assertEquals("5", previews.preview("user-a|home-a", item).total.previewText())
    }

    @Test fun continuousAndUnknownUnitsKeepExactAggregateQuantities() {
        for (unit in listOf("kg", "g", "L", "ml", "吨", "公斤", "斤", "custom")) {
            val measured = item.copy(id = unit, quantity = 2.5, quantityExact = "2.500000", unit = unit)
            val before = previews.preview("local", measured)
            assertFalse(before.individual)
            assertEquals("2.5", before.total.previewText())
            assertEquals(1, before.records.size)
            assertTrue(previews.receive("local", measured, "0.000001", null, "a"))
            assertEquals("2.500001", previews.preview("local", measured).total.previewText())
            assertEquals("0.000001", previews.preview("local", measured).records.last().quantity.previewText())
            assertFalse(previews.receive("local", measured, "0.0000001", null, "b"))
        }
    }

    @Test fun fractionalLegacyPiecesAndHugeQuantitiesNeverRoundOrAllocateHugeLists() {
        for (quantity in listOf(2.5, 10001.0, 1000000000.0)) {
            val legacy = item.copy(id = quantity.toString(), quantity = quantity)
            val result = previews.preview("local", legacy)
            assertFalse(result.individual)
            assertEquals(quantity.display(), result.total.previewText())
            assertEquals(1, result.records.size)
        }
    }

    @Test fun savedChangesRefreshOnlyBeforeReceiptsAndNeverInventConsumptionAllocation() {
        assertEquals("2", snapshot().total.previewText())
        val edited = item.copy(quantity = 7.0)
        assertEquals("7", previews.preview("local", edited).total.previewText())
        previews.receive("local", edited, "3", null, "a")
        val consumed = edited.copy(quantity = 6.0)
        val frozen = previews.preview("local", consumed)
        assertEquals("10", frozen.total.previewText())
        assertTrue(frozen.originalChanged(consumed))
        assertFalse(frozen.originalChanged(edited))
        assertFalse(previews.receive("local", consumed.copy(unit = "kg"), "2", null, "b"))
    }

    @Test fun terminalBatchesCannotReceive() {
        assertFalse(previews.receive("local", item.copy(lifecycleStatus = "FINISHED"), "2", null, "a"))
    }

    @Test fun editingOneRecordPreservesOtherPiecesAndAllIdentityFields() {
        previews.receive("local", item, "1", LocalDate.parse("2026-11-20"), "third")
        val before = snapshot().records
        val second = before[1]
        assertTrue(previews.updateRecord("local", item.id, second.id, "阳台", "2026-12-01", null))
        val after = snapshot().records
        assertEquals(before[0], after[0]); assertEquals(before[2], after[2])
        assertEquals(second.copy(location = "阳台", expiryDate = "2026-12-01", openedAt = null), after[1])
        assertEquals("3", snapshot().total.previewText())
        assertEquals(item, snapshot().baseline)
    }

    @Test fun openingUsesExplicitLocalDateOnceWithoutChangingSiblingsOrParent() {
        val fresh = item.copy(openedAt = "")
        val before = previews.preview("local", fresh).records
        assertTrue(previews.markOpened("local", fresh.id, before[0].id, LocalDate.parse("2026-10-27")))
        assertFalse(previews.markOpened("local", fresh.id, before[0].id, LocalDate.parse("2026-10-28")))
        val after = previews.preview("local", fresh).records
        assertEquals("2026-10-27", after[0].openedAt)
        assertEquals(before[1], after[1])
        assertEquals("", fresh.openedAt)
        assertEquals("ACTIVE", fresh.lifecycleStatus)
    }

    @Test fun consumingOriginalPiecesDoesNotReinitializeThemOrModifyParent() {
        val before = snapshot().records
        assertTrue(previews.consumeRecord("local", item.id, before[0].id))
        assertFalse(previews.consumeRecord("local", item.id, before[0].id))
        assertEquals(listOf(before[1]), snapshot().records)
        assertTrue(previews.consumeRecord("local", item.id, before[1].id))
        assertEquals("0", snapshot().total.previewText())
        assertTrue(snapshot().records.isEmpty())
        assertEquals(2.0, item.quantity, 0.0)
        assertTrue(previews.preview("local", item.copy(quantity = 7.0)).records.isEmpty())
    }

    @Test fun consumedReceiptRemainsIdempotentEvenWhenItsLastPieceIsGone() {
        val empty = item.copy(quantity = 0.0)
        assertTrue(previews.receive("local", empty, "2", null, "receipt"))
        previews.preview("local", empty).records.forEach { assertTrue(previews.consumeRecord("local", empty.id, it.id)) }
        assertFalse(previews.receive("local", empty, "2", null, "receipt"))
        assertTrue(previews.preview("local", empty).records.isEmpty())
        assertTrue(previews.receive("local", empty, "1", LocalDate.parse("2026-11-20"), "new-receipt"))
        assertEquals("1", previews.preview("local", empty).total.previewText())
    }

    @Test fun allRecordOperationsRejectOtherScopesItemsAndMissingIds() {
        val before = snapshot()
        val id = before.records.first().id
        for ((scope, itemId, recordId) in listOf(Triple("other-family", item.id, id),
            Triple("local", "other-item", id), Triple("local", item.id, "missing"))) {
            assertFalse(previews.updateRecord(scope, itemId, recordId, "阳台", null, null))
            assertFalse(previews.markOpened(scope, itemId, recordId))
            assertFalse(previews.consumeRecord(scope, itemId, recordId))
        }
        assertSame(before, snapshot())
        val other = previews.preview("other-family", item)
        previews.consumeRecord("local", item.id, id)
        assertSame(other, previews.preview("other-family", item))
    }

    @Test fun aggregateRecordsRejectEveryIndividualOperation() {
        val measured = item.copy(unit = "kg", quantity = 2.5)
        val before = previews.preview("local", measured)
        val id = before.records.single().id
        assertFalse(previews.updateRecord("local", measured.id, id, "阳台", null, null))
        assertFalse(previews.markOpened("local", measured.id, id))
        assertFalse(previews.consumeRecord("local", measured.id, id))
        assertSame(before, previews.preview("local", measured))
        assertEquals("2.5", before.total.previewText())
    }

    @Test fun editedDatesSurviveGlobalChangesWithoutAnyReceipt() {
        val id = snapshot().records.first().id
        previews.updateRecord("local", item.id, id, "阳台", "2026-11-15", null)
        val before = snapshot()
        val editedParent = item.copy(quantity = 9.0, location = "储物柜", expiry = "2026-12-20")
        assertSame(before, previews.preview("local", editedParent))
        assertTrue(before.originalChanged(editedParent))
        assertEquals("2026-11-15", before.records.first().expiryDate)
    }

    @Test fun editsValidateNewDatesAndLocationsWithoutDroppingLegacyValues() {
        val legacy = item.copy(expiry = "legacy-date")
        val id = previews.preview("local", legacy).records.first().id
        assertTrue(previews.updateRecord("local", legacy.id, id, "阳台", "legacy-date", legacy.openedAt))
        val before = previews.preview("local", legacy)
        assertFalse(previews.updateRecord("local", legacy.id, id, " ", null, null))
        assertFalse(previews.updateRecord("local", legacy.id, id, "冰箱", "2026-02-30", null))
        assertFalse(previews.updateRecord("local", legacy.id, id, "冰箱", null, "yesterday"))
        assertSame(before, previews.preview("local", legacy))
    }
}
