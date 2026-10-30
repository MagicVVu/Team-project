package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.ring.RingInventoryPage
import com.example.teamapp.ui.theme.TeamAppTheme
import org.json.JSONArray
import org.json.JSONObject
import org.junit.*
import java.util.UUID

class ProductRingIntegrationTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val prefs = mutableSetOf<String>()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    @Before fun setup() {
        val prefix = "product_ring_${UUID.randomUUID()}_"
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                prefs += prefix + name
                return super.getSharedPreferences(prefix + name, mode)
            }
        }
        val a = CloudAccount(BuildConfig.CLOUD_API_URL, "offline-never-sent", "fixture-user", "Fixture", "fixture-home")
        CloudCredentials(context).save(a)
        fun objectRow(id: String, name: String, status: String = "ACTIVE") = JSONObject().put("id", id).put("name", name)
            .put("unit", "个").put("category", "food").put("minimum_quantity", "5")
            .put("storage_location", "冰箱").put("expires_on", "2026-12-01").put("status", status).put("version", 1)
        val batches = JSONArray()
        repeat(10) { batches.put(objectRow("apple-$it", "苹果")) }
        repeat(12) { batches.put(objectRow("red-apple-$it", "红苹果")) }
        batches.put(objectRow("finished", "苹果", "FINISHED"))
        val product = JSONObject().put("product_id", "one").put("name", "苹果").put("base_unit", "个")
            .put("count", 22).put("category", "food").put("version", 1).put("inventory_items", batches)
        context.getSharedPreferences("magicvvu_cloud_cache", 0).edit().putString("${a.address}|${a.userId}|${a.householdId}",
            JSONObject().put("inventory_schema", "individual-v1").put("inventory", batches).put("shopping", JSONArray()).put("products", JSONArray().put(product).put(JSONObject(product.toString()).put("product_id", "empty").put("name", "全麦面包").put("count", 0).put("inventory_items", JSONArray()))).toString()).commit()
        store = InventoryStore(context)
    }
    @After fun cleanup() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        prefs.forEach { base.getSharedPreferences(it, 0).edit().clear().commit() }
    }
    private fun run(dark: Boolean, english: Boolean) {
        compose.setContent { AppLanguageProvider(if (english) "en" else "zh-CN") { TeamAppTheme(darkTheme = dark) {
            RingInventoryPage(store, { _, _ -> }, {}, {})
        } } }
        compose.onAllNodesWithText("*0", useUnmergedTree = true).assertCountEquals(0)
        compose.onAllNodesWithText("全麦面包", useUnmergedTree = true).assertCountEquals(0)
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).assertTextEquals("苹果")
        compose.onAllNodesWithText("*22", useUnmergedTree = true).onFirst().assertExists()
        shot("product-ring-${if (dark) "dark" else "light"}")
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("product-inventory-detail").assertExists()
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("product-batch-apple-0"))
        compose.onNodeWithTag("product-batch-apple-0").assertExists()
        compose.onAllNodesWithText(if (english) "Stocked on: Not recorded" else "入库日期：未登记").onFirst().assertExists()
        compose.onAllNodesWithText(if (english) "Opening status: Unopened" else "开封状态：未开封").onFirst().assertExists()
        compose.onAllNodesWithText(if (english) "Status: In stock" else "状态：在库").assertCountEquals(0)
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("product-batch-red-apple-11"))
        compose.onNodeWithTag("product-batch-red-apple-11").assertExists()
        compose.onNodeWithTag("product-batch-finished").assertDoesNotExist()
        compose.onNodeWithTag("product-inventory-detail").performScrollToIndex(0)
        compose.onNodeWithTag("product-show-ended").performClick()
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("product-batch-finished"))
        compose.onNodeWithTag("product-batch-finished").assertExists()
        compose.onNodeWithTag("product-inventory-detail").performScrollToIndex(0)
        shot("product-detail-${if (dark) "dark" else "light"}")
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).assertTextEquals("苹果")
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        val screenshot = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        context.cacheDir.resolve("$name.png").outputStream().use {
            screenshot.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        screenshot.recycle()
    }
    @Test fun lightChineseProductOpensAllRealBatches() = run(false, false)
    @Test fun darkEnglishProductOpensAllRealBatches() = run(true, true)
    @Test fun consumeActionUsesTheSelectedRedAppleIdentity() {
        var chosen: Pair<StockItem, String>? = null
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme {
            RingInventoryPage(store, { item, action -> chosen = item to action }, {}, {})
        } } }
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("consume-item-red-apple-3"))
        compose.onNodeWithTag("consume-item-red-apple-3").performClick()
        compose.waitUntil(5_000) { chosen != null }
        Assert.assertEquals("red-apple-3", chosen!!.first.id)
        Assert.assertEquals("红苹果", chosen!!.first.name)
        Assert.assertEquals("消耗库存", chosen!!.second)
    }
}
