package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
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

/** All language and inventory changes use separate test preferences. */
@RunWith(AndroidJUnit4::class)
class AppLanguageTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private lateinit var originalData: String

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("app_language_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        // Names matching UI labels must still be shown exactly as entered.
        val item = StockItem(name = "首页", quantity = 2.0, unit = "盒", category = "食品", location = "深色", minimum = 3.0)
        store.saveItem(item)
        store.plan(item.id, 1.0)
        originalData = store.export()
    }

    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }

    private fun switchAndCheck(dark: Boolean) {
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        compose.onNodeWithText("通用设置").performScrollTo().performClick()
        compose.onNodeWithTag("language-en").performClick()
        compose.onAllNodesWithText("General settings").onLast().assertExists()
        compose.onAllNodesWithText("Appearance", substring = true).onLast().assertExists()
        compose.onNodeWithTag("language-en").assertIsSelected()
        compose.onNodeWithText("Close").performClick()
        compose.onNodeWithText("Stock", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onAllNodesWithText("首页", substring = true).onLast().assertExists()
        compose.onAllNodesWithText("深色", substring = true).onLast().assertExists()
        compose.onNodeWithText("Minimum stock: 3 盒").assertExists()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2 盒")
        compose.onNodeWithText("Close").performClick()
        compose.onNodeWithText("Shop", useUnmergedTree = true).performClick()
        compose.onNodeWithText("Receive").assertExists()
        compose.onNodeWithContentDescription("More actions for 首页").performClick()
        compose.onNodeWithText("Adjust quantity").performClick()
        compose.onNodeWithText("Adjust purchase quantity").assertExists()
        compose.onNodeWithText("Close").performClick()
        compose.runOnIdle {
            Assert.assertEquals(originalData, store.export())
            val restarted = InventoryStore(context)
            Assert.assertEquals("en", restarted.language)
            Assert.assertEquals(originalData, restarted.export())
        }
        compose.onNodeWithText("Me", useUnmergedTree = true).performClick()
        compose.onNodeWithText("General settings").performScrollTo().performClick()
        compose.onNodeWithTag("language-zh-CN").performClick()
        compose.onAllNodesWithText("通用设置").onLast().assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.runOnIdle {
            Assert.assertEquals("zh-CN", InventoryStore(context).language)
            Assert.assertEquals(originalData, store.export())
        }
    }

    @Test fun lightSwitchesImmediatelyAndPersistsWithoutChangingRecords() = switchAndCheck(false)
    @Test fun darkSwitchesImmediatelyAndPersistsWithoutChangingRecords() = switchAndCheck(true)

    @Test fun switchingLanguageRetainsUnsubmittedFormAndRoute() {
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("物品名称 *").performTextInput("未提交的牛奶")
        compose.runOnIdle { store.updateLanguage("en") }
        compose.onNodeWithText("Manual entry").assertExists()
        compose.onNodeWithText("Item name *").assertExists()
        compose.onNodeWithText("未提交的牛奶").assertExists()
        compose.onNodeWithText("Close").performClick()
        compose.onNodeWithText("Stock", useUnmergedTree = true).assertExists()
        compose.runOnIdle { Assert.assertEquals(originalData, store.export()) }
    }

    @Test fun englishReceiptRequiresActualQuantityAndUpdatesOriginalItem() {
        store.updateLanguage("en")
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
        compose.onNodeWithText("Shop", useUnmergedTree = true).performClick()
        compose.onNodeWithText("Receive").performClick()
        compose.onNodeWithText("Confirm receipt").performClick()
        compose.onNodeWithText("Enter a valid positive number").assertExists()
        compose.runOnIdle { Assert.assertEquals(originalData, store.export()) }
        compose.onNodeWithText("Actual purchase quantity (盒)").performTextInput("1")
        compose.onNodeWithText("Confirm receipt").performClick()
        compose.runOnIdle {
            Assert.assertEquals(3.0, store.items.single().quantity, 0.0)
            Assert.assertEquals("首页", store.items.single().name)
            Assert.assertEquals("深色", store.items.single().location)
            Assert.assertTrue(store.purchases.isEmpty())
        }
    }

    @Test fun englishManualEntrySavesUserValuesAndShowsLocalizedFeedback() {
        store.updateLanguage("en")
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
        compose.onNodeWithText("Stock", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("Item name *").performTextInput("Cookies")
        compose.onNodeWithText("Quantity *").performTextInput("2")
        compose.onNodeWithText("Unit * (e.g. box, bag, bottle)").performTextInput("袋")
        compose.onNodeWithText("Confirm add").performScrollTo().performClick()
        compose.onNodeWithText("Saved").assertExists()
        compose.runOnIdle {
            val added = store.items.single { it.name == "Cookies" }
            Assert.assertEquals(2.0, added.quantity, 0.0)
            Assert.assertEquals("袋", added.unit)
            Assert.assertEquals("冰箱", added.location)
            Assert.assertEquals("首页", store.items.first { it.name != "Cookies" }.name)
        }
    }
}
