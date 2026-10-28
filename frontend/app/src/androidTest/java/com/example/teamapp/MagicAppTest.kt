package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.content.Intent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.data.*
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MagicAppTest {
    @get:Rule val compose = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private lateinit var store: InventoryStore
    private lateinit var milk: StockItem
    private lateinit var context: Context
    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("navigation_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        milk = StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0)
        store.saveItem(milk)
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
    }
    @After fun cleanup() {
        // MuMu may keep a finishing foreground test activity PAUSED until another
        // task comes forward. Stop it explicitly before ActivityScenario closes.
        val stopped = CountDownLatch(1)
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) stopped.countDown() }
        compose.runOnUiThread {
            compose.activity.lifecycle.addObserver(observer)
            compose.activity.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        stopped.await(5, TimeUnit.SECONDS)
        compose.runOnUiThread { compose.activity.lifecycle.removeObserver(observer) }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
    }
    @Test fun fourTabsAndDetailNavigationWork() {
        listOf("首页", "库存", "清单", "我的").forEach { compose.onNodeWithText(it).assertExists() }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithText("我的库存").assertIsDisplayed()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithText("最低库存：3 盒", substring = true).assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
        compose.onNodeWithText("我的家庭").assertExists()
        compose.onNodeWithText("库存规则").assertExists()
    }
    @Test fun purchaseRequiresActualQuantityAndUpdatesAllViews() {
        compose.runOnIdle { store.plan(milk.id, 2.0) }
        compose.onNodeWithText("清单", useUnmergedTree = true).performClick()
        compose.onNodeWithText("购买入库").performClick()
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
        compose.onNodeWithText("手动填写").performClick()
        compose.onNodeWithTag("photo-name").performTextInput("取消测试物品")
        compose.onNodeWithTag("photo-close").performClick()
        compose.runOnIdle { Assert.assertEquals(1, store.items.size) }
    }
}
