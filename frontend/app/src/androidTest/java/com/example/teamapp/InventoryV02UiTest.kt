package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith
import kotlin.math.abs

/** Production layout with isolated guest preferences; never launches the real account or inventory. */
@RunWith(AndroidJUnit4::class)
class InventoryV02UiTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private val preferenceNames = listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("inventory_v02_test_$name", mode)
        }
        preferenceNames.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() }
        store = InventoryStore(context)
        store.saveItem(StockItem(id = "v02-milk", name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0))
    }

    @After fun cleanup() {
        preferenceNames.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() }
    }

    @Test fun lightCompactToolbarAndInventoryActions() = checkPage(false)
    @Test fun darkCompactToolbarAndInventoryActions() = checkPage(true)

    private fun checkPage(dark: Boolean) {
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
        compose.onNodeWithTag("ring-toolbar").assertHeightIsEqualTo(48.dp)
        val search = compose.onNodeWithTag("ring-search").fetchSemanticsNode().boundsInRoot
        val add = compose.onNodeWithTag("ring-add").fetchSemanticsNode().boundsInRoot
        val cat = compose.onNodeWithTag("assistant-pull-cord").fetchSemanticsNode().boundsInRoot
        val density = context.resources.displayMetrics.density
        Assert.assertTrue("Search and add share one row", abs(search.center.y - add.center.y) < density * 2)
        Assert.assertTrue("Add must not cover search", search.right < add.left)
        Assert.assertTrue("Toolbar avoids the cat's touch area", add.right + density * 8 <= cat.left)
        compose.onNodeWithTag("assistant-pull-cord").assertWidthIsEqualTo(57.6.dp)
        compose.onNodeWithTag("ring-info-icon", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).performSemanticsAction(SemanticsActions.GetTextLayoutResult) { getLayout ->
            val results = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
            Assert.assertTrue(getLayout(results))
            Assert.assertEquals("The reference item name should not leave a lone character on a second line", 1, results.single().lineCount)
        }
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-previous").assertIsNotEnabled()
        compose.onNodeWithTag("ring-next").assertIsNotEnabled()
        shot(if (dark) "dark-v02" else "light-v02")

        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithText("最低库存：3 盒").assertExists()
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("inventory-detail-card").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("物品名称 *").performTextInput("取消录入的测试物品")
        compose.onNodeWithText("关闭").performClick()
        compose.runOnIdle { Assert.assertEquals(1, store.items.size) }

        compose.runOnIdle {
            store.saveItem(StockItem(id = "v02-paper", name = "测试纸巾", quantity = 2.0, unit = "包", category = "日用品", location = "储物柜"))
            store.saveItem(StockItem(id = "v02-apple", name = "测试苹果", quantity = 3.0, unit = "个", location = "冰箱"))
        }
        compose.waitForIdle()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 3")
        compose.onNodeWithTag("ring-search").performTextInput("纸巾")
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：测试纸巾")
        compose.onNodeWithTag("ring-category-食品").performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("0 / 0")
        compose.onNodeWithTag("ring-empty-action").performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 3")
        compose.onNodeWithTag("ring-category-日用品").performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-category-全部").performClick()
        compose.onNodeWithTag("ring-seek").performSemanticsAction(SemanticsActions.SetProgress) { Assert.assertTrue(it(2f)) }
        compose.waitForIdle()
        compose.onNodeWithTag("ring-position").assertTextEquals("3 / 3")
        compose.onNodeWithTag("ring-next").assertIsNotEnabled()
        compose.runOnIdle { Assert.assertEquals(3, store.items.size) }
    }

    private fun shot(name: String) {
        compose.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val folder = context.cacheDir.resolve("inventory-v02-review").apply { mkdirs() }
        val image = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }
}
