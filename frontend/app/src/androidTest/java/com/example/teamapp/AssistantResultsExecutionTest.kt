package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.UUID

internal fun resultContext(): Context {
    val prefix = "results_${UUID.randomUUID()}_"
    return object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix+name, mode)
    }
}

internal class ResultsFixture {
    val context = resultContext()
    val remote = ResultAgent()
    init { CloudCredentials(context).save(CloudAccount(BuildConfig.CLOUD_API_URL, "offline-results-token", ResultAgent.USER, "测试", ResultAgent.HOME)) }
    val cloud = CloudStore(context)
    fun store(refresh: suspend () -> Unit = {}) = AssistantStore(context, cloud, { remote }, refresh)
}

@RunWith(AndroidJUnit4::class)
class AssistantResultsExecutionTest {
    @Test fun verifiedResultsIncludeEvidenceAndDeduplicateWithoutReadingActiveDraft() {
        val result = JSONObject().put("intent", "QUERY_FORECAST").put("forecast", JSONArray())
        val response = JSONObject().put("task", JSONObject().put("result", JSONObject().put("forecast", JSONArray()).put("intent", "QUERY_FORECAST")))
            .put("active_task", JSONObject().put("task", JSONObject().put("result", JSONObject().put("should_not_render", true))))
            .put("evidence", JSONArray().put(JSONObject().put("kind", "verified_calculation").put("result", result))
                .put(JSONObject().put("kind", "verified_calculation").put("result", productResult()))
                .put(JSONObject().put("kind", "unverified").put("result", JSONObject().put("fake", true))))
        val entry = AssistantEntry("one", "{}", task = JSONObject().put("result", result).toString(), conversationResponse = response.toString())
        assertEquals(2, entry.structuredResults.size)
        assertFalse(entry.structuredResults.any { it.has("fake") || it.has("should_not_render") })
        assertEquals(entry.structuredResults.map { it.toString() }, AssistantEntry.fromJson(entry.toJson()).structuredResults.map { it.toString() })
    }

    @Test fun readOnlyPlanningEvidenceDoesNotChangeManualDraftExecutionPolicy() {
        val entry = AssistantEntry("one", "{}", task = JSONObject().put("result", JSONObject().put("intent", "MOVE")).toString(),
            conversationResponse = JSONObject().put("evidence", JSONArray().put(JSONObject().put("kind", "verified_calculation")
                .put("result", JSONObject().put("intent", "SUGGEST_PURCHASE").put("planning_basis", JSONObject())))).toString())
        assertFalse(entry.automaticPlan)
        assertEquals(2, entry.structuredResults.size)
        assertTrue(entry.structuredResults[1].has("planning_basis"))
    }

    @Test fun lostCommitResponseIsRecoveredByReceiptWithoutAnotherCommit() = runBlocking {
        val f = ResultsFixture(); val s = f.store(); s.connectAndRecover()
        f.remote.loseAfterCommit = true
        s.confirm(s.activeRequestId)
        assertEquals(1, f.remote.commits.size); assertEquals(4, f.remote.quantity)
        assertEquals(AssistantStatus.COMMITTED, s.activeEntry!!.state)
        assertTrue(f.remote.calls.indexOf("operation") > f.remote.calls.indexOf("commit"))
    }

    @Test fun sameDraftAcrossMessagesAndRecreationSharesOneOriginalConfirmation() = runBlocking {
        val f = ResultsFixture(); var s = f.store(); s.connectAndRecover()
        f.remote.loseBeforeCommit = true
        val originalId = s.activeRequestId
        s.confirm(originalId)
        val original = f.remote.commits.single()
        assertEquals(AssistantStatus.UNKNOWN, s.activeEntry!!.state)
        s = f.store(); s.connectAndRecover(); s.send("继续核对这份草稿")
        val alias = s.activeRequestId
        assertNotEquals(originalId, alias)
        assertEquals(original, s.entries.single { it.requestId == alias }.commitBody)
        s.confirm(alias)
        assertEquals(1, f.remote.commits.size)
        s.retryCommit(alias)
        assertEquals(listOf(original, original), f.remote.commits)
        assertEquals(4, f.remote.quantity)
        assertTrue(s.entries.filter { it.draftId == ResultAgent.DRAFT }.all { it.receipt.isNotBlank() && it.state == AssistantStatus.COMMITTED })
    }

    @Test fun concurrentConfirmationClicksOnDifferentMessagesDeductOnlyOnce() = runBlocking {
        val f = ResultsFixture(); val s = f.store(); s.connectAndRecover()
        val first = s.activeRequestId; s.send("核对同一份草稿"); val second = s.activeRequestId
        coroutineScope { repeat(4) { index -> launch { s.confirm(if (index % 2 == 0) first else second) } } }
        assertEquals(1, f.remote.commits.size); assertEquals(4, f.remote.quantity)
        assertEquals(AssistantStatus.COMMITTED, s.activeEntry!!.state)
    }

    @Test fun changedDraftCannotReplaceOriginalUncertainConfirmation() = runBlocking {
        val f = ResultsFixture(); val s = f.store(); s.connectAndRecover()
        val id = s.activeRequestId; f.remote.loseBeforeCommit = true; s.confirm(id)
        f.remote.revision = 2
        s.recover(id); s.retryCommit(id)
        assertEquals(1, f.remote.commits.size); assertEquals(6, f.remote.quantity)
        assertTrue(s.error.contains("变化"))
    }

    @Test fun legacyConflictingEnvelopesCanRecoverReceiptsWithoutReplacingEitherOriginal() = runBlocking {
        val f = ResultsFixture(); val s = f.store(); s.connectAndRecover(); s.confirm(s.activeRequestId)
        val original = s.activeEntry!!.copy(transportMode = "legacy", conversationBody = "", conversationResponse = "",
            receipt = "", state = AssistantStatus.UNKNOWN)
        val otherBody = JSONObject(original.commitBody).put("operation_id", UUID.randomUUID().toString()).toString()
        val other = original.copy(requestId = "older-attempt", commitBody = otherBody)
        f.context.getSharedPreferences("mewstow_assistant_v1", 0).edit()
            .putString(f.cloud.scopeKey, JSONArray(listOf(original.toJson(), other.toJson())).toString()).commit()
        val restored = f.store(); restored.bind(); restored.recover(original.requestId)
        assertEquals(AssistantStatus.COMMITTED, restored.entries.first().state)
        assertEquals(AssistantStatus.UNKNOWN, restored.entries.last().state)
        assertEquals(listOf(original.commitBody, otherBody), restored.entries.map { it.commitBody })
        restored.retryCommit(other.requestId)
        assertTrue(restored.error.contains("不同的历史确认")); assertEquals(1, f.remote.commits.size)
    }

    @Test fun tenTurnsKeepConversationRevisionAndDiscardEditsAfterDraftChanges() = runBlocking {
        val f = ResultsFixture(); val s = f.store(); s.connectAndRecover()
        s.edit(s.activeRequestId, "quantity", "4")
        repeat(10) { turn ->
            f.remote.reviseNextTurn = turn == 4
            s.send(if (turn == 4) "改成三盒" else "继续核对第${turn + 1}轮")
            assertTrue(s.error, s.error.isBlank())
            assertEquals(turn + 1, s.conversationRevision)
        }
        assertEquals(10, f.remote.turns); assertEquals(2, s.activeEntry!!.taskRevision)
        assertEquals("3", s.activeEntry!!.command.getString("quantity"))
        assertTrue(s.activeEntry!!.edits.isEmpty()); assertTrue(f.remote.commits.isEmpty())
    }

    @Test fun successfulReceiptRemainsSuccessfulWhenStockRefreshFails() = runBlocking {
        val f = ResultsFixture(); val s = f.store { throw IOException("synthetic refresh outage") }; s.connectAndRecover()
        val id = s.activeRequestId; s.confirm(id); s.recover(id); s.confirm(id)
        val entry = s.entries.single { it.requestId == id }
        assertEquals(AssistantStatus.COMMITTED, entry.state); assertTrue(entry.refreshNeeded)
        assertEquals(1, f.remote.commits.size); assertEquals(4, f.remote.quantity)
    }

    @Test fun suggestionRevalidationShowsStaleAndNeverCommits() = runBlocking {
        val f = ResultsFixture(); f.remote.automatic = true
        val s = f.store(); s.connectAndRecover(); s.revalidatePlanning(s.activeRequestId)
        assertEquals("stale", JSONObject(s.activeEntry!!.planningReview).getString("status"))
        assertEquals(AssistantStatus.UNSUPPORTED, s.activeEntry!!.state)
        assertEquals(1, f.remote.revalidations); assertTrue(f.remote.commits.isEmpty())
    }

    @Test fun forgedRevalidationWriteClaimIsRejected() = runBlocking {
        val f = ResultsFixture(); f.remote.automatic = true; f.remote.forgedReview = true
        val s = f.store(); s.connectAndRecover(); s.revalidatePlanning(s.activeRequestId)
        assertTrue(s.activeEntry!!.planningReview.isBlank()); assertTrue(s.error.isNotBlank())
        assertTrue(f.remote.commits.isEmpty())
    }

    @Test fun expiredCandidateCannotBeSentAsAnotherSelection() = runBlocking {
        val f = ResultsFixture(); f.remote.expired = true
        val s = f.store(); s.connectAndRecover()
        assertTrue(s.activeEntry!!.clarificationExpired)
        assertTrue(runCatching { s.clarify(s.activeRequestId, mapOf("batch_id" to ResultAgent.BATCH)) }.isFailure)
        assertEquals(0, f.remote.turns)
    }

    @Test fun receiptFromAnotherHouseholdCannotBecomeSuccess() = runBlocking {
        val f = ResultsFixture(); f.remote.forgedReceipt = true
        val s = f.store(); s.connectAndRecover(); s.confirm(s.activeRequestId)
        assertNotEquals(AssistantStatus.COMMITTED, s.activeEntry!!.state)
        assertTrue(s.activeEntry!!.receipt.isBlank()); assertEquals(1, f.remote.commits.size)
    }

    companion object {
        fun productResult(): JSONObject {
            val batch = JSONObject().put("batch_id", ResultAgent.BATCH).put("quantity", "6").put("unit", "盒").put("location", "冷藏室")
                .put("label_expiry", JSONObject.NULL).put("status", "ACTIVE").put("version", 2)
            val product = JSONObject().put("product_id", ResultAgent.PRODUCT).put("name", "测试牛奶").put("base_unit", "盒")
                .put("total_quantity", "6").put("nonexpired_active_quantity", "6").put("usable_quantity", JSONObject.NULL)
                .put("batches", JSONArray().put(batch))
            return JSONObject().put("product_planning", JSONArray().put(JSONObject().put("product", product)
                .put("recorded_consumption_quantity", "0").put("pending_quantity", JSONObject.NULL)
                .put("remaining_days", JSONObject.NULL).put("suggested_quantity", JSONObject.NULL)
                .put("reason_codes", JSONArray().put("PRODUCT_USABLE_QUANTITY_UNKNOWN").put("PRODUCT_COVERAGE_UNKNOWN"))))
                .put("planning_context", JSONObject().put("pending_state", "association_unknown").put("pending_count", 2))
                .put("data_gaps", JSONArray().put("PENDING_ASSOCIATION_UNKNOWN"))
        }
    }
}

internal class ResultAgent : AgentClient(BuildConfig.CLOUD_API_URL, "offline-only") {
    var quantity = 6; var revision = 1; var automatic = false; var expired = false
    var reviseNextTurn = false
    var loseBeforeCommit = false; var loseAfterCommit = false; var forgedReview = false; var forgedReceipt = false
    var turns = 0; var revalidations = 0
    val commits = mutableListOf<String>(); val calls = mutableListOf<String>()
    private var receipt: JSONObject? = null
    private var conversationRevision = 0
    override suspend fun capabilities() = JSONObject().put("conversation_memory_protocol", "conversation-memory-1")
        .put("actions", JSONObject().put("CONSUME", true).put("PLAN_ADD", true))
    private fun command() = JSONObject().put("action", if (automatic) "PLAN_ADD" else "CONSUME").put("name", "测试牛奶")
        .put("batch_id", BATCH).put("expected_version", 2).put("quantity", if (revision == 1) "2" else "3").put("unit", "盒")
    private fun taskPayload(): JSONObject {
        val result = JSONObject().put("draft", command()).put("intent", if (automatic) "SUGGEST_PURCHASE" else "CONSUME")
            .put("clarification", JSONObject().put("allowed_fields", JSONArray().put("batch_id")))
            .put("candidates", JSONArray().put(JSONObject().put("id", BATCH).put("name", "牛奶").put("quantity", "6").put("unit", "盒").put("version", 2)))
        if (automatic) result.put("planning_basis", JSONObject())
        return JSONObject().put("task_id", TASK).put("household_id", HOME).put("revision", revision)
            .put("original_text", "消耗两盒牛奶").put("status", if (expired) "needs_clarification" else "needs_confirmation")
            .put("expires_at", if (expired) "2020-01-01T00:00:00Z" else "2099-01-01T00:00:00Z")
            .put("draft_id", if (expired) JSONObject.NULL else DRAFT).put("result", result)
    }
    override suspend fun currentConversation(householdId: String, cursor: String?) = JSONObject().put("protocol_version", "conversation-memory-1")
        .put("household_id", HOME).put("conversation_id", CONVERSATION).put("conversation_revision", conversationRevision)
        .put("messages", JSONArray()).put("active_task", JSONObject().put("task", taskPayload()))
    override suspend fun conversationTurn(body: JSONObject): JSONObject {
        check(body.getInt("conversation_revision") == conversationRevision)
        check(body.getString("task_id") == TASK && body.getInt("revision") == revision)
        if (reviseNextTurn) { revision++; reviseNextTurn = false }
        turns++; conversationRevision++
        return JSONObject().put("protocol_version", "conversation-memory-1").put("conversation_id", CONVERSATION)
            .put("conversation_revision", conversationRevision).put("current_conversation_revision", conversationRevision)
            .put("request_id", body.getString("request_id")).put("original_text", body.getString("text"))
            .put("reply", "这是原草稿，仍需核对确认。").put("kind", "task").put("inventory_written", false)
            .put("task", taskPayload()).put("active_task", JSONObject().put("task", taskPayload()))
    }
    override suspend fun task(id: String) = taskPayload()
    override suspend fun draft(id: String) = JSONObject().put("revision", revision).put("draft", command())
    override suspend fun execution(id: String) = JSONObject().put("task_id", TASK).put("draft_id", DRAFT).put("task_revision", revision)
        .put("draft_revision", revision).put("status", if (receipt == null) "pending" else "committed")
        .put("editable_fields", JSONArray().put("quantity").put("unit")).also { receipt?.let { r -> it.put("receipt", wireReceipt(r)) } }
    override suspend fun commit(id: String, body: JSONObject): JSONObject {
        calls += "commit"; commits += body.toString()
        if (loseBeforeCommit) { loseBeforeCommit = false; throw SocketTimeoutException("before send") }
        if (receipt == null) {
            quantity -= 2
            receipt = JSONObject().put("protocol_version", "draft-operation-receipt-1").put("status", "committed")
                .put("operation_id", body.getString("operation_id")).put("draft_id", DRAFT).put("task_id", TASK)
                .put("draft_revision", body.getInt("draft_revision")).put("task_revision", body.getInt("task_revision"))
                .put("action", "CONSUME").put("scope", JSONObject().put("user_id", USER).put("household_id", HOME))
                .put("committed_at", "2026-10-29T00:00:00Z").put("result", JSONObject())
        }
        if (loseAfterCommit) { loseAfterCommit = false; throw SocketTimeoutException("after commit") }
        return wireReceipt(receipt!!)
    }
    override suspend fun operation(id: String): JSONObject {
        calls += "operation"
        return receipt?.let(::wireReceipt) ?: throw CloudFailure(404, "not found", "OPERATION_NOT_FOUND")
    }
    private fun wireReceipt(value: JSONObject) = JSONObject(value.toString()).also { if (forgedReceipt) it.getJSONObject("scope").put("household_id", UUID.randomUUID().toString()) }
    override suspend fun planningRevalidation(id: String, body: JSONObject): JSONObject {
        revalidations++
        return JSONObject().put("protocol_version", "planning-revalidation-1").put("draft_id", DRAFT).put("status", "stale")
            .put("inventory_written", forgedReview).put("shopping_written", false).put("automatic_planning_commit", false)
            .put("mismatches", JSONArray().put("inventory_versions")).put("blockers", JSONArray().put("AUTOMATIC_PLANNING_NOT_APPROVED"))
    }
    companion object {
        const val USER = "00000000-0000-4000-8000-000000000001"
        const val HOME = "00000000-0000-4000-8000-000000000002"
        const val TASK = "00000000-0000-4000-8000-000000000003"
        const val DRAFT = "00000000-0000-4000-8000-000000000004"
        const val BATCH = "00000000-0000-4000-8000-000000000005"
        const val PRODUCT = "00000000-0000-4000-8000-000000000006"
        const val CONVERSATION = "00000000-0000-4000-8000-000000000007"
    }
}
