package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.AppEntry
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID

/** Explicit opt-in shared-cloud acceptance: only its own account/family are written. */
class SharedCloudAcceptanceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun oldTunnelSessionRequiresLoginWithoutDeletingItsEnvelope() {
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val prefix = "team_old_origin_${UUID.randomUUID()}_"
        val context = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences(prefix + name, mode)
        }
        CloudCredentials(context).save(CloudAccount("http://10.0.2.2:18080", "synthetic-not-a-real-token", "old-test", "旧测试"))
        val prefs = context.getSharedPreferences("magicvvu_cloud_credentials", 0)
        val envelope = prefs.getString("session", null)
        assertNotNull(envelope)
        assertFalse(CloudStore(context).signedIn)
        assertEquals(envelope, prefs.getString("session", null))
    }

    @Test fun registerLoginInventoryShoppingAndRemoteAgent() {
        assertEquals("debug", BuildConfig.BUILD_TYPE)
        assertEquals("com.example.teamapp", BuildConfig.APPLICATION_ID)
        assertFalse(BuildConfig.CLOUD_EXPECT_ISOLATED)
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val suffix = UUID.randomUUID().toString().replace("-", "").take(10)
        val prefix = "team_unified_${suffix}_"
        val context = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences(prefix + name, mode)
        }
        val store = InventoryStore(context)
        val phone = "+999" + System.currentTimeMillis().toString().takeLast(11)
        val password = "T7" + UUID.randomUUID().toString().replace("-", "").take(14)
        try {
            compose.setContent { TeamAppTheme(darkTheme = false) { AppEntry(store) } }
            compose.onNodeWithText("去注册").performScrollTo().performClick()
            compose.onNodeWithTag("auth-nickname").performScrollTo().performTextInput("统一包联调$suffix")
            compose.onNodeWithTag("auth-phone").performScrollTo().performTextInput(phone)
            compose.onNodeWithTag("auth-password").performScrollTo().performTextInput(password)
            compose.onNodeWithTag("auth-confirmation").performScrollTo().performTextInput(password)
            compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
            compose.waitUntil(30_000) { store.cloud.signedIn && !store.cloud.busy }
            compose.onNodeWithText("新家庭名称").performScrollTo().performTextInput("mumu-team-$suffix")
            compose.onNodeWithText("创建家庭").performScrollTo().performClick()
            compose.waitUntil(30_000) { !store.cloud.account?.householdId.isNullOrBlank() && !store.cloud.busy }
            val user = requireNotNull(store.cloud.account)
            val fixture = JSONObject().put("run", prefix).put("user_ids", org.json.JSONArray(listOf(user.userId)))
                .put("household_ids", org.json.JSONArray(listOf(user.householdId)))
            target.filesDir.resolve("team-unified-fixture.json").writeText(fixture.toString())
            runBlocking {
                val me = CloudApi(user.address, user.token).request("GET", "/api/v1/users/me")
                assertFalse(me.getBoolean("phone_verified"))
                val milk = StockItem(name = "牛奶", quantity = 3.0, unit = "盒", location = "测试冰箱")
                store.saveItemSynced(milk, null)
                val original = store.items.single()
                store.saveItemSynced(original.copy(quantity = 4.0), original)
                assertEquals(4.0, store.items.single().quantity, 0.0)
                val edited = store.items.single()
                store.planSynced(edited, 2.0, UUID.randomUUID().toString())
                val plan = store.cloud.shopping.single { !it.purchased }
                store.cloud.purchase(plan.id, 1.0, "测试冰箱", "")
                assertEquals(5.0, store.items.sumOf { it.quantity }, 0.0)
                assertTrue(store.cloud.shopping.any { it.purchased })
                store.cloud.assistant.send("牛奶还有多少？")
                val entry = store.cloud.assistant.entries.last()
                assertEquals("Agent error: ${entry.errorCode}", AssistantStatus.ANSWERED, entry.state)
                assertTrue(entry.reply.isNotBlank())
                store.deleteItemSynced(store.items.first { it.id == original.id }, UUID.randomUUID().toString())
                assertEquals(1, store.items.size)
                store.cloud.logout()
                assertFalse(store.cloud.signedIn)
                val rejected = runCatching { CloudApi(user.address, user.token).request("GET", "/api/v1/users/me") }.exceptionOrNull()
                assertTrue(rejected is CloudFailure && rejected.status == 401)
            }
        } finally {
            runBlocking { if (store.cloud.signedIn) runCatching { store.cloud.logout() } }
        }
    }
}
