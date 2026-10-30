package com.example.teamapp

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import android.graphics.Bitmap
import com.example.teamapp.data.CloudStore
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.ring.RingInventoryPage
import com.example.teamapp.ui.theme.TeamAppTheme
import com.example.teamapp.ui.ProductGroupingInput
import com.example.teamapp.ui.ProductGroupingFlow
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.Rule
import org.junit.runner.RunWith

/** Explicit opt-in: read the signed-in device's inventory, with no business writes. */
@RunWith(AndroidJUnit4::class)
class LiveInventoryReadTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    @Test fun signedInDeviceReadsCurrentServerWithoutLegacyQuantity() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveInventoryReadOnly") == "true")
        val store = CloudStore(instrumentation.targetContext)
        assertTrue("Live check requires the device's existing signed-in account", store.signedIn)
        val scope = store.scopeKey
        store.refresh()
        assertNull(store.error)
        assertNull(store.productError)
        assertEquals(scope, store.scopeKey)
        assertTrue("Expected the existing nonempty inventory", store.items.isNotEmpty())
        assertTrue(store.products.isNotEmpty())
        assertTrue("Zero-stock products must not be returned", store.products.all { it.count > 0 })
        assertTrue("Ended objects must not be returned", store.items.all { it.lifecycleStatus == "ACTIVE" })
        assertTrue(store.items.all { it.individualRecord && it.quantity in listOf(0.0, 1.0) })
        assertTrue(store.products.all { product -> product.count == product.batches.count { it.lifecycleStatus == "ACTIVE" } })
        assertTrue(store.lastSync.isNotBlank())
        // A second instance must also parse the saved quantity-free response.
        val restored = CloudStore(instrumentation.targetContext)
        assertNull(restored.error)
        assertEquals(store.items.size, restored.items.size)
        assertEquals(store.products.map { it.id }, restored.products.map { it.id })
    }

    @Test fun realServerInventoryRendersTheRingAndDetails() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveInventoryReadOnly") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = InventoryStore(context)
        assertTrue(store.cloud.signedIn)
        runBlocking { store.cloud.refresh() }
        assertNull(store.cloud.error)
        assertNull(store.cloud.productError)
        assertTrue(store.cloud.products.isNotEmpty())
        compose.setContent {
            AppLanguageProvider("zh-CN") { TeamAppTheme {
                RingInventoryPage(store, { _, _ -> }, {}, {})
            } }
        }
        compose.onNodeWithTag("ring-info-name", useUnmergedTree = true).assertExists()
        compose.onAllNodesWithText("No value for quantity", substring = true).assertCountEquals(0)
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("product-inventory-detail").assertExists()
        compose.waitForIdle()
        val screenshot = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        context.cacheDir.resolve("live-inventory-detail-20261030.png").outputStream().use {
            screenshot.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        screenshot.recycle()
    }

    @Test fun existingServerNamePromptsBeforeAnyInventoryWrite() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveInventoryReadOnly") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val cloud = CloudStore(context)
        runBlocking { cloud.refresh() }
        val existing = cloud.items.first()
        val before = cloud.items.size
        val pending = cloud.pendingProductGrouping()
        val input = ProductGroupingInput(existing.copy(id = java.util.UUID.randomUUID().toString(), quantity = 1.0), cloud.scopeKey)
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme {
            ProductGroupingFlow(cloud, input, clear = {}, busy = {}, error = { error(it) },
                saved = { error("This read-only test must never create inventory") })
        } } }
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("product-grouping-dialog").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("product-grouping-merge").assertExists()
        compose.onNodeWithTag("product-grouping-separate").assertExists()
        assertEquals(before, cloud.items.size)
        assertEquals(pending, cloud.pendingProductGrouping())
        compose.waitForIdle()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        context.cacheDir.resolve("live-grouping-confirmation-20261030.png").outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        bitmap.recycle()
        compose.onNodeWithText("取消添加").performClick()
    }
}
