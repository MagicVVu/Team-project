package com.example.teamapp

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.data.*
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MagicAppTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var store: InventoryStore
    private lateinit var milk: StockItem
    @Before fun setup() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        milk = StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0)
        store.saveItem(milk)
        compose.setContent { TeamAppTheme { MagicApp(store) } }
    }
    @After fun cleanup() { InstrumentationRegistry.getInstrumentation().targetContext.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    @Test fun fourTabsAndDetailNavigationWork() {
        listOf("首页", "库存", "清单", "我的").forEach { compose.onNodeWithText(it).assertExists() }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithText("我的库存").assertIsDisplayed()
        compose.onNodeWithTag("ring-detail").performScrollTo().performClick()
        compose.onNodeWithText("最低库存：3 盒", substring = true).assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        compose.onNodeWithText("我的家庭").assertExists()
        compose.onNodeWithText("库存检测规则").assertExists()
    }
    @Test fun purchaseRequiresActualQuantityAndUpdatesAllViews() {
        compose.runOnIdle { store.plan(milk.id, 2.0) }
        compose.onNodeWithText("清单", useUnmergedTree = true).performClick()
        compose.onNodeWithText("已购买").performClick()
        compose.onNodeWithText("确认入库").performClick()
        compose.onNodeWithText("请输入有效正数").assertExists()
        compose.runOnIdle { Assert.assertEquals(1.0, store.items.single().quantity, 0.0) }
        compose.onNodeWithText("实际购入数量（盒）").performTextInput("1")
        compose.onNodeWithText("确认入库").performClick()
        compose.runOnIdle { Assert.assertEquals(2.0, store.items.single().quantity, 0.0); Assert.assertTrue(store.purchases.isEmpty()) }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onAllNodesWithText("2 盒")[0].assertExists()
    }
    @Test fun cancelledAddDoesNotChangeInventory() {
        compose.onNodeWithText("拍照添加").performClick()
        compose.onNodeWithText("改为手动填写").performClick()
        compose.onNodeWithText("物品名称 *").performTextInput("取消测试物品")
        compose.onNodeWithText("关闭").performClick()
        compose.runOnIdle { Assert.assertEquals(1, store.items.size) }
    }
}
