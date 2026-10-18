package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/** Real Android HTTP/Keystore + isolated SSH/PostgreSQL service. Never runs on production. */
@RunWith(AndroidJUnit4::class)
class CloudIntegrationTest {
    @Test fun realCloudFlowPreservesGuestAndSharesIndependentPurchaseBatches() = runBlocking {
        val url = InstrumentationRegistry.getArguments().getString("cloudTestUrl").orEmpty()
        assumeTrue("Requires an explicitly configured isolated service", url.isNotEmpty())
        assertTrue("Refusing to write to a non-test server", CloudApi(url).request("GET", "/api/v1/health").getBoolean("isolated_test"))
        val prefix = "cloud_integration_${UUID.randomUUID()}_"
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        fun isolatedContext(suffix: String) = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + suffix + name, mode)
        }
        val context = isolatedContext("owner")
        val otherContext = isolatedContext("member")
        val store = InventoryStore(context)
        val second = InventoryStore(otherContext)
        val guest = StockItem(name="独立游客牛奶", quantity=7.0, unit="盒")
        store.saveItem(guest); store.plan(guest.id, 2.0)
        val localBefore = context.getSharedPreferences("magicvvu_v1", 0).getString("state", null)
        val suffix = System.currentTimeMillis().toString().takeLast(9)
        val fixture = InstrumentationRegistry.getArguments()
        val preseeded = !fixture.getString("legacyPhone").isNullOrBlank()
        val phoneA = fixture.getString("legacyPhone") ?: "+1999${suffix}1"
        val phoneB = fixture.getString("legacyOtherPhone") ?: "+1999${suffix}2"
        val password = if (preseeded) fixture.getString("fixturePassword")!! else UUID.randomUUID().toString()
        try {
            store.cloud.login(url, phoneA, password, if (preseeded) null else "Android owner")
            assertTrue(store.cloud.signedIn)
            assertTrue(store.items.isEmpty())
            store.cloud.createHousehold("Android 联调 $suffix")
            val firstHome = store.cloud.account!!.householdId
            val milk = StockItem(name="联调牛奶", quantity=4.5, unit="盒", minimum=6.0, location="冰箱", expiry="2027-01-01")
            store.saveItemSynced(milk, null)
            assertEquals(milk.id, store.items.single().id)
            assertEquals(6.0, store.items.single().minimum, 0.0)
            // Replaying a client-generated item ID never creates a second batch.
            store.saveItemSynced(milk, null)
            assertEquals(1, store.items.size)
            val stale = store.items.single()
            val token = store.cloud.account!!.token
            val envelope = context.getSharedPreferences("magicvvu_cloud_credentials", 0).getString("session", "")!!
            assertFalse(envelope.contains(token)); assertFalse(envelope.contains(password)); assertFalse(envelope.contains(phoneA))
            val restored = InventoryStore(context)
            assertEquals(firstHome, restored.cloud.account!!.householdId)
            assertEquals(milk.id, restored.items.single().id)
            second.cloud.login(url, phoneB, password, if (preseeded) null else "Android member")
            second.cloud.joinHousehold(store.cloud.invitation())
            assertEquals(milk.id, second.items.single().id)
            val operationId = UUID.randomUUID().toString()
            val before = second.items.single()
            second.changeQuantitySynced(before, -1.25, operationId)
            second.changeQuantitySynced(before, -1.25, operationId)
            assertEquals(3.25, second.items.single().quantity, 0.0)
            val conflict = runCatching { store.changeQuantitySynced(stale, -1.0, UUID.randomUUID().toString()) }.exceptionOrNull()
            assertTrue(conflict is CloudFailure && conflict.status == 409)
            store.cloud.refresh()
            assertEquals(3.25, store.items.single().quantity, 0.0)
            store.planSynced(store.items.single(), 2.0, UUID.randomUUID().toString())
            second.cloud.refresh()
            val pending = second.cloud.shopping.single { !it.purchased }
            second.cloud.purchase(pending.id, 1.5, "厨房", "2027-02-01")
            second.cloud.purchase(pending.id, 1.5, "厨房", "2027-02-01")
            assertEquals(2, second.items.size)
            assertEquals(4.75, second.items.sumOf { it.quantity }, 0.0)
            assertTrue(second.purchases.isEmpty())
            assertTrue(second.cloud.shopping.single().purchased)
            assertEquals(1.5, second.cloud.shopping.single().quantity, 0.0)
            store.cloud.refresh()
            assertEquals(2, store.items.size)
            val answer = store.cloud.ask("库存有什么")
            assertTrue(answer.contains("牛奶"))
            store.cloud.createHousehold("Android 空家庭 $suffix")
            assertTrue(store.items.isEmpty()); assertTrue(store.purchases.isEmpty())
            store.cloud.selectHousehold(firstHome)
            assertEquals(2, store.items.size)
            assertEquals(2, store.cloud.households.size)
            assertEquals(localBefore, context.getSharedPreferences("magicvvu_v1", 0).getString("state", null))
            second.cloud.logout()
            store.cloud.logout()
            assertEquals(guest.id, store.items.single().id)
            assertEquals(7.0, store.items.single().quantity, 0.0)
            assertEquals(2.0, store.purchases.single().quantity, 0.0)
            assertFalse(InventoryStore(context).cloud.signedIn)
            // Server-side logout actually revokes the opaque token.
            val expired = runCatching { CloudApi(url, token).request("GET", "/api/v1/users/me") }.exceptionOrNull()
            assertTrue(expired is CloudFailure && expired.status == 401)
        } finally {
            runCatching { store.cloud.logout() }; runCatching { second.cloud.logout() }
            for (ctx in listOf(context, otherContext)) for (name in listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")) ctx.getSharedPreferences(name, 0).edit().clear().commit()
        }
    }
}
