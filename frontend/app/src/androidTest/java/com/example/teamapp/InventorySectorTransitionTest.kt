package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.localInventoryProducts
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.UUID
import kotlin.math.abs

class InventorySectorTransitionTest {
    @get:Rule val compose = createComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val prefix = "sector_transition_${UUID.randomUUID()}_"
    private val preferences = mutableSetOf<String>()
    private val context = object : ContextWrapper(instrumentation.targetContext) {
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
            preferences += prefix + name
            return super.getSharedPreferences(prefix + name, mode)
        }
    }

    @After fun cleanup() {
        preferences.forEach { instrumentation.targetContext.getSharedPreferences(it, 0).edit().clear().commit() }
    }

    @Test fun lightSectorOpensAndReturnsToItsOwnBounds() = checkTransition(false)
    @Test fun darkSectorOpensAndReturnsToItsOwnBounds() = checkTransition(true)

    private fun checkTransition(dark: Boolean) {
        val store = InventoryStore(context)
        store.updateLanguage("zh-CN")
        store.saveItem(StockItem(id = "preview-apple", name = "青苹果", quantity = 2.0, unit = "件", location = "冰箱"))
        val productId = localInventoryProducts(store.items).single().id
        val sector = compose.onNodeWithTag("ring-card-product:$productId")
        val preview = compose.onNodeWithTag("ring-selected-info")
        val detail = compose.onNodeWithTag("inventory-detail-card")
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        sector.assertIsSelected()
        val sectorLabel = sector.fetchSemanticsNode().boundsInRoot
        val previewBounds = preview.fetchSemanticsNode().boundsInRoot
        val mode = if (dark) "dark" else "light"
        val capture = InstrumentationRegistry.getArguments().getString("captureSectorMotion") == "true"
        val recording = if (capture) instrumentation.uiAutomation.executeShellCommand(
            "screenrecord --size 720x1280 --bit-rate 3M --time-limit 6 /data/local/tmp/sector-transition-$mode.mp4"
        ) else null
        fun advance(ms: Long) {
            if (!capture) compose.mainClock.advanceTimeBy(ms)
            else repeat((ms / 16).toInt()) {
                compose.mainClock.advanceTimeByFrame()
                SystemClock.sleep(16)
            }
        }
        compose.mainClock.autoAdvance = false
        try {
            if (capture) SystemClock.sleep(420)
            sector.performTouchInput { click() }
            compose.mainClock.advanceTimeByFrame()
            val origin = detail.fetchSemanticsNode().boundsInRoot
            assertTrue("Detail starts at the ring's selected sector", origin.contains(sectorLabel.center))
            assertTrue("Sector click must not jump to the lower preview", origin.top < previewBounds.top - 16f)
            advance(96)
            val mid = detail.fetchSemanticsNode().boundsInRoot
            assertTrue("Sector outline expands toward the full detail", mid.width > origin.width && mid.top < origin.top)
            if (capture) shot("$mode-expanding")
            advance(880)
            compose.onNodeWithTag("product-inventory-detail").assertIsDisplayed()
            if (capture) { shot("$mode-detail"); SystemClock.sleep(500) }
            compose.onNodeWithTag("inventory-detail-close").performClick()
            advance(304)
            val returning = detail.fetchSemanticsNode().boundsInRoot
            assertTrue("Closing returns to the sector, above the lower preview", returning.top < previewBounds.top)
            assertTrue("Closing narrows the detail toward the source sector", returning.width < mid.width + (origin.width - mid.width) * .1f)
            advance(640)
        } finally {
            compose.mainClock.autoAdvance = true
            recording?.let { ParcelFileDescriptor.AutoCloseInputStream(it).use { stream -> stream.readBytes() } }
        }
        detail.assertDoesNotExist()
        sector.assertIsSelected()
        assertTrue(abs(sector.fetchSemanticsNode().boundsInRoot.top - sectorLabel.top) < 2f)

        preview.performClick()
        compose.onNodeWithTag("product-inventory-detail").assertIsDisplayed()
        compose.onNodeWithTag("inventory-detail-close").performClick()
        detail.assertDoesNotExist()
    }

    private fun shot(name: String) {
        android.os.SystemClock.sleep(200)
        val folder = context.cacheDir.resolve("inventory-sector-transition").apply { mkdirs() }
        val image = instrumentation.uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }
}
