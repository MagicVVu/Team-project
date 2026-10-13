package com.example.teamapp

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
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    @Before fun setup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    @Test fun purchasingUsesActualAmountAndPersistsAcrossInstances() {
        val store = InventoryStore(context)
        val item = StockItem(name = "测试牛奶", quantity = 1.0, unit = "盒", minimum = 3.0)
        store.saveItem(item)
        assertFalse(store.plan(item.id, 2.0)); assertTrue(store.plan(item.id, 4.0))
        assertEquals(1, store.purchases.size); assertEquals(1.0, store.items.single().quantity, 0.0)
        store.receive(item.id, 1.0)
        assertEquals(2.0, store.items.single().quantity, 0.0); assertTrue(store.purchases.isEmpty())
        assertTrue(runCatching { store.receive(item.id, 1.0) }.isFailure)
        val restored = InventoryStore(context)
        assertEquals(2.0, restored.items.single().quantity, 0.0); assertTrue(restored.items.single().status(3).low)
        assertEquals(2, restored.items.single().history.size)
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
    @Test fun duplicatesRequireConfirmationAndConsumptionCannotGoNegative() {
        val store = InventoryStore(context)
        val item = StockItem(name = "测试鸡蛋", quantity = 2.0, unit = "个")
        store.saveItem(item)
        assertTrue(runCatching { store.saveItem(item.copy(id = "other", quantity = 3.0)) }.isFailure)
        assertEquals(2.0, store.items.single().quantity, 0.0)
        store.saveItem(item.copy(id = "other", quantity = 3.0), "入库")
        assertEquals(5.0, store.items.single().quantity, 0.0)
        store.saveItem(item.copy(id = "other", quantity = 1.0), "盘点")
        assertEquals(1.0, store.items.single().quantity, 0.0)
        assertTrue(runCatching { store.changeQuantity(item.id, -2.0) }.isFailure)
        assertEquals(1.0, store.items.single().quantity, 0.0)
        store.plan(item.id, 2.0); store.deleteItem(item.id)
        assertTrue(store.items.isEmpty()); assertTrue(store.purchases.isEmpty())
    }
}
