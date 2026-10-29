package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.net.SocketTimeoutException
import java.util.UUID

/** All cloud/agent calls are in-memory fixtures; no production credentials or writes. */
@RunWith(AndroidJUnit4::class)
class ConversationFlowTest {
    private lateinit var context: Context
    private lateinit var cloud: CloudStore
    private lateinit var remote: MemoryAgent
    private lateinit var store: AssistantStore
    @Before fun setup() {
        val prefix = "conversation_${UUID.randomUUID()}_"
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix+name, mode)
        }
        CloudCredentials(context).save(CloudAccount(BuildConfig.CLOUD_API_URL, "offline-memory-token", USER, "测试", HOME))
        cloud = CloudStore(context)
        remote = MemoryAgent()
        store = AssistantStore(context, cloud, { remote }, {})
    }

    @Test fun openingRestoresCloudHistoryAndPagesWithoutResetting() = runBlocking {
        remote.earlier = true
        store.connectAndRecover()
        assertEquals(listOf("GET current"), remote.calls)
        assertEquals(CONVERSATION, store.conversationId)
        assertEquals(7, store.conversationRevision)
        assertTrue(store.entries.single().historical)
        store.loadEarlierConversation()
        assertEquals(listOf("earlier", "history"), store.entries.map { it.requestId })
        assertTrue(store.historyCursor.isBlank())
        store.connectAndRecover()
        assertEquals(1, store.entries.count { it.requestId == "history" })
        assertFalse(remote.calls.any { it.startsWith("RESET") })
    }

    @Test fun newConversationResetsOnlyWhenServerRequiresIt() = runBlocking {
        remote.missing = true
        store.connectAndRecover(); store.connectAndRecover()
        assertEquals(1, remote.calls.count { it == "RESET" })
        assertEquals(CONVERSATION, store.conversationId)
    }

    @Test fun sendPersistsOriginalTextAndSelectorsThenAdoptsNewestRevision() = runBlocking {
        store.connectAndRecover(); store.send("  牛奶在哪里？  ")
        assertTrue(store.error.isBlank())
        val body = JSONObject(remote.posts.single())
        assertEquals("  牛奶在哪里？  ", body.getString("text"))
        assertEquals(CONVERSATION, body.getString("conversation_id")); assertEquals(7, body.getInt("conversation_revision"))
        assertEquals(setOf("household_id", "request_id", "conversation_id", "conversation_revision", "text"), body.keys().asSequence().toSet())
        val saved = store.entries.single { it.requestId == body.getString("request_id") }
        assertEquals(remote.posts.single(), saved.conversationBody)
        assertTrue(saved.conversationResolved); assertEquals("本轮回答", saved.reply)
        assertEquals(8, store.conversationRevision)
        assertEquals("p85-dialogue-1", JSONObject(saved.conversationResponse).getJSONObject("dialogue").getString("protocol_version"))
    }

    @Test fun lostReplyQueriesOriginalIdAndNeverPostsTwice() = runBlocking {
        remote.loseReply = true
        store.connectAndRecover(); store.send("原文保持不变")
        assertEquals(1, remote.posts.size)
        val id = JSONObject(remote.posts.single()).getString("request_id")
        assertTrue(remote.calls.contains("GET recovery $id"))
        assertTrue(store.entries.single { it.requestId == id }.conversationResolved)
        assertEquals("本轮回答", store.entries.single { it.requestId == id }.reply)
    }

    @Test fun savedPlanSurvivesStoreRecreationAndOnlyExplicitRecoveryResumesExactBody() = runBlocking {
        remote.loseReply = true; remote.recoveryPhase = "prepared"
        store.connectAndRecover(); store.send("保留这个原请求")
        val body = remote.posts.single(); val id = JSONObject(body).getString("request_id")
        val recreated = AssistantStore(context, cloud, { remote }, {})
        recreated.connectAndRecover()
        assertEquals(1, remote.posts.size)
        assertFalse(recreated.entries.single { it.requestId == id }.conversationResolved)
        recreated.send("不应越过尚未解决的消息")
        assertEquals(1, remote.posts.size)
        remote.loseReply = false
        recreated.recover(id)
        assertEquals(listOf(body, body), remote.posts)
        assertTrue(recreated.entries.single { it.requestId == id }.conversationResolved)
    }

    @Test fun unknownUnderstandingNeverRepostsEvenWhenRecoverIsPressed() = runBlocking {
        remote.loseReply = true; remote.recoveryPhase = "result_unknown"
        store.connectAndRecover(); store.send("这条理解还没有结果")
        val id = JSONObject(remote.posts.single()).getString("request_id")
        store.recover(id)
        assertEquals(1, remote.posts.size)
        assertEquals(AssistantStatus.UNKNOWN, store.entries.single { it.requestId == id }.state)
    }

    @Test fun currentTaskStaysIndependentFromAnUnrelatedReadOnlyTurn() = runBlocking {
        remote.active = true
        store.connectAndRecover()
        val activeId = store.activeEntry!!.taskId
        store.send("顺便查别的物品")
        assertEquals(activeId, store.activeEntry!!.taskId)
        val body = JSONObject(remote.posts.single())
        assertEquals(activeId, body.getString("task_id")); assertEquals(3, body.getInt("revision"))
        assertEquals(AssistantStatus.PENDING, store.activeEntry!!.state)
    }

    @Test fun aNewLoginCanGetRecoverTheSameUserAndHouseholdOutbox() = runBlocking {
        remote.loseReply = true; remote.recoveryPhase = "processing"
        store.connectAndRecover(); store.send("登录后继续查询原请求")
        val id = JSONObject(remote.posts.single()).getString("request_id")
        CloudCredentials(context).save(CloudAccount(BuildConfig.CLOUD_API_URL, "new-offline-memory-token", USER, "测试", HOME))
        val signedInAgain = CloudStore(context)
        remote.recoveryPhase = "completed"
        val restored = AssistantStore(context, signedInAgain, { remote }, {})
        restored.connectAndRecover()
        assertEquals(1, remote.posts.size)
        assertTrue(restored.entries.single { it.requestId == id }.conversationResolved)
        val prefs = context.getSharedPreferences("mewstow_assistant_v1", 0).all.values.joinToString()
        assertFalse(prefs.contains("offline-memory-token"))
    }

    companion object {
        private const val HOME = "00000000-0000-4000-8000-000000000001"
        private const val USER = "00000000-0000-4000-8000-000000000002"
        private const val CONVERSATION = "00000000-0000-4000-8000-000000000003"
        private const val TASK = "00000000-0000-4000-8000-000000000004"
        private const val DRAFT = "00000000-0000-4000-8000-000000000005"
        private const val CURSOR = "00000000-0000-4000-8000-000000000006"
        private const val READ_TASK = "00000000-0000-4000-8000-000000000007"
    }

    private class MemoryAgent : AgentClient(BuildConfig.CLOUD_API_URL, "never-used") {
        val calls = mutableListOf<String>(); val posts = mutableListOf<String>()
        var missing = false; var earlier = false; var active = false; var loseReply = false
        var recoveryPhase = "completed"; private var revision = 7
        private val responses = mutableMapOf<String, JSONObject>()
        override suspend fun capabilities() = JSONObject().put("conversation_memory_protocol", "conversation-memory-1")
            .put("conversation_dialogue_protocol", "p85-dialogue-1").put("actions", JSONObject().put("MOVE", true))
        private fun taskPayload(id: String = TASK) = JSONObject().put("task_id", id).put("household_id", HOME).put("revision", 3)
            .put("original_text", "移动牛奶").put("status", if (id == TASK) "needs_confirmation" else "answered")
            .put("draft_id", if (id == TASK) DRAFT else JSONObject.NULL).put("result", JSONObject())
        private fun activePayload(): Any = if (active) JSONObject().put("task", taskPayload()).put("execution", JSONObject.NULL) else JSONObject.NULL
        override suspend fun currentConversation(householdId: String, cursor: String?): JSONObject {
            assertEquals(HOME, householdId); calls += if (cursor == null) "GET current" else "GET earlier"
            val history = JSONObject().put("request_id", if (cursor == null) "history" else "earlier")
                .put("original_text", "历史问题").put("reply", "历史回答").put("phase", "completed").put("task_id", JSONObject.NULL)
            val messages = if (missing) JSONArray() else JSONArray().put(history)
            if (!missing && cursor == null) responses.values.forEach { response ->
                messages.put(JSONObject().put("request_id", response.getString("request_id"))
                    .put("original_text", response.getString("original_text")).put("reply", response.getString("reply"))
                    .put("phase", if (recoveryPhase == "completed") "completed" else "understood").put("task_id", JSONObject.NULL))
            }
            return JSONObject().put("protocol_version", "conversation-memory-1").put("household_id", HOME)
                .put("conversation_id", if (missing) JSONObject.NULL else CONVERSATION).put("conversation_revision", revision)
                .put("requires_reset", missing).put("messages", messages)
                .put("next_cursor", if (earlier && cursor == null) CURSOR else JSONObject.NULL).put("active_task", activePayload())
        }
        override suspend fun resetConversation(body: JSONObject): JSONObject {
            calls += "RESET"; missing = false; revision = 0
            return JSONObject().put("protocol_version", "conversation-memory-1").put("request_id", body.getString("request_id"))
                .put("conversation_id", CONVERSATION).put("current_conversation_revision", 0).put("inventory_written", false)
        }
        override suspend fun conversationTurn(body: JSONObject): JSONObject {
            calls += "POST turn"; posts += body.toString()
            val id = body.getString("request_id")
            val response = responses.getOrPut(id) {
                revision++
                JSONObject().put("protocol_version", "conversation-memory-1").put("request_id", id)
                    .put("original_text", body.getString("text")).put("conversation_id", CONVERSATION)
                    .put("conversation_revision", revision).put("current_conversation_revision", revision).put("inventory_written", false)
                    .put("reply", "本轮回答").put("kind", "explain").put("task", if (active) taskPayload(READ_TASK) else JSONObject.NULL)
                    .put("active_task", activePayload()).put("model_calls", 1).put("dialogue", JSONObject().put("protocol_version", "p85-dialogue-1"))
            }
            if (loseReply) throw SocketTimeoutException("Synthetic response loss")
            return response
        }
        override suspend fun recoverConversation(requestId: String, householdId: String): JSONObject {
            calls += "GET recovery $requestId"
            val response = responses.getValue(requestId)
            return JSONObject().put("request_id", requestId).put("original_text", response.getString("original_text"))
                .put("phase", recoveryPhase).put("response", if (recoveryPhase == "completed") response else JSONObject.NULL)
        }
        override suspend fun conversation(body: JSONObject): JSONObject = throw AssertionError("New turns must not use the old chat endpoint")
        override suspend fun control(id: String, body: JSONObject): JSONObject = throw AssertionError("Chat must use one conversation turn")
        override suspend fun draft(id: String) = JSONObject().put("revision", 1).put("draft", JSONObject().put("action", "MOVE").put("to_location", "冷藏室"))
        override suspend fun execution(id: String) = JSONObject().put("task_id", TASK).put("draft_id", DRAFT)
            .put("task_revision", 3).put("draft_revision", 1).put("status", "pending").put("editable_fields", JSONArray().put("to_location"))
        override suspend fun task(id: String): JSONObject = taskPayload(id)
    }
}
