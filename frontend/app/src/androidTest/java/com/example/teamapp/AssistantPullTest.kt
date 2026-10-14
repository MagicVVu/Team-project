package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.espresso.Espresso
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith

/** All records belong to isolated test preferences, never the user's inventory. */
@RunWith(AndroidJUnit4::class)
class AssistantPullTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("assistant_pull_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        store.saveItem(StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0))
    }

    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    private fun launch(dark: Boolean = false) { compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } } }
    private fun pull(factor: Float) {
        compose.onNodeWithTag("assistant-pull-cord").performTouchInput {
            val start = Offset(width / 2f, height * .7f)
            swipe(start, start + Offset(0f, height * factor), 500)
        }
        compose.waitForIdle()
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val file = context.cacheDir.resolve("assistant-pull/$name.png")
        file.parentFile!!.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    private fun checkTabs(dark: Boolean) {
        launch(dark)
        compose.onNodeWithTag("assistant-pull-cord").assertDoesNotExist()
        for (tab in listOf("库存", "清单", "我的")) {
            compose.onNodeWithText(tab, useUnmergedTree = true).performClick()
            compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
            pull(.3f)
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            pull(2f)
            compose.onNodeWithTag("assistant-curtain").assertIsDisplayed()
            compose.onNodeWithTag("assistant-ip").assertIsDisplayed()
            compose.onNodeWithText("首页").assertDoesNotExist()
            val curtain = compose.onNodeWithTag("assistant-curtain").fetchSemanticsNode().boundsInRoot
            val root = compose.onRoot().fetchSemanticsNode().boundsInRoot
            Assert.assertEquals(root.width, curtain.width, 1f)
            Assert.assertEquals(root.height, curtain.height, 1f)
            shot("${if (dark) "dark" else "light"}-$tab")
            compose.onNodeWithTag("assistant-close").performClick()
            compose.waitForIdle()
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
        }
        pull(2f)
        Espresso.pressBack()
        compose.waitForIdle()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
    }

    @Test fun lightPullThresholdAndCoverageWorkAcrossAllThreeTabs() { checkTabs(false) }
    @Test fun darkPullThresholdAndCoverageWorkAcrossAllThreeTabs() { checkTabs(true) }
    @Test fun inventoryAnswerAndReplenishmentRequireConfirmation() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        pull(2f)
        compose.onNodeWithText("补货建议").performClick()
        compose.onNodeWithText("测试纯牛奶：", substring = true).assertExists()
        compose.runOnIdle { Assert.assertTrue(store.purchases.isEmpty()) }
        compose.onNodeWithText("核对并加入补货清单").performClick()
        compose.onNodeWithText("确认补货建议").assertIsDisplayed()
        compose.runOnIdle { Assert.assertTrue(store.purchases.isEmpty()) }
        compose.onNodeWithText("确认").performClick()
        compose.runOnIdle {
            Assert.assertEquals(2.0, store.purchases.single().quantity, 0.0)
            Assert.assertEquals(1.0, store.items.single().quantity, 0.0)
        }
    }
}
