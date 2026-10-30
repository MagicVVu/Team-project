package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.Editor
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*

class InventoryUnitlessEditorTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val prefix = "unitless_${java.util.UUID.randomUUID()}_"
    private val preferences = mutableSetOf<String>()
    private val context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
            preferences += prefix + name
            return super.getSharedPreferences(prefix + name, mode)
        }
    }
    @After fun cleanup() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        preferences.forEach { base.getSharedPreferences(it, 0).edit().clear().commit() }
    }
    private fun show(store: InventoryStore, initial: StockItem? = null, draft: VoiceDraft? = null) {
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme {
            Editor(store, initial, draft = draft, notify = {}, onSaved = {})
        } } }
        compose.onAllNodes(hasSetTextAction() and hasText("单位", substring = true)).assertCountEquals(0)
    }
    @Test fun addingThreeObjectsNeedsNoUnitInput() {
        val store = InventoryStore(context)
        show(store, draft = VoiceDraft("苹果", "3", "盒", "冰箱"))
        compose.onNodeWithTag("inventory-editor-confirm").performScrollTo().performClick()
        compose.waitUntil(5_000) { store.items.size == 3 }
        Assert.assertTrue(store.items.all { it.individualRecord && it.quantity == 1.0 && it.unit == "件" })
        Assert.assertTrue(store.items.all { it.purchasedAt == java.time.LocalDate.now().toString() })
    }
    @Test fun editingDoesNotRequireOrRewriteLegacyUnit() {
        val store = InventoryStore(context)
        store.saveItem(StockItem(name = "牛奶", quantity = 1.0, unit = "瓶", location = "冰箱", purchasedAt = "2026-10-01"))
        val item = store.items.single()
        show(store, initial = item)
        compose.onNodeWithTag("inventory-editor-confirm").performScrollTo().performClick()
        compose.waitForIdle()
        Assert.assertEquals("瓶", store.items.single().unit)
        Assert.assertEquals(item.id, store.items.single().id)
        Assert.assertEquals("2026-10-01", store.items.single().purchasedAt)
    }
    @Test fun measuredVoiceInputBecomesOneObjectWithSpecification() {
        val store = InventoryStore(context)
        show(store, draft = VoiceDraft("肉", "500", "克", "冰箱"))
        compose.onNodeWithTag("inventory-editor-confirm").performScrollTo().performClick()
        compose.waitUntil(5_000) { store.items.isNotEmpty() }
        Assert.assertEquals(1, store.items.size)
        Assert.assertEquals("500克", store.items.single().specification)
    }
}
