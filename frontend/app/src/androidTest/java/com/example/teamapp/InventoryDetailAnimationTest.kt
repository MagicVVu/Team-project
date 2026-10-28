package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.ring.RingInventoryPage
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith
import kotlin.math.abs

/** Uses isolated guest preferences; no production account, cloud writes or seeded inventory. */
@RunWith(AndroidJUnit4::class)
class InventoryDetailAnimationTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private val preferenceNames = listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("inventory_detail_animation_test_$name", mode)
        }
        preferenceNames.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() }
        store = InventoryStore(context)
        store.saveItem(StockItem(id = "detail-first", name = "测试牛奶", quantity = 1.0, unit = "盒", minimum = 3.0))
        store.saveItem(StockItem(id = "detail-second", name = "测试纸巾", quantity = 2.0, unit = "包", category = "日用品"))
    }

    @After fun cleanup() { preferenceNames.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() } }

    private fun showApp(dark: Boolean = false) {
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
    }

    @Test fun unselectedTapSelectsAndSelectedTapExpands() {
        showApp()
        compose.onNodeWithTag("ring-card-detail-second").performTouchInput { click() }
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：测试纸巾")
        compose.onNodeWithTag("ring-card-detail-second").performTouchInput { click() }
        compose.onNodeWithTag("inventory-detail-name").assertTextEquals("测试纸巾")
        shot("light-detail")
        compose.onNodeWithTag("inventory-detail-close").performClick()
        waitForClosed()
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-card-detail-second").assertIsSelected()
        compose.onNodeWithTag("ring-selected-info").assertIsDisplayed()
    }

    @Test fun darkDetailBackAndBackdropRestoreSelection() {
        showApp(dark = true)
        repeat(2) {
            compose.onNodeWithTag("ring-selected-info").performClick()
            compose.onNodeWithTag("inventory-detail-name").assertTextEquals("测试牛奶")
            if (it == 0) shot("dark-detail")
            if (it == 0) compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
            else compose.onNodeWithTag("inventory-detail-backdrop").performTouchInput { click(Offset(width - 3f, height - 3f)) }
            compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
            compose.onNodeWithTag("ring-card-detail-first").assertIsSelected()
        }
    }

    @Test fun rapidTapsAndEarlyBackReverseFromCurrentBounds() {
        showApp()
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("ring-card-detail-first").performClick()
        compose.mainClock.advanceTimeBy(450)
        compose.onAllNodesWithTag("inventory-detail-card").assertCountEquals(1)
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        compose.mainClock.advanceTimeBy(900)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").assertIsDisplayed()
    }

    @Test fun cardStartsAtMeasuredPreviewAndSurvivesDeletionWhileExpanding() {
        showApp()
        val source = compose.onNodeWithTag("ring-selected-info").fetchSemanticsNode().boundsInRoot
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("ring-selected-info").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.mainClock.advanceTimeByFrame()
        val start = compose.onNodeWithTag("inventory-detail-card").fetchSemanticsNode().boundsInRoot
        Assert.assertTrue("Card must start at the real preview x", abs(source.left - start.left) < 2f)
        Assert.assertTrue("Card must start at the real preview y", abs(source.top - start.top) < 2f)
        Assert.assertTrue("Card must start at the real preview width", abs(source.width - start.width) < 2f)
        compose.mainClock.advanceTimeBy(80)
        val during = compose.onNodeWithTag("inventory-detail-card").fetchSemanticsNode().boundsInRoot
        Assert.assertTrue("Expansion should immediately widen and lift the same card", during.width > start.width && during.top < start.top)
        compose.runOnUiThread { store.deleteItem("detail-first") }
        compose.mainClock.advanceTimeBy(900)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").assertIsDisplayed()
    }

    @Test fun liveDataUpdatesAndDeletionSafelyRemoveOverlay() {
        showApp()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.runOnIdle {
            val first = store.items.first { it.id == "detail-first" }
            store.saveItem(first.copy(quantity = 7.0, expiry = ""))
        }
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("7 盒")
        compose.onNodeWithTag("inventory-detail-facts").assertExists()
        compose.runOnIdle { store.deleteItem("detail-first") }
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：测试纸巾")
    }

    @Test fun switchingTabsDisposesDetailAndReusesExistingEditor() {
        showApp()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithText("首页", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-content").performScrollToNode(hasTestTag("inventory-detail-edit"))
        compose.onNodeWithTag("inventory-detail-edit").performClick()
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
        compose.onNodeWithText("物品名称 *").assertExists()
    }

    @Test fun smallPhoneFitsWithoutPageScrollAndLongDetailRemainsReadable() {
        compose.runOnIdle {
            val first = store.items.first { it.id == "detail-first" }
            store.saveItem(first.copy(name = "一件名称很长的库存物品用于检查详情文本换行和小屏幕上的关闭行为"))
        }
        compose.setContent {
            TeamAppTheme {
                Box(Modifier.requiredSize(360.dp, 640.dp)) { MagicApp(store) }
            }
        }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        val page = compose.onNodeWithTag("ring-inventory-page").fetchSemanticsNode()
        Assert.assertFalse(page.config.contains(SemanticsActions.ScrollBy))
        Assert.assertFalse(page.config.contains(SemanticsProperties.VerticalScrollAxisRange))
        listOf("ring-toolbar", "ring-selected-info", "ring-category-全部", "ring-seek", "ring-position").forEach {
            compose.onNodeWithTag(it).assertIsDisplayed()
            val bounds = compose.onNodeWithTag(it).fetchSemanticsNode().boundsInRoot
            Assert.assertTrue("$it should fit in the inventory page", bounds.top >= page.boundsInRoot.top && bounds.bottom <= page.boundsInRoot.bottom)
        }
        shot("small-phone-page")
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-name").assertTextContains("一件名称很长", substring = true)
        shot("small-phone-detail")
        compose.onNodeWithTag("inventory-detail-close").assertIsDisplayed().performClick()
    }

    @Test fun largeFontAndShortViewportKeepControlsVisibleAndDisposeCleanly() {
        var mounted by mutableStateOf(true)
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                TeamAppTheme(darkTheme = false) {
                    if (mounted) Box(Modifier.requiredSize(420.dp, 280.dp)) {
                        RingInventoryPage(store, { _, _ -> }, {}, {})
                    }
                }
            }
        }
        compose.onNodeWithTag("ring-selected-info").assertIsDisplayed()
        compose.onNodeWithTag("ring-category-全部").assertIsDisplayed()
        val page = compose.onNodeWithTag("ring-inventory-page").fetchSemanticsNode().boundsInRoot
        listOf("ring-selected-info", "ring-categories", "ring-seek").forEach { tag ->
            val bounds = compose.onNodeWithTag(tag).fetchSemanticsNode().boundsInRoot
            Assert.assertTrue("$tag must fit the short viewport", bounds.top >= page.top && bounds.bottom <= page.bottom)
        }
        val categories = compose.onNodeWithTag("ring-categories").fetchSemanticsNode().boundsInRoot
        val previous = compose.onNodeWithTag("ring-previous").fetchSemanticsNode().boundsInRoot
        Assert.assertTrue("Category controls must not cover browsing controls", categories.bottom <= previous.top)
        shot("short-viewport-large-font")
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-close").assertIsDisplayed()
        compose.runOnIdle { mounted = false }
        compose.onNodeWithTag("inventory-detail-card").assertDoesNotExist()
    }

    private fun waitForClosed() {
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("inventory-detail-card").fetchSemanticsNodes().isEmpty() }
    }

    private fun shot(name: String) {
        compose.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val image = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val folder = context.cacheDir.resolve("inventory-detail-animation").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }
}
