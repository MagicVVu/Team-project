package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.data.*
import org.junit.Assert.*
import org.junit.Before
import org.junit.After
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class InventoryStoreTest {
    private val context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
            super.getSharedPreferences("inventory_store_test_$name", mode)
    }
    @Before fun setup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    @Test fun purchasingUsesActualAmountAndPersistsAcrossInstances() {
        val store = InventoryStore(context)
        val item = StockItem(name = "测试牛奶", quantity = 1.0, unit = "盒", minimum = 3.0)
        store.saveItem(item)
        assertFalse(store.plan(item.id, 2.0)); assertTrue(store.plan(item.id, 4.0))
        assertEquals(1, store.purchases.size); assertEquals(1.0, store.items.single().quantity, 0.0)
        store.receive(item.id, 1.0)
        assertEquals(2, store.items.size); assertTrue(store.items.all { it.quantity == 1.0 }); assertTrue(store.purchases.isEmpty())
        assertTrue(runCatching { store.receive(item.id, 1.0) }.isFailure)
        val restored = InventoryStore(context)
        assertEquals(2, restored.items.size); assertTrue(restored.items.all { it.individualRecord })
        assertTrue(restored.items.all { it.history.isNotEmpty() })
    }
    @Test fun unreadableDataIsPreservedUntilExplicitClear() {
        context.getSharedPreferences("magicvvu_v1", 0).edit().putString("state", "invalid-json-original").commit()
        val store = InventoryStore(context)
        assertNotNull(store.storageError)
        assertEquals("invalid-json-original", store.export())
        store.clear()
        assertNull(store.storageError)
        assertTrue(InventoryStore(context).items.isEmpty())
    }
    @Test fun repeatedIntakesPersistSeparateObjectsAndUseOnlyTheSelectedObject() {
        val store = InventoryStore(context)
        val item = StockItem(name = "苹果", quantity = 10.0, unit = "个")
        store.saveItem(item)
        store.saveItem(item.copy(id = "red-intake", name = "红苹果", quantity = 12.0))
        assertEquals(22, store.items.size)
        assertEquals(22, localInventoryProducts(store.items).single().count)
        assertTrue(runCatching { store.changeQuantity(item.id, -2.0) }.isFailure)
        store.changeQuantity(item.id, -1.0)
        val restored = InventoryStore(context)
        assertEquals(21, localInventoryProducts(restored.items).single().count)
        assertEquals(1, restored.items.count { it.lifecycleStatus == "FINISHED" })
        assertEquals(22, restored.items.map { it.id }.distinct().size)
        assertFalse(restored.export().contains("\"quantity\""))
    }
    @Test fun cloudRecordHasNoAmountAndLegacyAmountsCannotInflateItsCount() {
        val json = org.json.JSONObject().put("id", "object-one").put("name", "牛奶").put("unit", "份")
            .put("status", "ACTIVE").put("version", 1).put("specification", "500ml")
        val item = json.toStock()
        assertEquals(1.0, item.quantity, 0.0)
        assertEquals("500ml", item.specification)
        assertTrue(item.individualRecord)
        assertFalse(item.copy(minimum = 5.0).status(3).low)
        assertEquals(1.0, json.put("quantity", "500").toStock().quantity, 0.0)
        assertEquals(0.0, json.put("status", "FINISHED").toStock().quantity, 0.0)
    }
}
