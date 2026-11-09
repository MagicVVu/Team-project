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
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.util.UUID

class InventoryMotionFeedbackTest {
    @get:Rule val compose = createComposeRule()
    private val base = InstrumentationRegistry.getInstrumentation().targetContext
    private val prefix = "inventory_motion_${UUID.randomUUID()}_"
    private val preferences = mutableSetOf<String>()
    private val context = object : ContextWrapper(base) {
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
            val isolatedName = prefix + name
            preferences += isolatedName
            return super.getSharedPreferences(isolatedName, mode)
        }
    }

    @After fun cleanup() {
        preferences.forEach { base.getSharedPreferences(it, 0).edit().clear().commit() }
    }

    @Test fun lightSaveShowsTheCheckOnlyAfterSuccessfulAdd() = checkAdd(dark = false)
    @Test fun darkSaveShowsTheCheckOnlyAfterSuccessfulAdd() = checkAdd(dark = true)

    private fun checkAdd(dark: Boolean) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val capture = InstrumentationRegistry.getArguments().getString("captureInventoryMotion") == "true"
        val store = InventoryStore(context)
        store.updateLanguage("zh-CN")
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
        val mode = if (dark) "dark" else "light"
        val recording = if (capture) instrumentation.uiAutomation.executeShellCommand(
            "screenrecord --size 720x1280 --bit-rate 3M --time-limit 12 /data/local/tmp/inventory-next-motion-$mode.mp4"
        ) else null
        try {
            if (capture) SystemClock.sleep(450)
            checkForm(store, capture)
            if (capture) {
                SystemClock.sleep(350)
                val bitmap = instrumentation.uiAutomation.takeScreenshot()
                val folder = context.cacheDir.resolve("inventory-motion-review").apply { mkdirs() }
                folder.resolve("saved-$mode.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                bitmap.recycle()
            }
            checkBrowse(store, capture)
        } finally {
            recording?.let { ParcelFileDescriptor.AutoCloseInputStream(it).use { stream -> stream.readBytes() } }
        }
    }

    private fun checkForm(store: InventoryStore, capture: Boolean) {
        press(compose.onNodeWithTag("ring-add"), capture)
        val save = compose.onNodeWithTag("inventory-editor-confirm")
        if (!capture) {
            save.performScrollTo().performClick()
            compose.onNodeWithText("请填写物品名称").assertExists()
            compose.onNodeWithTag("inventory-saved-notice").assertDoesNotExist()
            compose.onNodeWithTag("ring-arrival").assertDoesNotExist()
            compose.runOnIdle { assertEquals(0, store.items.size) }
        }

        compose.onNode(hasSetTextAction() and hasText("物品名称", substring = true)).performScrollTo().performTextInput("青苹果")
        compose.onNode(hasSetTextAction() and hasText("数量", substring = true)).performScrollTo().performTextInput("1")
        save.performScrollTo()
        val arrival = compose.onNodeWithTag("ring-arrival")
        compose.mainClock.autoAdvance = false
        try {
            save.performTouchInput { down(center) }
            advanceFrames(8, capture)
            save.performTouchInput { up() }
            for (frame in 0 until 55) {
                if (compose.onAllNodesWithTag("ring-arrival").fetchSemanticsNodes().isNotEmpty()) break
                advanceFrames(1, capture)
            }
            arrival.assertExists()
            save.assertDoesNotExist()
            advanceFrames(47, capture)
            arrival.assertDoesNotExist()
        } finally {
            compose.mainClock.autoAdvance = true
        }
        compose.onNodeWithTag("inventory-saved-notice").assertIsDisplayed()
        compose.onNodeWithText("已保存").assertIsDisplayed()
        compose.runOnIdle { assertEquals("青苹果", store.items.single().name) }
    }

    private fun checkBrowse(store: InventoryStore, capture: Boolean) {
        compose.runOnIdle {
            store.saveItem(StockItem(name = "香蕉", quantity = 1.0, unit = "件"))
            store.saveItem(StockItem(name = "纸巾", quantity = 1.0, unit = "件", category = "日用品"))
        }
        val count = compose.onNodeWithTag("ring-position")
        count.assertTextEquals("1 / 3")
        press(compose.onNodeWithTag("ring-next"), capture)
        count.assertTextEquals("2 / 3")
        press(compose.onNodeWithTag("ring-category-日用品"), capture)
        count.assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-next").assertIsNotEnabled()
        press(compose.onNodeWithTag("ring-category-其他"), capture)
        count.assertTextEquals("0 / 0")
        press(compose.onNodeWithTag("ring-empty-action"), capture)
        count.assertTextEquals("1 / 3")
    }

    private fun advanceFrames(count: Int, capture: Boolean) {
        repeat(count) {
            compose.mainClock.advanceTimeByFrame()
            if (capture) SystemClock.sleep(18)
        }
    }

    private fun press(button: SemanticsNodeInteraction, capture: Boolean) {
        if (!capture) { button.performTouchInput { click() }; return }
        // Pace only the opt-in preview against the real display recorder.
        compose.mainClock.autoAdvance = false
        try {
            button.performTouchInput { down(center) }
            advanceFrames(8, capture)
            button.performTouchInput { up() }
            advanceFrames(34, capture)
        } finally {
            compose.mainClock.autoAdvance = true
        }
    }
}
