package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.AppEntry
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.util.UUID

class CloudUiIntegrationTest {
    @get:Rule val compose = createComposeRule()

    @Test fun phoneLoginCreateHomeAddPlanAndPurchaseThroughRealScreens() {
        val url = InstrumentationRegistry.getArguments().getString("cloudTestUrl").orEmpty()
        assumeTrue("Requires isolated test service", url.isNotBlank())
        val suffix = System.currentTimeMillis().toString().takeLast(9)
        val phone = "+1998${suffix}1"
        val password = UUID.randomUUID().toString()
        runBlocking {
            assertTrue(CloudApi(url).request("GET", "/api/v1/health").getBoolean("isolated_test"))
            CloudApi(url).register(phone, password, "UI 联调")
        }
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val context = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences("cloud_ui_${suffix}_$name", mode)
        }
        val store = InventoryStore(context)
        try {
            compose.setContent { TeamAppTheme(darkTheme=false) { AppEntry(store) } }
            compose.onNodeWithTag("auth-phone").performScrollTo().performTextInput(phone)
            compose.onNodeWithTag("auth-server").performScrollTo().performTextClearance()
            compose.onNodeWithTag("auth-server").performTextInput(url)
            compose.onNodeWithTag("auth-password").performScrollTo().performTextInput(password)
            compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
            compose.waitUntil(25_000) { store.cloud.signedIn && !store.cloud.busy }
            compose.onNodeWithText("新家庭名称").performScrollTo().performTextInput("UI 家庭 $suffix")
            compose.onNodeWithText("创建家庭").performScrollTo().performClick()
            compose.waitUntil(25_000) { !store.cloud.account?.householdId.isNullOrBlank() && !store.cloud.busy }
            compose.onNodeWithText("拍照添加").performClick()
            compose.onNodeWithText("改为手动填写").performClick()
            compose.onNodeWithText("物品名称 *").performTextInput("UI 联调牛奶")
            compose.onNodeWithText("数量 *").performTextInput("2")
            compose.onNodeWithText("单位 *（如盒、袋、瓶、个）").performTextInput("盒")
            compose.onNodeWithText("最低库存（选填，默认 0）").performScrollTo().performTextClearance()
            compose.onNodeWithText("最低库存（选填，默认 0）").performTextInput("3")
            compose.onNodeWithText("确认添加").performScrollTo().performClick()
            compose.waitUntil(25_000) { store.items.size == 1 && !store.cloud.busy }
            compose.onNodeWithText("库存", useUnmergedTree=true).performClick()
            compose.onNodeWithTag("ring-selected-info").performScrollTo().performClick()
            compose.onNodeWithText("加入采购清单 / 调整计划").performScrollTo().performClick()
            compose.onNodeWithText("确认保存").performClick()
            compose.waitUntil(25_000) { store.purchases.size == 1 && !store.cloud.busy }
            compose.onNodeWithText("清单", useUnmergedTree=true).performClick()
            compose.onNodeWithText("已购买").performClick()
            compose.onNodeWithText("实际数量（盒）").performTextClearance()
            compose.onNodeWithText("实际数量（盒）").performTextInput("3")
            compose.onNodeWithText("确认购买并入库").performClick()
            compose.waitUntil(25_000) { store.items.size == 2 && !store.cloud.busy }
            assertEquals(5.0, store.items.sumOf { it.quantity }, 0.0)
            assertTrue(store.purchases.isEmpty())
            // Empty-list mascot motion can prevent Espresso from considering
            // this emulator idle. Freeze frame advancement for static checks.
            compose.mainClock.autoAdvance = false
            compose.mainClock.advanceTimeBy(500)
            compose.onNodeWithText("已购历史").performClick()
            compose.mainClock.advanceTimeBy(500)
            compose.onNodeWithText("UI 联调牛奶").assertExists()
            screenshot("cloud-purchased-history")
            compose.onNodeWithText("库存", useUnmergedTree=true).performClick()
            compose.mainClock.advanceTimeBy(500)
            compose.onNodeWithText("我的库存").assertExists()
            screenshot("cloud-inventory")
        } finally {
            compose.mainClock.autoAdvance = true
            runBlocking { runCatching { store.cloud.logout() } }
            for (name in listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")) context.getSharedPreferences(name, 0).edit().clear().commit()
        }
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val folder = context.cacheDir.resolve("cloud-verification").apply { mkdirs() }
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
