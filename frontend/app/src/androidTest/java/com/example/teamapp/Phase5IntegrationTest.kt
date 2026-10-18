package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.SocketTimeoutException
import java.util.UUID

class Phase5IntegrationTest {
    private val args get() = InstrumentationRegistry.getArguments()
    private fun context(): Context {
        val prefix = "p5_${UUID.randomUUID()}_"
        return object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
    }
    private suspend fun cloud(ctx: Context, member: Boolean = false): CloudStore {
        val url = args.getString("executionTestUrl").orEmpty(); assumeTrue(url.isNotBlank())
        return CloudStore(ctx).apply {
            login(url, args.getString(if (member) "fixtureMemberPhone" else "fixturePhone")!!, args.getString("fixturePassword")!!)
            selectHousehold(args.getString("fixtureHousehold")!!)
        }
    }
    @Test fun messageSurvivesOfflineCapabilityPreflight() = runBlocking {
        val ctx = context(); val c = cloud(ctx)
        val a = AssistantStore(ctx, c, clientFactory = { throw java.io.IOException("Synthetic offline before preflight") })
        a.send("纸巾还有多少")
        val original = a.entries.single(); assertEquals(AssistantStatus.UNKNOWN, original.state)
        assertTrue(original.taskId.isBlank())
        val restored = CloudStore(ctx); restored.assistant.bind()
        assertEquals(original.requestBody, restored.assistant.entries.single().requestBody)
        restored.assistant.retryMessage(original.requestId)
        val recovered = restored.assistant.entries.single()
        assertEquals(AssistantStatus.ANSWERED, recovered.state); assertEquals(original.requestId, recovered.requestId)
        assertEquals(original.requestBody, recovered.requestBody); restored.logout()
    }
    @Test fun processedMessageLostResponseReusesOriginalRequest() = runBlocking {
        val ctx = context(); val c = cloud(ctx); var first = true
        val a = AssistantStore(ctx, c, clientFactory = { account -> object : AgentClient(account.address, account.token) {
            override suspend fun message(body: JSONObject): JSONObject {
                val result = super.message(body)
                if (first) { first = false; throw SocketTimeoutException("Synthetic message response loss") }
                return result
            }
        } })
        val before = c.items.map { it.id to it.quantity }
        a.send("纸巾还有多少"); val original = a.entries.single()
        assertEquals(AssistantStatus.UNKNOWN, original.state); assertTrue(original.taskId.isBlank())
        a.retryMessage(original.requestId); val recovered = a.entries.single()
        assertEquals(AssistantStatus.ANSWERED, recovered.state); assertEquals(original.requestBody, recovered.requestBody)
        val account = c.account!!
        val replay = AgentClient(account.address, account.token).message(JSONObject(original.requestBody))
        assertEquals(recovered.taskId, replay.getString("task_id")); c.refresh()
        assertEquals(before, c.items.map { it.id to it.quantity }); c.logout()
    }
    @Test fun twoMembersCompeteForOneVersionWithoutDuplicateConsume() = runBlocking {
        assumeTrue(!args.getString("fixtureMemberPhone").isNullOrBlank())
        val first = cloud(context()); val second = cloud(context(), member = true)
        val before = first.items.single { it.name == "纸巾" }.quantity
        first.assistant.send("纸巾消耗一包。"); second.assistant.send("纸巾消耗一包。")
        val a = first.assistant.entries.last(); val b = second.assistant.entries.last()
        assertEquals(AssistantStatus.PENDING, a.state); assertEquals(AssistantStatus.PENDING, b.state)
        coroutineScope {
            val one = async { first.assistant.confirm(a.requestId) }; val two = async { second.assistant.confirm(b.requestId) }
            one.await(); two.await()
        }
        val results = listOf(first.assistant.entries.last(), second.assistant.entries.last())
        assertEquals(1, results.count { it.state == AssistantStatus.COMMITTED })
        assertEquals(1, results.count { it.state == AssistantStatus.CONFLICT })
        first.refresh(); assertEquals(before - 1, first.items.single { it.name == "纸巾" }.quantity, 0.0)
        val account = first.account!!
        val events = CloudApi(account.address, account.token).request("GET", "/api/v1/households/${account.householdId}/consumption-events").getJSONArray("items")
        val opIds = results.map { it.operationId }
        assertEquals(1, (0 until events.length()).count { events.getJSONObject(it).getString("operation_id") in opIds })
        first.logout(); second.logout()
    }
}
