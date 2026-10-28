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
        fun batch(id: String, count: String, status: String) = JSONObject().put("id", id).put("name", "真实批次 $id")
            .put("quantity", count).put("unit", "盒").put("category", "food").put("minimum_quantity", "0")
            .put("storage_location", "冰箱").put("expires_on", "2026-12-01").put("status", status).put("version", 1)
        val batches = JSONArray().put(batch("batch-a", "2", "ACTIVE")).put(batch("batch-b", "0", "FINISHED"))
        val product = JSONObject().put("product_id", "one").put("name", "商品牛奶").put("base_unit", "盒")
            .put("category", "food").put("version", 1).put("inventory_items", batches)
        context.getSharedPreferences("magicvvu_cloud_cache", 0).edit().putString("${a.address}|${a.userId}|${a.householdId}",
            JSONObject().put("inventory", batches).put("shopping", JSONArray()).put("products", JSONArray().put(product)).toString()).commit()
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
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).assertTextEquals("商品牛奶")
        shot("product-ring-${if (dark) "dark" else "light"}")
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("product-inventory-detail").assertExists()
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("product-batch-batch-a"))
        compose.onNodeWithTag("product-batch-batch-a").assertExists()
        compose.onNodeWithTag("product-inventory-detail").performScrollToNode(hasTestTag("product-batch-batch-b"))
        compose.onNodeWithTag("product-batch-batch-b").assertExists()
        compose.onNodeWithTag("product-inventory-detail").performScrollToIndex(0)
        shot("product-detail-${if (dark) "dark" else "light"}")
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).assertTextEquals("商品牛奶")
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
}
