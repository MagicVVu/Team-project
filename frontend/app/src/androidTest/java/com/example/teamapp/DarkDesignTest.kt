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
import java.time.LocalDate
import org.junit.*
import org.junit.runner.RunWith

/** All mutations are confined to a dedicated test preferences file. */
@RunWith(AndroidJUnit4::class)
class DarkDesignTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private lateinit var milk: StockItem

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("dark_design_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        store.updateAppearance("深色")
        milk = StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0, expiry = LocalDate.now().plusDays(2).toString())
        store.saveItem(milk)
        store.saveItem(StockItem(name = "测试全麦面包", quantity = 2.0, unit = "袋", expiry = LocalDate.now().minusDays(2).toString()))
        store.saveItem(StockItem(name = "测试洗衣液", quantity = 1.0, unit = "瓶", category = "日用品", location = "阳台", minimum = 2.0))
    }

    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }

    private fun launch() {
        compose.setContent { TeamAppTheme(darkTheme = store.appearance != "浅色") { MagicApp(store) } }
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        // MuMu's renderer presents frames after Compose becomes idle.
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val folder = context.cacheDir.resolve("dark-design-verification").apply { mkdirs() }
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun tabsSearchFilterDetailAndRemindersUseRealRecords() {
        launch()
        compose.onNodeWithContentDescription("Mew 库存管家").assertExists()
        screenshot("home-fixture")
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        screenshot("inventory-fixture")
        compose.onNodeWithTag("ring-category-日用品").performClick()
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：测试洗衣液")
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-category-全部").performClick()
        compose.onNodeWithTag("ring-search-toggle").performClick()
        compose.onNodeWithTag("ring-search").performTextInput("测试纯牛奶")
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithText("最低库存：3 盒").assertExists()
        screenshot("detail-fixture")
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithContentDescription("库存提醒").performClick()
        compose.onNodeWithText("测试全麦面包").assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        screenshot("profile-fixture")
        compose.onNodeWithText("关于 Mewstow").performScrollTo().performClick()
        compose.onNodeWithContentDescription("Mewstow").assertIsDisplayed()
        compose.onNodeWithText("猫又 Nekomata · 昵称 Mew").assertExists()
        screenshot("about-mewstow")
        compose.runOnIdle { Assert.assertEquals(3, store.items.size) }
    }

    @Test fun purchaseStillValidatesActualQuantityBeforeUpdatingStock() {
        store.plan(milk.id, 2.0)
        launch()
        compose.onNodeWithText("清单", useUnmergedTree = true).performClick()
        screenshot("shopping-fixture")
        compose.onNodeWithText("购买入库").performScrollTo().performClick()
        screenshot("purchase-fixture")
        compose.onNodeWithText("确认入库").performClick()
        compose.onNodeWithText("请输入有效正数").assertExists()
        compose.runOnIdle { Assert.assertEquals(1.0, store.items.first { it.id == milk.id }.quantity, 0.0) }
        compose.onNodeWithText("实际购入数量（盒）").performTextInput("1")
        compose.onNodeWithText("确认入库").performClick()
        compose.runOnIdle {
            Assert.assertEquals(2.0, store.items.first { it.id == milk.id }.quantity, 0.0)
            Assert.assertTrue(store.purchases.isEmpty())
        }
    }

    @Test fun cancelledPhotoAndManualEntryDoNotChangeStock() {
        launch()
        compose.onNodeWithText("拍照添加").performScrollTo().performClick()
        screenshot("photo-fixture")
        compose.onNodeWithText("手动填写").performClick()
        screenshot("manual-fixture")
        compose.onNodeWithTag("photo-name").performTextInput("取消测试")
        compose.onNodeWithTag("photo-close").performClick()
        compose.runOnIdle { Assert.assertEquals(3, store.items.size) }
    }

    @Test fun appearanceSwitchKeepsCurrentPanelAndInventory() {
        launch()
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        compose.onNodeWithText("通用设置").performScrollTo().performClick()
        screenshot("settings-fixture")
        compose.onNodeWithText("浅色").performClick()
        compose.runOnIdle { Assert.assertEquals("浅色", store.appearance) }
        compose.onNodeWithText("外观模式", substring = true).performClick()
        compose.onNodeWithText("深色").performClick()
        compose.runOnIdle {
            Assert.assertEquals("深色", store.appearance)
            Assert.assertEquals(3, store.items.size)
        }
        compose.onNodeWithText("界面语言").assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("我的家庭").assertExists()
    }
}
