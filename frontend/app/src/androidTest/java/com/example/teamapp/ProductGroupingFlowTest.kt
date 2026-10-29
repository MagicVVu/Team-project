package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.*
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.*
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.UUID

/** Offline transport and dedicated preferences: no live account or inventory is changed. */
class ProductGroupingFlowTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private lateinit var context: Context
    private lateinit var api: GroupingApi
    private lateinit var cloud: CloudStore
    private val preferenceNames = mutableSetOf<String>()
    private val savedIds = mutableListOf<String>()
    private var input by mutableStateOf<ProductGroupingInput?>(null)
    private var error by mutableStateOf("")
    private val item = StockItem(id = UUID.randomUUID().toString(), name = "纯牛奶", quantity = 10.0,
        quantityExact = "10", unit = "盒", category = "食品", location = "冰箱")

    @Before fun setup() {
        val prefix = "grouping_flow_${UUID.randomUUID()}_"
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                preferenceNames += prefix + name
                return super.getSharedPreferences(prefix + name, mode)
            }
        }
        api = GroupingApi()
        CloudCredentials(context).save(CloudAccount(BuildConfig.CLOUD_API_URL, "offline-never-sent", api.user, "Fixture", api.home))
        cloud = CloudStore(context) { _, _ -> api }
    }
    @After fun cleanup() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        preferenceNames.forEach { base.getSharedPreferences(it, 0).edit().clear().commit() }
    }
    private fun show(dark: Boolean = false, english: Boolean = false) {
        input = ProductGroupingInput(item, cloud.scopeKey)
        compose.setContent { AppLanguageProvider(if (english) "en" else "zh-CN") { TeamAppTheme(darkTheme = dark) {
            Column {
                Text(error, modifier = Modifier.testTag("grouping-test-error"))
                ProductGroupingFlow(cloud, input, clear = { input = null }, busy = {}, error = { error = it }, saved = { savedIds += it })
            }
        } } }
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        // The dialog window's platform enter animation is outside Compose's test clock.
        android.os.SystemClock.sleep(350)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        context.cacheDir.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun serverGroupsAutomaticallyAndReceivesWholeItemCount() {
        api.candidates = listOf(api.match(api.first, "牛奶", api.product), api.match(api.second, "鲜牛奶", null))
        show()
        compose.waitUntil(5_000) { savedIds.isNotEmpty() }
        compose.onNodeWithTag("product-grouping-dialog").assertDoesNotExist()
        val body = JSONObject(api.writes.single())
        Assert.assertEquals(item.id, body.getString("id"))
        Assert.assertEquals("10", body.getString("quantity"))
        Assert.assertFalse(body.has("product_grouping"))
        Assert.assertEquals(0, api.matchReads)
    }

    @Test fun matchingEndpointIsNoLongerRequiredByTheEntryFlow() {
        api.matchFailure = true
        show(dark = true, english = true)
        compose.waitUntil(5_000) { savedIds.isNotEmpty() }
        Assert.assertEquals(1, api.writes.size)
        Assert.assertEquals(0, api.matchReads)
    }

    @Test fun uncertainSaveSurvivesStoreRecreationAndReplaysTheSameBody() {
        api.timeoutOnce = true
        show()
        compose.waitUntil(5_000) { cloud.pendingProductGrouping() != null && error.isNotBlank() }
        compose.onNodeWithTag("product-grouping-recovery").assertExists()
        val restored = CloudStore(context) { _, _ -> api }
        val pending = restored.pendingProductGrouping()
        Assert.assertNotNull(pending)
        Assert.assertEquals(api.writes.single(), pending!!.body)
        runBlocking { restored.replayGroupedInventory(pending) }
        Assert.assertEquals(2, api.writes.size)
        Assert.assertEquals(api.writes[0], api.writes[1])
        Assert.assertNull(restored.pendingProductGrouping())
    }

    @Test fun expiredAuthenticationDoesNotEraseAnEarlierUnknownSave() {
        api.timeoutOnce = true
        show()
        compose.waitUntil(5_000) { cloud.pendingProductGrouping() != null && error.isNotBlank() }
        val pending = cloud.pendingProductGrouping()!!
        api.authFailure = true
        runBlocking { runCatching { cloud.replayGroupedInventory(pending) } }
        Assert.assertEquals(pending, cloud.pendingProductGrouping())
    }
}

private class GroupingApi : CloudApi(BuildConfig.CLOUD_API_URL) {
    val home = "00000000-0000-4000-8000-000000000001"
    val user = "00000000-0000-4000-8000-000000000002"
    val first = "00000000-0000-4000-8000-000000000003"
    val second = "00000000-0000-4000-8000-000000000004"
    val product = "00000000-0000-4000-8000-000000000005"
    var candidates = emptyList<JSONObject>()
    var matchReads = 0
    var matchFailure = false
    var timeoutOnce = false
    var authFailure = false
    val writes = mutableListOf<String>()
    fun match(id: String, name: String, pid: String?) = JSONObject().put("inventory_item_id", id).put("name", name)
        .put("inventory_version", 3).put("product_id", pid ?: JSONObject.NULL)
        .put("product_version", if (pid != null) 7 else JSONObject.NULL).put("product_name", if (pid != null) "牛奶" else JSONObject.NULL)
    override suspend fun request(method: String, path: String, body: JSONObject?): JSONObject {
        if (path.contains("inventory-product-matches?")) {
            matchReads++
            if (matchFailure) throw IOException("Offline fixture: matching unavailable")
            return JSONObject().put("protocol_version", "inventory-product-matches-1").put("total", candidates.size)
                .put("items", JSONArray(candidates))
        }
        if (method == "POST" && path.endsWith("inventory-items")) {
            writes += requireNotNull(body).toString()
            if (timeoutOnce) { timeoutOnce = false; throw SocketTimeoutException("Offline fixture: result unknown") }
            if (authFailure) throw CloudFailure(401, "Offline fixture: login expired")
            return JSONObject().put("id", body.getString("id"))
        }
        if (method == "GET" && (path.contains("inventory-items?") || path.contains("inventory-products?") || path.contains("shopping-list/items?"))) {
            return JSONObject().put("items", JSONArray()).put("total", 0)
        }
        throw IllegalStateException("Unexpected offline request: $method $path")
    }
}
