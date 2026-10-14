package com.example.teamapp

import android.graphics.Bitmap
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.ui.ring.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.cos
import kotlin.math.sin

@RunWith(AndroidJUnit4::class)
class RingPrototypeTest {
    @get:Rule val compose = createComposeRule()
    private fun launch() { compose.setContent { RingInventoryTestPage(false, {}, {}) } }
    private fun count(n: Int) { compose.onNodeWithTag("ring-scenario-$n").performScrollTo().performClick(); compose.waitForIdle() }
    private fun seek(index: Int) {
        compose.onNodeWithTag("ring-seek").performScrollTo().performSemanticsAction(SemanticsActions.SetProgress) { assertTrue(it(index.toFloat())) }
        compose.waitForIdle()
    }
    private fun position(text: String) { compose.onNodeWithTag("ring-position").assertTextEquals(text) }
    private fun dragArc(degrees: Float) {
        compose.onNodeWithTag("ring-viewport").performScrollTo().performTouchInput {
            val cx = width * .98f; val cy = height / 2f; val radius = width * .68f
            down(Offset(cx - radius, cy))
            (1..15).forEach { step ->
                val angle = (180f + degrees * step / 15f) * Math.PI.toFloat() / 180f
                moveTo(Offset(cx + radius * cos(angle), cy + radius * sin(angle)), 16)
            }
            up()
        }
        compose.waitForIdle()
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val folder = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir.resolve("ring-verification").apply { mkdirs() }
        val image = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }

    @Test fun allRequestedSizesKeepCardDimensionsAndCanReachTheLastItem() {
        launch()
        for (light in listOf(false, true)) {
            if (light) compose.onNodeWithTag("ring-test-theme").performScrollTo().performClick()
            var cardWidth: Float? = null
            var cardHeight: Float? = null
            for (n in listOf(0, 1, 3, 12, 30, 100)) {
                count(0)
                count(n)
                position(if (n == 0) "0 / 0" else "1 / $n")
                if (n <= 1) compose.onNodeWithTag("ring-seek").assertDoesNotExist()
                if (n > 0) {
                    val bounds = compose.onNodeWithTag("ring-card-ring-mock-0").fetchSemanticsNode().boundsInRoot
                    if (cardWidth == null) { cardWidth = bounds.width; cardHeight = bounds.height }
                    assertEquals(cardWidth!!, bounds.width, 1f)
                    assertEquals(cardHeight!!, bounds.height, 1f)
                    val visible = compose.onAllNodes(hasTestTagPrefix("ring-card-")).fetchSemanticsNodes()
                    assertTrue(visible.size <= 8)
                    assertTrue(visible.size <= n)
                }
                if (n > 1) {
                    seek(n - 1)
                    position("$n / $n")
                    compose.onNodeWithTag("ring-next").assertIsNotEnabled()
                    compose.onNodeWithTag("ring-detail").performScrollTo().performClick()
                    compose.onNodeWithTag("ring-detail-name").assertTextEquals(ringResults(mockRingInventory(n), 3, "", "全部", false, RingOrder.STATUS).last().name)
                    compose.onNodeWithText("关闭详情").performClick()
                }
            }
        }
    }

    @Test fun arcDragSnapsAndStopsAtBothEndsWithoutWrapping() {
        launch(); count(100)
        dragArc(-30f)
        position("2 / 100")
        seek(99); dragArc(-45f); position("100 / 100")
        seek(0); dragArc(45f); position("1 / 100")
        compose.onNodeWithTag("ring-previous").assertIsNotEnabled()
    }

    @Test fun searchCategoryAttentionAndDetailsAgree() {
        launch(); count(100)
        compose.onNodeWithTag("ring-category-食品").performScrollTo().performClick()
        position("1 / 34")
        compose.onNodeWithTag("ring-attention").performClick()
        position("1 / 25")
        compose.onNodeWithTag("ring-search").performScrollTo().performTextInput("099")
        position("0 / 0")
        compose.onNodeWithTag("ring-empty-action").performScrollTo().performClick()
        position("1 / 100")
        compose.onNodeWithTag("ring-search").performScrollTo().performTextInput("100")
        position("1 / 1")
        compose.onNodeWithTag("ring-seek").assertDoesNotExist()
        compose.onNodeWithTag("ring-detail").performScrollTo().performClick()
        compose.onNodeWithTag("ring-detail-name").assertTextEquals(mockRingInventory(100).last().name)
    }

    @Test fun mockAddDeleteUpdateAndEmptyAddKeepSelectionCoherent() {
        launch(); count(30); seek(1)
        val ordered = ringResults(mockRingInventory(30), 3, "", "全部", false, RingOrder.STATUS)
        compose.onNodeWithTag("ring-mock-add").performScrollTo().performClick()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：${ordered[1].name}")
        compose.onNodeWithTag("ring-mock-update").performScrollTo().performClick()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：${ordered[1].name}")
        compose.onNodeWithTag("ring-mock-delete").performScrollTo().performClick()
        compose.waitForIdle()
        compose.onNodeWithTag("ring-mock-total").assertTextEquals("30 条模拟记录 · 不写入真实库存")
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：${ordered[2].name}")
        count(0)
        compose.onNodeWithTag("ring-empty-action").performScrollTo().performClick()
        position("1 / 1")
    }

    @Test fun draggingSeekBarPreviewsNameAndCommitsTheSameItem() {
        launch(); count(100)
        compose.onNodeWithTag("ring-seek").performScrollTo().performTouchInput {
            down(Offset(width * .1f, height / 2f))
            moveTo(Offset(width * .9f, height / 2f), 160)
        }
        compose.onNodeWithTag("ring-seek-label").assertTextContains("定位至：", substring = true)
        compose.onNodeWithTag("ring-seek").performTouchInput { up() }
        compose.waitForIdle()
        val text = compose.onNodeWithTag("ring-position").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].single().text
        val selectedIndex = text.substringBefore(" / ").toInt() - 1
        assertTrue(selectedIndex in 80..99)
        val ordered = ringResults(mockRingInventory(100), 3, "", "全部", false, RingOrder.STATUS)
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：${ordered[selectedIndex].name}")
        compose.onNodeWithTag("ring-detail").performScrollTo().performClick()
        compose.onNodeWithTag("ring-detail-name").assertTextEquals(ordered[selectedIndex].name)
    }

    @Test fun captureSixReviewScreens() {
        launch()
        for (mode in listOf("dark", "light")) {
            if (mode == "light") compose.onNodeWithTag("ring-test-theme").performScrollTo().performClick()
            for (n in listOf(3, 30, 100)) {
                count(0); count(n)
                seek(when(n) { 3 -> 1; 30 -> 14; else -> 89 })
                compose.onNodeWithTag("ring-scenario-$n").performScrollTo()
                shot("$mode-$n")
            }
        }
    }

    private fun hasTestTagPrefix(prefix: String) = SemanticsMatcher("test tag starts with $prefix") {
        it.config.getOrElse(androidx.compose.ui.semantics.SemanticsProperties.TestTag) { "" }.startsWith(prefix)
    }
}
