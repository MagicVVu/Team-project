package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.*
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.*
import org.junit.runner.RunWith
import java.net.SocketTimeoutException
import java.util.UUID

/** Completely offline fixtures; the fake transport never opens a socket. */
@RunWith(AndroidJUnit4::class)
class FrontendAlignmentTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private lateinit var ctx: Context
    private lateinit var api: FixtureApi
    private lateinit var cloud: CloudStore
    private val names = mutableSetOf<String>()
    @Before fun setup() {
        val prefix = "alignment_${UUID.randomUUID()}_"
        ctx = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                names += prefix + name
                return super.getSharedPreferences(prefix + name, mode)
            }
        }
        api = FixtureApi()
        CloudCredentials(ctx).save(CloudAccount(BuildConfig.CLOUD_API_URL, "offline-test-token", api.user, "测试成员", api.home))
        cloud = CloudStore(ctx) { _, _ -> api }
        runBlocking { cloud.refresh() }
    }
    @After fun cleanup() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        names.forEach { base.getSharedPreferences(it, 0).edit().clear().commit() }
    }

    @Test fun lifecycleDtosRetainExactQuantityAndWireCategory() {
        val stock = api.stock().put("opened_at", "2026-10-01").put("status", "FINISHED").put("quantity", "0.000001").put("category", "medicine").toStock()
        Assert.assertEquals("2026-10-01", stock.openedAt); Assert.assertFalse(stock.activeBatch)
        Assert.assertEquals("0.000001", stock.quantityText); Assert.assertEquals("药品", stock.category)
        Assert.assertEquals("medicine", stock.toCloudJson().getString("category"))
    }
    @Test fun unknownWriteReplaysTheSameOperationAfterStoreRecreation() = runBlocking {
        val store = cloud.planningFacts
        store.load(api.batch)
        api.timeoutOnce = true
        store.save(api.batch, "preferences", JSONObject().put("minimum_stock", "2.000001").put("coverage_days", 14), "用户核对", 3, 0)
        Assert.assertTrue(store.pending.containsKey(api.batch))
        val original = store.pending.getValue(api.batch)
        val restored = PlanningFactsStore(ctx, cloud) { api }
        restored.bind(); Assert.assertEquals(original, restored.pending[api.batch])
        restored.replay(api.batch)
        Assert.assertTrue(restored.pending.isEmpty())
        Assert.assertEquals(2, api.writes.size)
        Assert.assertEquals(api.writes[0], api.writes[1])
        Assert.assertEquals(1, restored.document(api.batch)!!.getInt("facts_version"))
    }
    @Test fun explicitClearDoesNotClearOmittedSectionsAndConflictsNeverAutoRetry() = runBlocking {
        val store = cloud.planningFacts
        store.load(api.batch)
        store.save(api.batch, "risk_facts", null, "明确清除", 3, 0)
        val body = JSONObject(api.writes.last())
        Assert.assertTrue(body.has("risk_facts") && body.isNull("risk_facts"))
        Assert.assertFalse(body.has("preferences")); Assert.assertFalse(body.has("coverage"))
        api.conflictOnce = true
        store.save(api.batch, "preferences", JSONObject().put("minimum_stock", "5"), "用户核对", 3, 1)
        Assert.assertEquals("PLANNING_FACTS_VERSION_CONFLICT", store.errorCode)
        Assert.assertTrue(store.pending.isEmpty())
        Assert.assertEquals(2, api.writes.size)
        Assert.assertEquals(2, store.document(api.batch)!!.getInt("facts_version"))
        store.save(api.batch, "preferences", JSONObject().put("minimum_stock", "6"), "未复核旧版本", 3, 1)
        Assert.assertEquals("A stale form must not be silently rebased", 2, api.writes.size)
    }
    @Test fun outboxesRemainIsolatedWhenTheHouseholdChanges() = runBlocking {
        val store = cloud.planningFacts
        store.load(api.batch); api.timeoutOnce = true
        store.save(api.batch, "preferences", JSONObject().put("minimum_stock", "2"), "核对", 3, 0)
        val original = store.pending.getValue(api.batch)
        cloud.selectHousehold(api.otherHome); store.bind()
        Assert.assertTrue(store.pending.isEmpty()); Assert.assertTrue(store.documents.isEmpty())
        cloud.selectHousehold(api.home); store.bind()
        Assert.assertEquals(original, store.pending[api.batch])
    }
    @Test fun unreadableOutboxIsPreservedAndBlocksNewWrites() = runBlocking {
        val prefs = ctx.getSharedPreferences("mewstow_planning_facts_v1", 0)
        val key = "${cloud.scopeKey}|pending"
        prefs.edit().putString(key, "{broken-original").commit()
        val store = PlanningFactsStore(ctx, cloud) { api }
        store.load(api.batch)
        store.save(api.batch, "risk_facts", null, "核对", 3, 0)
        Assert.assertTrue(api.writes.isEmpty())
        Assert.assertEquals("{broken-original", prefs.getString(key, null))
        Assert.assertTrue(store.error.contains("原记录已保留"))
    }
    @Test fun factsPageUsesRealVersionsAndLeavesCoverageUnknownUntilExplicitInput() {
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { PlanningFactsPanel(cloud, cloud.items.single(), "coverage") } } }
        compose.onNodeWithTag("planning-facts-panel").assertExists()
        compose.onNodeWithText("家庭时区：Asia/Shanghai").assertExists()
        compose.onNodeWithText("没有消费事件不代表零消费。请逐日核对；今天和未来不可声明完整。").assertExists()
        Assert.assertTrue(api.writes.isEmpty())
        shot("facts-light-zh")
        compose.onNodeWithText("日历选择已结束日期").performScrollTo().performClick()
        compose.onNodeWithTag("coverage-weekday-0").assertTextEquals("日")
        val today = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"))
        compose.onNodeWithTag("coverage-day-$today").assertIsNotEnabled()
        shot("coverage-calendar-zh")
        compose.onNodeWithText("取消").performClick()
    }
    @Test fun englishDarkFactsKeepProtocolValuesAndRenderConsistently() {
        compose.setContent { AppLanguageProvider("en") { TeamAppTheme(darkTheme = true) { Surface { PlanningFactsPanel(cloud, cloud.items.single(), "risk_facts") } } } }
        compose.onAllNodesWithText("Label & storage", substring = true).assertCountEquals(2)
        compose.onNodeWithText("Household timezone: Asia/Shanghai").assertExists()
        Assert.assertEquals("食品", cloud.items.single().category)
        shot("facts-dark-en")
    }
    @Test fun ledgerShowsOnlyConsumedEventsAndOriginalReceipt() {
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { ConsumptionEventsPanel(cloud, api.batch) } } }
        compose.onNodeWithText("已读取 1 / 1 条消费事件").assertExists()
        compose.onNodeWithText("0.000001 L").assertExists()
        shot("ledger-light-zh")
        compose.onNodeWithText("查看原业务回执").performScrollTo().performClick()
        compose.onNodeWithText("状态：已执行").assertExists()
        compose.onNodeWithText("CONSUME").assertExists()
    }
    @Test fun changingOnePreferencePreservesTheOtherFieldsInItsReplacementBlock() {
        api.seedPreferences()
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { PlanningFactsPanel(cloud, cloud.items.single()) } } }
        compose.onNodeWithText("规划最低库存（可未知）").performScrollTo().performTextClearance()
        compose.onNodeWithText("规划最低库存（可未知）").performTextInput("4")
        compose.onNodeWithText("核对来源（必填）").performScrollTo().performTextInput("逐项核对包装与消费需求")
        compose.onNodeWithTag("planning-save").performScrollTo().performClick()
        compose.waitForIdle()
        val prefs = JSONObject(api.writes.single()).getJSONObject("preferences")
        Assert.assertEquals("4", prefs.getString("minimum_stock"))
        Assert.assertEquals(14, prefs.getInt("coverage_days")); Assert.assertEquals(3, prefs.getInt("lead_days"))
        Assert.assertEquals("盒", prefs.getString("order_unit")); Assert.assertEquals("2", prefs.getString("pack_size"))
    }
    @Test fun concurrentLedgerPagingDeduplicatesEventsAndShowsTheReadGap() {
        api.pagedLedger = true
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { ConsumptionEventsPanel(cloud) } } }
        compose.onNodeWithText("继续读取消费事件").performScrollTo().performClick()
        compose.onNodeWithText("已读取 2 / 3 条消费事件").assertExists()
        compose.onNodeWithText("分页期间记录可能变化，已读取条目不足总数，请刷新核对。").assertExists()
        compose.onAllNodesWithText("0.000001 L").assertCountEquals(2)
    }
    @Test fun structuredCardsKeepNullForecastUnknownAndSeparatePartialSections() {
        val result = JSONObject().put("sections", JSONArray().put(JSONObject().put("name", "risk").put("status", "unavailable"))
            .put(JSONObject().put("name", "planning").put("status", "partial")))
            .put("forecast", JSONArray().put(JSONObject().put("name", "测试牛奶").put("status", "insufficient_data").put("remaining_days", JSONObject.NULL).put("reference_date", JSONObject.NULL)))
            .put("truncated", true).put("total_count", 12)
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { androidx.compose.foundation.layout.Column { AgentResultCards(result, { _, _ -> }, {}) } } } }
        compose.onNodeWithText("暂不可用").assertExists(); compose.onNodeWithText("部分可用").assertExists()
        compose.onNodeWithText("参考剩余天数：未知 / 尚不足以判断").assertExists()
        compose.onNodeWithText("参考日期：未知 / 尚不足以判断").assertExists()
        compose.onNodeWithText("仅展示部分结果；符合条件总数：12").assertExists()
    }
    @Test fun familyActionsAreGatedByRoleAndRequireNameConfirmation() = runBlocking {
        api.role = "owner"; cloud.refresh()
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = true) { Surface {
            androidx.compose.foundation.layout.Column { FamilyManagement(cloud, listOf(CloudMember(api.user, "我", "owner", "2026-10-01"), CloudMember(api.member, "测试成员", "member", "2026-10-02")), {}) }
        } } } }
        compose.onNodeWithText("设为管理员").assertExists()
        compose.onNodeWithText("转让家庭").assertExists()
        shot("family-dark-zh")
        compose.onNodeWithText("解散家庭").performClick()
        compose.onNodeWithTag("family-confirm-management").assertIsNotEnabled()
        compose.onNodeWithText("完整家庭名").performTextInput("测试家庭")
        compose.onNodeWithTag("family-confirm-management").assertIsEnabled()
        Assert.assertTrue(api.management.isEmpty())
    }
    @Test fun openingFormDoesNotRequestQuantityAndTerminalBatchesCannotPrepare() {
        val item = mutableStateOf(cloud.items.single())
        compose.setContent { AppLanguageProvider("en") { TeamAppTheme(darkTheme = false) { BatchOperationsPanel(cloud, item.value, "OPEN") } } }
        compose.onNodeWithText("Actual opening date YYYY-MM-DD").assertExists()
        compose.onNodeWithText("Quantity (L)").assertDoesNotExist()
        shot("batch-open-light-en")
        compose.runOnIdle { item.value = item.value.copy(lifecycleStatus = "FINISHED") }
        compose.onNodeWithTag("batch-prepare").assertIsNotEnabled()
        Assert.assertTrue(cloud.assistant.entries.isEmpty())
    }
    @Test fun batchRequestBindsOnlyARealSourceTaskAndTheExactBatch() = runBlocking {
        val client = FixtureAgent(api)
        val assistant = AssistantStore(ctx, cloud, { client }, {})
        assistant.sendForBatch(cloud.items.single(), "这批还能用多久？")
        Assert.assertEquals(1, client.references.size)
        val body = JSONObject(client.references.single())
        Assert.assertEquals(api.batch, body.getString("batch_id"))
        Assert.assertEquals(client.sourceTask, body.getString("source_task_id"))
        Assert.assertEquals(1, body.getInt("source_revision"))
        Assert.assertEquals("reference", assistant.entries.last().transportMode)
    }
    @Test fun absentBatchNeverFabricatesAReferenceSource() = runBlocking {
        val client = FixtureAgent(api).apply { includeBatch = false }
        val assistant = AssistantStore(ctx, cloud, { client }, {})
        Assert.assertTrue(runCatching { assistant.sendForBatch(cloud.items.single(), "消耗它1L") }.isFailure)
        Assert.assertTrue(client.references.isEmpty())
    }
    @Test fun independentPreviewRunsOnlyOnceAndEditsInvalidateIt() = runBlocking {
        val client = FixtureAgent(api).apply { createDraft = true }
        val assistant = AssistantStore(ctx, cloud, { client }, {})
        assistant.send("把牛奶开封日期设为2026-10-01")
        val id = assistant.entries.single().requestId
        assistant.validateDraft(id)
        Assert.assertEquals(1, client.previews.size); Assert.assertEquals(0, client.controls)
        Assert.assertTrue(assistant.entries.single().checkedPreview.isNotBlank())
        assistant.edit(id, "opened_at", "2026-10-02")
        Assert.assertTrue(assistant.entries.single().checkedPreview.isBlank())
    }
    @Test fun cancellationStaysCancelledWhileReferenceResetReplaysItsOriginalBody() = runBlocking {
        val client = FixtureAgent(api).apply { createDraft = true; failClearOnce = true }
        val assistant = AssistantStore(ctx, cloud, { client }, {})
        assistant.send("把牛奶开封日期设为2026-10-01")
        val id = assistant.entries.single().requestId
        assistant.cancel(id)
        val cancelled = assistant.entries.single()
        Assert.assertEquals(AssistantStatus.CANCELLED, cancelled.state)
        Assert.assertFalse(cancelled.referenceCleared)
        Assert.assertTrue(cancelled.referenceClearBody.isNotBlank())
        assistant.cancel(id)
        Assert.assertEquals(AssistantStatus.CANCELLED, assistant.entries.single().state)
        Assert.assertTrue(assistant.entries.single().referenceCleared)
        Assert.assertEquals(2, client.clears.size); Assert.assertEquals(client.clears[0], client.clears[1])
        Assert.assertTrue(assistant.activeRequestId.isBlank()); Assert.assertTrue(assistant.referenceLabel.isBlank())
    }
    private fun shot(name: String) {
        compose.waitForIdle(); InstrumentationRegistry.getInstrumentation().waitForIdleSync(); android.os.SystemClock.sleep(300)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val folder = ctx.cacheDir.resolve("frontend-alignment").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
    }
}

private class FixtureAgent(private val fixture: FixtureApi) : AgentClient(BuildConfig.CLOUD_API_URL, "offline-agent") {
    val sourceTask = "00000000-0000-4000-8000-000000000010"
    private val secondTask = "00000000-0000-4000-8000-000000000011"
    private val draftId = "00000000-0000-4000-8000-000000000012"
    var includeBatch = true
    var createDraft = false
    var failClearOnce = false
    var controls = 0
    private var cancelled = false
    val references = mutableListOf<String>()
    val previews = mutableListOf<String>()
    val clears = mutableListOf<String>()
    override suspend fun capabilities() = JSONObject().put("conversation_protocol", "backend-conversation-1").put("trusted_reference_messages", true)
        .put("chat_controls", false).put("execution_preview", true).put("household_timezone", "Asia/Shanghai")
        .put("actions", JSONObject().put("OPEN", true).put("CONSUME", true).put("MOVE", true).put("ADD", true).put("PLAN_ADD", true).put("DISCARD", true))
    private fun command() = JSONObject().put("action", "OPEN").put("name", "测试牛奶").put("batch_id", fixture.batch).put("expected_version", 3).put("opened_at", "2026-10-01")
    private fun taskPayload(id: String) = JSONObject().put("task_id", id).put("household_id", fixture.home).put("revision", 1)
        .put("status", if (createDraft) "needs_confirmation" else "answered").put("draft_id", if (createDraft) draftId else JSONObject.NULL)
        .put("result", JSONObject().put("status", if (createDraft) "needs_confirmation" else "answered")
            .put("facts", if (includeBatch) JSONArray().put(fixture.stock()) else JSONArray()))
    private fun response(body: JSONObject, id: String) = JSONObject().put("protocol_version", "backend-conversation-1").put("request_id", body.getString("request_id"))
        .put("inventory_written", false).put("resolution", JSONObject().put("kind", "new_task")).put("task", taskPayload(id))
    override suspend fun conversation(body: JSONObject): JSONObject {
        if (body.getString("text") == "开始新任务") {
            clears += body.toString()
            check(body.getString("task_id") == sourceTask && body.getInt("revision") == 1)
            if (failClearOnce) { failClearOnce = false; throw SocketTimeoutException("Synthetic reference-reset response loss") }
            return response(body, sourceTask).put("resolution", JSONObject().put("kind", "clear_reference"))
        }
        return response(body, sourceTask)
    }
    override suspend fun referenceMessage(body: JSONObject): JSONObject { references += body.toString(); return response(body, secondTask) }
    override suspend fun draft(id: String) = JSONObject().put("draft_id", draftId).put("revision", 1).put("draft", command())
    override suspend fun execution(id: String) = JSONObject().put("draft_id", draftId).put("task_id", sourceTask).put("draft_revision", 1).put("task_revision", 1)
        .put("status", if (cancelled) "cancelled" else "pending").put("editable_fields", JSONArray().put("opened_at"))
    override suspend fun preview(id: String, body: JSONObject): JSONObject {
        previews += body.toString()
        return execution(id).put("command", command()).put("before", fixture.stock()).put("after", fixture.stock().put("opened_at", "2026-10-01"))
            .put("prospective", true).put("inventory_written", false)
    }
    override suspend fun control(id: String, body: JSONObject): JSONObject { controls++; error("Control must not run when only independent preview is supported") }
    override suspend fun cancel(id: String, body: JSONObject): JSONObject { cancelled = true; return JSONObject().put("draft_id", draftId).put("status", "cancelled") }
}

private class FixtureApi : CloudApi(BuildConfig.CLOUD_API_URL) {
    val home = "00000000-0000-4000-8000-000000000001"
    val otherHome = "00000000-0000-4000-8000-000000000002"
    val user = "00000000-0000-4000-8000-000000000003"
    val member = "00000000-0000-4000-8000-000000000004"
    val batch = "00000000-0000-4000-8000-000000000005"
    val operation = "00000000-0000-4000-8000-000000000006"
    var role = "member"
    var timeoutOnce = false
    var conflictOnce = false
    var pagedLedger = false
    var version = 0
    val writes = mutableListOf<String>()
    val management = mutableListOf<String>()
    private val receipts = mutableMapOf<String, String>()
    private var preferences: Any = JSONObject.NULL
    fun seedPreferences() { preferences = JSONObject().put("minimum_stock", "1").put("coverage_days", 14).put("lead_days", 3).put("order_unit", "盒").put("pack_size", "2") }
    override suspend fun verifiedCapabilities() = JSONObject().put("planning_facts_protocol", "backend-planning-facts-1").put("household_timezone", "Asia/Shanghai")
    fun stock() = JSONObject().put("id", batch).put("name", "测试牛奶").put("quantity", "5.000001").put("unit", "L").put("category", "food")
        .put("storage_location", "冰箱").put("minimum_quantity", "1").put("version", 3).put("status", "ACTIVE").put("opened_at", JSONObject.NULL)
    private fun document() = JSONObject().put("protocol_version", "backend-planning-facts-1").put("household_id", home).put("inventory_item_id", batch)
        .put("inventory_version", 3).put("facts_version", version).put("household_timezone", "Asia/Shanghai")
        .put("preferences", preferences).put("risk_facts", JSONObject.NULL).put("stock_verification", JSONObject.NULL)
        .put("coverage", JSONArray()).put("invalidated_sections", JSONArray()).put("provenance", JSONObject()).put("inventory_written", false)
    override suspend fun request(method: String, path: String, body: JSONObject?): JSONObject {
        if (method == "GET" && path == "/api/v1/users/me") return JSONObject().put("id", user).put("display_name", "测试成员")
        if (method == "GET" && path == "/api/v1/households") return JSONObject().put("items", JSONArray().put(JSONObject().put("id", home).put("name", "测试家庭").put("my_role", role)).put(JSONObject().put("id", otherHome).put("name", "其他家庭").put("my_role", "member")))
        if (path.endsWith("planning-facts")) {
            if (method == "GET") return document()
            check(method == "PATCH" && body != null)
            writes += body.toString()
            if (conflictOnce) { conflictOnce = false; version++; throw CloudFailure(409, "资料已更新", "PLANNING_FACTS_VERSION_CONFLICT") }
            val id = body.getString("operation_id")
            val result = receipts[id] ?: run {
                check(body.getInt("expected_facts_version") == version)
                version++; if (body.has("preferences")) preferences = body.get("preferences")
                document().toString().also { receipts[id] = it }
            }
            if (timeoutOnce) { timeoutOnce = false; throw SocketTimeoutException("Synthetic response loss") }
            return JSONObject(result)
        }
        if (path.startsWith("/api/v1/operations/")) return JSONObject().put("operation_id", operation).put("action", "CONSUME").put("status", "committed")
            .put("scope", JSONObject().put("household_id", home).put("user_id", user)).put("committed_at", "2026-10-23T10:00:00Z").put("event_ids", JSONArray().put("event-one"))
        if (path.contains("consumption-events")) {
            val event = JSONObject().put("id", "event-one").put("operation_id", operation)
                .put("inventory_item_id", batch).put("quantity", "0.000001").put("unit", "L").put("occurred_at", "2026-10-23T10:00:00Z")
                .put("before", JSONObject().put("quantity", "5.000002")).put("after", JSONObject().put("quantity", "5.000001"))
            val entries = JSONArray().put(event)
            if (pagedLedger && !path.contains("offset=0")) entries.put(JSONObject(event.toString()).put("id", "event-two"))
            return JSONObject().put("total", if (pagedLedger) 3 else 1).put("items", entries)
        }
        if (method == "GET" && path.contains("inventory-items?")) return JSONObject().put("total", 1).put("items", if (path.contains("offset=0")) JSONArray().put(stock()) else JSONArray())
        if (method == "GET" && path.contains("shopping-list/items")) return JSONObject().put("total", 0).put("items", JSONArray())
        if (method == "GET" && path.endsWith("members")) return JSONObject().put("items", JSONArray())
        management += "$method $path"
        return JSONObject()
    }
}
