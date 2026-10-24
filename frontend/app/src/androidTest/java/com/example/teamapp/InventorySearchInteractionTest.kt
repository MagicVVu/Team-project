package com.example.teamapp

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.ring.StockRingBrowser
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Isolated in-memory inventory: no account, backend or user preferences. */
@RunWith(AndroidJUnit4::class)
class InventorySearchInteractionTest {
    @get:Rule val compose = createComposeRule()
    private var additions = 0

    private fun launch(dark: Boolean = false) {
        compose.setContent {
            TeamAppTheme(darkTheme = dark) {
                Box(Modifier.width(320.dp).fillMaxSize()) {
                    StockRingBrowser(listOf(
                        StockItem(id = "milk", name = "牛奶", category = "食品", quantity = 1.0, unit = "盒"),
                        StockItem(id = "apple", name = "苹果", category = "食品", quantity = 2.0, unit = "个"),
                        StockItem(id = "paper", name = "纸巾", category = "日用品", quantity = 1.0, unit = "包")
                    ), 3, {}, { additions++ }, showAddAction = true)
                }
            }
        }
    }

    @Test fun cancelClearsQueryPreservesCategoryAndRestoresAdd() {
        launch()
        compose.onNodeWithTag("ring-search").assertDoesNotExist()
        compose.onNodeWithTag("ring-search-surface").assertWidthIsEqualTo(48.dp)
        compose.onNodeWithTag("ring-add").assertContentDescriptionEquals("添加物品").performClick()
        compose.runOnIdle { assertEquals(1, additions) }
        compose.onNodeWithTag("ring-category-食品").performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 2")
        compose.onNodeWithTag("ring-search-toggle").performClick()
        compose.onNodeWithTag("ring-search").assertIsFocused().performTextInput("牛奶")
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-add").assertContentDescriptionEquals("取消").performClick()
        compose.onNodeWithTag("ring-search").assertDoesNotExist()
        compose.onNodeWithTag("ring-category-食品").assertIsSelected()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 2")
        compose.onNodeWithTag("ring-search-toggle").performClick()
        compose.onNodeWithTag("ring-search").assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("")))
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithTag("ring-add").performClick()
        compose.runOnIdle { assertEquals(2, additions) }
    }

    @Test fun interruptedMotionKeepsLeftEdgeAddAndViewportStationary() {
        launch(dark = true)
        val closed = compose.onNodeWithTag("ring-search-surface").fetchSemanticsNode().boundsInRoot
        val add = compose.onNodeWithTag("ring-add").fetchSemanticsNode().boundsInRoot
        val viewport = compose.onNodeWithTag("ring-viewport").fetchSemanticsNode().boundsInRoot
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("ring-search-toggle").performClick()
        compose.mainClock.advanceTimeBy(144)
        val partial = compose.onNodeWithTag("ring-search-surface").fetchSemanticsNode().boundsInRoot
        assertTrue(partial.width > closed.width)
        assertEquals(closed.left, partial.left, .1f)
        assertTrue(partial.right < add.left)
        compose.onNodeWithTag("ring-add").performClick()
        compose.mainClock.advanceTimeBy(64)
        compose.onNodeWithTag("ring-search-toggle").performClick()
        compose.mainClock.advanceTimeBy(400)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithTag("ring-search").assertIsFocused()
        val expanded = compose.onNodeWithTag("ring-search-surface").fetchSemanticsNode().boundsInRoot
        assertTrue(expanded.width > partial.width)
        assertEquals(closed.left, expanded.left, .1f)
        assertTrue(expanded.right < add.left)
        assertEquals(add, compose.onNodeWithTag("ring-add").fetchSemanticsNode().boundsInRoot)
        assertEquals(viewport, compose.onNodeWithTag("ring-viewport").fetchSemanticsNode().boundsInRoot)
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithTag("ring-search-surface").assertWidthIsEqualTo(48.dp)
        compose.onNodeWithTag("ring-search").assertDoesNotExist()
        compose.runOnIdle { assertEquals(0, additions) }
    }
}
