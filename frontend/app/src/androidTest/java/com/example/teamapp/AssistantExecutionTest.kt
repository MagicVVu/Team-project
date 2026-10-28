package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.net.SocketTimeoutException
import java.util.UUID

/** Real emulator -> localhost SSH -> stage-3 PostgreSQL, with transport loss injected at its boundary. */
@RunWith(AndroidJUnit4::class)
class AssistantExecutionTest {
    private val args get() = InstrumentationRegistry.getArguments()
    private fun context(): Context {
        val prefix = "p4_${UUID.randomUUID()}_"
        return object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
    }
    private suspend fun login(ctx: Context): CloudStore {
        val url = args.getString("executionTestUrl").orEmpty()
        assumeTrue("Explicit isolated fixture required", url.isNotBlank() && !args.getString("fixturePhone").isNullOrBlank())
        val health = CloudApi(url).request("GET", "/api/v1/health")
        assertEquals("0.9.0", health.getString("version")); assertTrue(health.getBoolean("isolated_test"))
        return CloudStore(ctx).apply {
            login(url, args.getString("fixturePhone")!!, args.getString("fixturePassword")!!)
            selectHousehold(args.getString("fixtureHousehold")!!)
            assistant.connectAndRecover()
            assertEquals("draft-execution-1", JSONObject(assistant.capabilities).getString("protocol_version"))
        }
    }
    private fun api(cloud: CloudStore) = cloud.account!!.let { CloudApi(it.address, it.token) }
    private fun paper(cloud: CloudStore) = cloud.items.single { it.name == "纸巾" }
    private suspend fun draft(a: AssistantStore, text: String): AssistantEntry {
        a.send(text)
        return a.entries.last().also { assertEquals(a.error, AssistantStatus.PENDING, it.state) }
    }
    private fun committed(a: AssistantStore, id: String): AssistantEntry = a.entries.single { it.requestId == id }.also {
        assertEquals(a.error, AssistantStatus.COMMITTED, it.state)
        assertEquals("committed", JSONObject(it.receipt).getString("status"))
        assertFalse("Refresh parses both old message history and new event history", it.refreshNeeded)
    }
    @Test fun realFourActionsClarificationCancellationOwnershipAndVersion() = runBlocking {
        val ctx = context(); val cloud = login(ctx); val a = cloud.assistant
        val start = paper(cloud).quantity
        a.send("纸巾还有多少")
        assertEquals(AssistantStatus.ANSWERED, a.entries.last().state)
        assertTrue(a.entries.last().reply.contains("纸巾")); assertTrue(a.entries.last().draftId.isBlank())
        val beforeAdd = cloud.items.map { it.id to it.quantity }
        var e = draft(a, "添加2袋饼干")
        cloud.refresh(); assertEquals(beforeAdd, cloud.items.map { it.id to it.quantity })
        a.edit(e.requestId, "location", "储物柜"); a.confirm(e.requestId)
        e = committed(a, e.requestId)
        assertEquals(2.0, cloud.items.single { it.id == JSONObject(e.receipt).getJSONObject("result").getJSONObject("inventory_item").getString("id") }.quantity, 0.0)
        val destination = if (paper(cloud).location == "储藏室") "书房" else "储藏室"
        val move = draft(a, "把纸巾移到$destination"); a.confirm(move.requestId); committed(a, move.requestId)
        assertEquals(destination, paper(cloud).location); assertEquals(start, paper(cloud).quantity, 0.0)
        val consume = draft(a, "纸巾消耗1包"); a.confirm(consume.requestId); val done = committed(a, consume.requestId)
        assertEquals(start - 1, paper(cloud).quantity, 0.0)
        assertFalse(done.refreshNeeded)
        val events = api(cloud).request("GET", "/api/v1/households/${cloud.account!!.householdId}/consumption-events").getJSONArray("items")
        assertTrue((0 until events.length()).any { events.getJSONObject(it).getString("operation_id") == done.operationId && events.getJSONObject(it).getString("event_type") == "Consumed" })
        val plan = draft(a, "采购清单加2包纸巾"); a.confirm(plan.requestId); val planned = committed(a, plan.requestId)
        val shoppingId = JSONObject(planned.receipt).getJSONObject("result").getJSONObject("shopping_item").getString("id")
        assertTrue(cloud.shopping.any { it.id == shoppingId && it.quantity == 2.0 && !it.purchased })
        assertFalse(JSONObject(planned.receipt).getBoolean("inventory_written"))
        val cancel = draft(a, "纸巾消耗1包"); val quantity = paper(cloud).quantity
        a.cancel(cancel.requestId); assertEquals(AssistantStatus.CANCELLED, a.entries.last().state)
        a.confirm(cancel.requestId); cloud.refresh(); assertEquals(quantity, paper(cloud).quantity, 0.0)
        a.send("牛奶消耗1盒")
        val clarify = a.entries.last(); assertEquals(a.error, AssistantStatus.CLARIFICATION, clarify.state)
        assertEquals(2, clarify.candidates.size)
        val selected = clarify.candidates[1]; val batch = selected.optString("batch_id").ifBlank { selected.getString("id") }
        a.clarify(clarify.requestId, mapOf("batch_id" to batch))
        val clarified = a.entries.last(); assertEquals(clarify.taskId, clarified.taskId)
        // The actual gateway may keep task revision when the next result has no clarification context.
        assertTrue(clarified.taskRevision >= clarify.taskRevision); assertEquals(batch, clarified.command.getString("batch_id"))
        assertEquals(clarified.taskRevision, clarified.executionJson.getInt("task_revision"))
        assertEquals(AssistantStatus.PENDING, clarified.state)
        a.cancel(clarified.requestId)
        for (words in listOf("纸巾昨天开封", "把纸巾全部丢弃", "买2包纸巾")) {
            a.send(words); assertEquals(a.error, AssistantStatus.UNSUPPORTED, a.entries.last().state)
            assertTrue(a.entries.last().receipt.isBlank())
        }
        val stale = draft(a, "纸巾消耗1包")
        val p = paper(cloud)
        api(cloud).request("PATCH", "/api/v1/households/${cloud.account!!.householdId}/inventory-items/${p.id}",
            JSONObject().put("expected_version", p.version).put("operation_id", UUID.randomUUID().toString()).put("storage_location", "书房"))
        a.confirm(stale.requestId); assertEquals(AssistantStatus.CONFLICT, a.entries.last().state)
        a.recover(stale.requestId); assertEquals(AssistantStatus.CONFLICT, a.entries.last().state)
        val other = CloudApi(cloud.account!!.address).login(args.getString("fixtureOtherPhone")!!, args.getString("fixturePassword")!!)
        val failure = runCatching { CloudApi(other.address, other.token).request("GET", "/api/v1/drafts/${stale.draftId}/execution") }.exceptionOrNull()
        assertTrue(failure is CloudFailure && failure.status == 404)
        val foreignCommit = runCatching { CloudApi(other.address, other.token).request("POST", "/api/v1/drafts/${stale.draftId}/commit",
            JSONObject().put("operation_id", UUID.randomUUID().toString()).put("draft_revision", stale.draftRevision).put("task_revision", stale.taskRevision).put("edits", JSONObject())) }.exceptionOrNull()
        assertTrue(foreignCommit is CloudFailure && foreignCommit.status == 404)
        val home = cloud.account!!.householdId
        cloud.selectHousehold(args.getString("fixtureSecondHousehold")!!); a.bind(); assertTrue(a.entries.isEmpty())
        a.confirm(stale.requestId); cloud.selectHousehold(home); a.bind()
        assertTrue(a.entries.any { it.requestId == stale.requestId })
        val beforeLogout = ctx.getSharedPreferences("mewstow_assistant_v1", 0).all.toMap()
        cloud.logout(); a.bind(); assertTrue(a.entries.isEmpty())
        assertEquals("Logout detaches identity without deleting durable requests", beforeLogout, ctx.getSharedPreferences("mewstow_assistant_v1", 0).all)
        val restored = login(ctx)
        assertTrue(restored.assistant.entries.any { it.requestId == stale.requestId })
        restored.logout()
    }
    @Test fun lostSuccessfulResponseRestoresAfterStoreAndCredentialRecreation() = runBlocking {
        val ctx = context(); val cloud = login(ctx)
        val a = AssistantStore(ctx, cloud, clientFactory = { account -> object : AgentClient(account.address, account.token) {
            override suspend fun commit(id: String, body: JSONObject): JSONObject {
                super.commit(id, body) // Real transaction committed; simulate losing the response.
                throw SocketTimeoutException("Synthetic response loss")
            }
        } })
        a.bind(); val before = paper(cloud).quantity
        val draft = draft(a, "纸巾消耗1包"); a.confirm(draft.requestId)
        val uncertain = a.entries.last(); assertEquals(AssistantStatus.UNKNOWN, uncertain.state)
        val originalBody = uncertain.commitBody; val originalId = uncertain.operationId
        assertTrue(originalId.isNotBlank())
        val restored = CloudStore(ctx); assertTrue(restored.signedIn)
        restored.assistant.connectAndRecover()
        val done = committed(restored.assistant, draft.requestId)
        assertEquals(originalBody, done.commitBody); assertEquals(originalId, done.operationId)
        assertEquals(before - 1, paper(restored).quantity, 0.0)
        restored.assistant.retryCommit(draft.requestId); assertEquals(before - 1, paper(restored).quantity, 0.0)
        assertFalse(ctx.getSharedPreferences("mewstow_assistant_v1", 0).all.values.joinToString().contains(restored.account!!.token))
        restored.logout()
    }
    @Test fun timeoutBeforeSendAnd404KeepOriginalOperationAndExactBody() = runBlocking {
        val ctx = context(); val cloud = login(ctx)
        var first = true
        val a = AssistantStore(ctx, cloud, clientFactory = { account -> object : AgentClient(account.address, account.token) {
            override suspend fun commit(id: String, body: JSONObject): JSONObject {
                if (first) { first = false; throw SocketTimeoutException("Synthetic connection loss") }
                return super.commit(id, body)
            }
        } })
        a.bind(); val before = paper(cloud).quantity
        val draft = draft(a, "纸巾消耗1包"); a.confirm(draft.requestId)
        val original = a.entries.last().commitBody
        a.recover(draft.requestId) // Real operation GET returns 404, draft is pending.
        assertEquals(AssistantStatus.UNKNOWN, a.entries.last().state); assertEquals(original, a.entries.last().commitBody)
        cloud.refresh(); assertEquals(before, paper(cloud).quantity, 0.0)
        a.retryCommit(draft.requestId); val done = committed(a, draft.requestId)
        assertEquals(original, done.commitBody); assertEquals(before - 1, paper(cloud).quantity, 0.0)
        a.retryCommit(draft.requestId); assertEquals(before - 1, paper(cloud).quantity, 0.0)
        cloud.logout()
    }
    @Test fun committedReceiptSurvivesRefreshFailureAndConcurrentConfirm() = runBlocking {
        val ctx = context(); val cloud = login(ctx)
        val a = AssistantStore(ctx, cloud, refreshHousehold = { throw java.io.IOException("Synthetic refresh outage") })
        a.bind(); val before = paper(cloud).quantity
        val draft = draft(a, "纸巾消耗1包")
        coroutineScope { repeat(4) { launch { a.confirm(draft.requestId) } } }
        val done = a.entries.last()
        assertEquals(AssistantStatus.COMMITTED, done.state); assertTrue(done.refreshNeeded)
        assertTrue(done.receipt.isNotBlank()); assertTrue(done.notice.isNotBlank())
        val restored = CloudStore(ctx); restored.assistant.connectAndRecover()
        val confirmed = committed(restored.assistant, draft.requestId)
        assertEquals(done.commitBody, confirmed.commitBody); assertEquals(before - 1, paper(restored).quantity, 0.0)
        restored.logout()
    }
    @Test fun explicitServerRejectionIsFailedAndNeverBecomesRetryableUnknown() = runBlocking {
        val ctx = context(); val cloud = login(ctx); val a = cloud.assistant
        val before = paper(cloud).quantity
        val draft = draft(a, "纸巾消耗1包")
        a.edit(draft.requestId, "unit", "袋") // Different package units must be rejected by the authority.
        a.confirm(draft.requestId)
        val rejected = a.entries.last()
        assertEquals(AssistantStatus.FAILED, rejected.state); assertEquals("UNIT_MISMATCH", rejected.errorCode)
        val restored = CloudStore(ctx); restored.assistant.connectAndRecover()
        assertEquals(AssistantStatus.FAILED, restored.assistant.entries.last().state)
        assertEquals("UNIT_MISMATCH", restored.assistant.entries.last().errorCode)
        val offline = AssistantStore(ctx, restored, clientFactory = { throw java.io.IOException("Synthetic offline recovery") })
        offline.bind(); offline.recover(draft.requestId)
        assertEquals(AssistantStatus.FAILED, offline.entries.last().state)
        assertEquals("UNIT_MISMATCH", offline.entries.last().errorCode)
        restored.assistant.retryCommit(draft.requestId)
        restored.refresh(); assertEquals(before, paper(restored).quantity, 0.0)
        assertEquals(rejected.commitBody, restored.assistant.entries.last().commitBody)
        restored.logout()
    }
}
