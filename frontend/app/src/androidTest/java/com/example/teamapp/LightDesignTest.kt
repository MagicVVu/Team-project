package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith

/** Test fixtures use a separate preferences file and never clear the user's inventory. */
@RunWith(AndroidJUnit4::class)
class LightDesignTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private lateinit var milk: StockItem

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("light_design_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE).edit().clear().commit()
        store = InventoryStore(context)
        milk = StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0)
        store.saveItem(milk)
    }

    @After fun cleanup() {
        context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE).edit().clear().commit()
    }

    private fun launch(dark: Boolean = false) {
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val folder = context.cacheDir.resolve("light-design-verification").apply { mkdirs() }
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun lightTabsDetailAndProfileKeepTheirActions() {
        launch()
        compose.onNodeWithContentDescription("Mewstow").assertIsDisplayed()
        listOf("首页", "库存", "清单", "我的").forEach { compose.onNodeWithText(it, useUnmergedTree = true).assertExists() }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        screenshot("stock-ring-fixture")
        compose.onNodeWithText("查看详情 →").assertDoesNotExist()
        compose.onNodeWithTag("ring-info-icon", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag("ring-selected-info").performScrollTo().performClick()
        compose.onNodeWithText("最低库存：3 盒", substring = true).assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        compose.onNodeWithText("圆环库存测试").assertDoesNotExist()
        compose.onNodeWithText("我的家庭").assertExists()
        compose.onNodeWithText("库存规则").performClick()
        compose.onNodeWithText("提前提醒天数（0–365）").assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("通用设置").performScrollTo().performClick()
        compose.onNodeWithText("外观模式", substring = true).assertExists()
    }

    @Test fun ringUsesRealInventoryAndSearchFiltersWithoutChangingData() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithText("圆环测试设置").assertDoesNotExist()
        screenshot("stock-ring-fixture")
        compose.onNodeWithTag("ring-selected-info").performScrollTo().performClick()
        compose.onNodeWithText("最低库存：3 盒", substring = true).assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithTag("ring-search").performScrollTo().performTextInput("纯牛奶")
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithText("清空").performClick()
        compose.onNodeWithTag("ring-category-日用品").performScrollTo().performClick()
        compose.onNodeWithText("没有找到匹配的物品").performScrollTo().assertIsDisplayed()
        compose.runOnIdle { Assert.assertEquals(1, store.items.size) }
    }

    @Test fun purchaseStillRequiresConfirmedActualQuantity() {
        store.plan(milk.id, 2.0)
        launch()
        compose.onNodeWithText("清单", useUnmergedTree = true).performClick()
        screenshot("shopping-fixture")
        compose.onNodeWithContentDescription("测试纯牛奶的更多操作").performClick()
        compose.onNodeWithText("调整数量").performClick()
        compose.onNodeWithText("调整采购数量").assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.runOnIdle { Assert.assertEquals(2.0, store.purchases.single().quantity, 0.0) }
        compose.onNodeWithContentDescription("测试纯牛奶的更多操作").performClick()
        compose.onNodeWithText("移除").performClick()
        compose.runOnIdle {
            Assert.assertTrue(store.purchases.isEmpty())
            Assert.assertEquals(1.0, store.items.single().quantity, 0.0)
            store.plan(milk.id, 2.0)
        }
        compose.onNodeWithText("购买入库").performScrollTo().performClick()
        compose.onNodeWithText("确认入库").performClick()
        compose.onNodeWithText("请输入有效正数").assertExists()
        compose.runOnIdle { Assert.assertEquals(1.0, store.items.single().quantity, 0.0) }
        compose.onNodeWithText("实际购入数量（盒）").performTextInput("1")
        compose.onNodeWithText("确认入库").performClick()
        compose.runOnIdle {
            Assert.assertEquals(2.0, store.items.single().quantity, 0.0)
            Assert.assertTrue(store.purchases.isEmpty())
        }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：测试纯牛奶")
        compose.onAllNodesWithText("2 盒")[0].assertExists()
    }

    @Test fun cancelAddKeepsInventoryUntouched() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("物品名称 *").performTextInput("取消测试物品")
        compose.onNodeWithText("关闭").performClick()
        compose.runOnIdle { Assert.assertEquals(1, store.items.size) }
    }

    @Test fun darkModeKeepsExistingNavigationAndDetailActions() {
        launch(dark = true)
        compose.onNodeWithContentDescription("Mewstow").assertIsDisplayed()
        compose.onNodeWithText("Mew 助手").assertExists()
        screenshot("dark-home-fixture")
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-inventory-page").assertExists()
        compose.onNodeWithText("圆环").assertDoesNotExist()
        compose.onNodeWithTag("ring-selected-info").performScrollTo().performClick()
        compose.onNodeWithText("最低库存").assertExists()
        compose.onNodeWithText("3 盒").assertExists()
    }
}
