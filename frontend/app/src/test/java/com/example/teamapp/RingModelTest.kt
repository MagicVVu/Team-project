package com.example.teamapp

import com.example.teamapp.ui.ring.*
import org.junit.Assert.*
import org.junit.Test

class RingModelTest {
    @Test fun fixedSpacingAndBoundedWindowForEveryRequestedSize() {
        listOf(0, 1, 3, 12, 30, 100, 1000).forEach { count ->
            for (position in 0 until count) {
                val visible = RingMath.visible(position.toFloat(), count).toList()
                assertTrue(visible.size <= 8)
                assertEquals(visible.size, visible.distinct().size)
                assertTrue(position in visible)
                assertTrue(visible.all { it in 0 until count })
                assertEquals(30f, RingMath.angle(position + 1, position.toFloat()) - RingMath.angle(position, position.toFloat()), 0f)
            }
        }
        assertTrue(RingMath.visible(0f, 0).isEmpty())
        assertEquals(listOf(0), RingMath.visible(0f, 1).toList())
        assertTrue(99 in RingMath.visible(99f, 100))
    }
    @Test fun dragStopsAtFiniteEndsWithSmallElasticOvershoot() {
        assertEquals(-.18f, RingMath.drag(0f, 180f, 100), .001f)
        assertEquals(99.18f, RingMath.drag(99f, -180f, 100), .001f)
        assertEquals(0, RingMath.index(-.18f, 100))
        assertEquals(99, RingMath.index(99.18f, 100))
        assertEquals(0f, RingMath.drag(0f, 120f, 1), 0f)
        assertEquals(2f, RingMath.deltaDegrees(179f, -179f), .001f)
    }
    @Test fun selectionSurvivesAddsUpdatesSortAndFiltersById() {
        val ids = listOf("a", "b", "c")
        assertEquals("b", RingMath.selection(ids, ids + "d", "b", false))
        assertEquals("b", RingMath.selection(ids, listOf("c", "a", "b"), "b", false))
        assertEquals("b", RingMath.selection(ids, listOf("b", "c"), "b", true))
        assertEquals("a", RingMath.selection(ids, listOf("a", "c"), "b", true))
    }
    @Test fun deletingSelectedPicksNextOrPreviousAtTheEnd() {
        val ids = listOf("a", "b", "c")
        assertEquals("c", RingMath.selection(ids, listOf("a", "c"), "b", false))
        assertEquals("b", RingMath.selection(ids, listOf("a", "b"), "c", false))
        assertNull(RingMath.selection(ids, emptyList(), "a", false))
    }
    @Test fun filtersAndDefaultOrderUseExistingStockStatus() {
        val fixtures = mockRingInventory(100)
        val all = ringResults(fixtures, 3, "", "全部", false, RingOrder.STATUS)
        assertEquals(100, all.size)
        assertEquals(100, all.map { it.id }.distinct().size)
        assertEquals(34, ringResults(fixtures, 3, "", "食品", false, RingOrder.STATUS).size)
        assertEquals(1, ringResults(fixtures, 3, "100", "全部", false, RingOrder.STATUS).size)
        assertEquals(75, ringResults(fixtures, 3, "", "全部", true, RingOrder.STATUS).size)
        assertEquals(100, all.map { it.id }.toSet().size)
    }
}
