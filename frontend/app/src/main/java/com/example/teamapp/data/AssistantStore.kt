package com.example.teamapp.data

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.security.MessageDigest

/** Durable outbox. A view disappearing never cancels an in-flight business request. */
class AssistantStore(
    context: Context, private val cloud: CloudStore,
    private val clientFactory: (CloudAccount) -> AgentClient = { AgentClient(it.address, it.token) },
    private val refreshHousehold: suspend () -> Unit = { cloud.refresh() }
) {
    private val prefs = context.getSharedPreferences("mewstow_assistant_v1", Context.MODE_PRIVATE)
    private val work = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val mutex = Mutex()
    private var boundScope = ""
    var entries by mutableStateOf<List<AssistantEntry>>(emptyList()); private set
    var capabilities by mutableStateOf<String>("{}"); private set
    var busy by mutableStateOf(false); private set
    var error by mutableStateOf(""); private set
    var referenceLabel by mutableStateOf(""); private set
    var activeRequestId by mutableStateOf(""); private set
    var phase by mutableStateOf(""); private set
    val activeEntry get() = entries.firstOrNull { it.requestId == activeRequestId }
    val conversationEnabled get() = JSONObject(capabilities).optString("conversation_protocol") == "backend-conversation-1"
    private val currentSession get() = cloud.account?.token?.let { token -> MessageDigest.getInstance("SHA-256").digest(token.toByteArray()).joinToString("") { "%02x".format(it) } }.orEmpty()
    private var unreadable = false

    fun launch(block: suspend AssistantStore.() -> Unit) = work.launch {
        runCatching { block() }.onFailure { error = it.message ?: "请核对任务后重试" }
    }
    fun bind() {
        if (boundScope == cloud.scopeKey) return
        if (boundScope.isNotBlank()) prefs.edit().remove("$boundScope|active").commit()
        boundScope = cloud.scopeKey; entries = emptyList(); capabilities = "{}"; error = ""; unreadable = false; referenceLabel = ""; activeRequestId = ""
        if (boundScope.isBlank()) return
        try {
            entries = prefs.getString(boundScope, null)?.let { JSONArray(it).objects().map(AssistantEntry::fromJson) }.orEmpty()
            if (prefs.getString("$boundScope|session", "") == currentSession) {
                activeRequestId = prefs.getString("$boundScope|active", "").orEmpty().takeIf { id -> entries.any { it.requestId == id } }.orEmpty()
            }
        } catch (_: Exception) {
            unreadable = true; error = "任务缓存无法读取，原始记录已保留。请核对服务器回执，勿重复执行。"
        }
    }
    fun clearAccount(account: CloudAccount?) {
        // Detach active identity only. Preserve durable requests/receipts across logout.
        // A later authenticated login may GET-recover the same scoped outbox, never auto-POST.
        if (boundScope.isNotBlank()) prefs.edit().remove("$boundScope|active").remove("$boundScope|session").commit()
        boundScope = ""; entries = emptyList(); capabilities = "{}"; activeRequestId = ""; referenceLabel = ""
    }
    private fun verifyScope(scope: String) {
        check(scope == cloud.scopeKey && scope == boundScope && !cloud.expired && cloud.signedIn) { "账号或家庭已切换，请重新选择当前家庭任务" }
    }
    private fun save(scope: String, next: List<AssistantEntry>) {
        verifyScope(scope)
        check(prefs.edit().putString(scope, JSONArray(next.map { it.toJson() }).toString())
            .putString("$scope|active", activeRequestId).putString("$scope|session", currentSession).commit()) {
            "无法持久保存操作请求，已停止发送。请检查设备空间"
        }
        entries = next
    }
    private fun entry(id: String) = entries.single { it.requestId == id }
    private fun update(scope: String, item: AssistantEntry) = save(scope, entries.map { if (it.requestId == item.requestId) item else it })

    private suspend fun session(id: String? = null, block: suspend (String, AgentClient) -> Unit) = mutex.withLock {
        bind(); val scope = boundScope
        try {
            check(!unreadable) { error }
            verifyScope(scope)
            val a = requireNotNull(cloud.account)
            require(a.householdId.isNotBlank()) { "请先选择家庭" }
            busy = true; error = ""; phase = "正在核对服务能力"
            val api = clientFactory(a)
            val caps = api.capabilities(); verifyScope(scope); capabilities = caps.toString()
            block(scope, api)
        } catch (failure: Exception) {
            if (scope == cloud.scopeKey && boundScope == scope) {
                val code = (failure as? CloudFailure)?.errorCode.orEmpty()
                error = ChatMessages.reason(code, failure.message ?: "请核对任务后重试")
                if (code in setOf("CONVERSATION_BINDING_CHANGED", "CONVERSATION_SUPERSEDED", "CONVERSATION_SESSION_EXPIRED")) { activeRequestId = ""; referenceLabel = "" }
                if (id != null && entries.any { it.requestId == id }) {
                    var old = entry(id)
                    val hinted = (failure as? CloudFailure)?.taskIdHint.orEmpty()
                    if (code == "AI_OUTCOME_UNKNOWN" && hinted.isNotBlank()) {
                        runCatching { UUID.fromString(hinted).toString() }.getOrNull()?.let {
                            old = old.copy(task = JSONObject().put("task_id", it).toString())
                        }
                    }
                    val definitiveRejection = failure is CloudFailure && failure.status in setOf(401,403,404,409,422) &&
                        code !in setOf("AI_OUTCOME_UNKNOWN", "CONVERSATION_PROCESSING", "TASK_PROCESSING", "CONCURRENT_DUPLICATE_REQUEST")
                    if (definitiveRejection && old.conversationBody.isNotBlank()) {
                        val selector = JSONObject(old.conversationBody).optString("task_id")
                        val bound = activeEntry?.takeIf { it.taskId == selector }
                        old = old.copy(conversationResolved = true, task = if (old.controlBody.isBlank() && old.taskId.isBlank() && bound != null) bound.task else old.task)
                    }
                    val state = when {
                        code == "AI_OUTCOME_UNKNOWN" -> AssistantStatus.UNKNOWN
                        old.state in setOf(AssistantStatus.COMMITTED, AssistantStatus.CANCELLED, AssistantStatus.EXPIRED, AssistantStatus.CONFLICT) ||
                            (old.state == AssistantStatus.FAILED && old.commitBody.isNotBlank()) -> old.state
                        code.contains("VERSION_CONFLICT") || code.contains("REVISION_CONFLICT") -> AssistantStatus.CONFLICT
                        code.contains("EXPIRED") -> AssistantStatus.EXPIRED
                        code in setOf("ACTION_NOT_EXECUTABLE", "PLANNING_REVALIDATION_UNAVAILABLE") -> AssistantStatus.UNSUPPORTED
                        failure is CloudFailure && failure.status in setOf(401, 403, 404, 409, 422) -> AssistantStatus.FAILED
                        old.commitBody.isNotBlank() || old.cancelBody.isNotBlank() || old.clarificationBody.isNotBlank() -> AssistantStatus.UNKNOWN
                        else -> AssistantStatus.UNKNOWN
                    }
                    runCatching { update(scope, old.copy(state = state, notice = error, failureCode = code.ifBlank { old.failureCode })) }
                    if (state == AssistantStatus.CONFLICT) runCatching { cloud.refresh() }
                }
            }
        } finally { busy = false; phase = "" }
    }

    suspend fun connectAndRecover() = session { scope, api ->
        phase = "正在恢复已保存的任务"
        for (item in entries.toList().asReversed().distinctBy { it.taskId.ifBlank { it.requestId } }.asReversed()) {
            if (item.taskId.isNotBlank() && item.state !in setOf(AssistantStatus.CANCELLED, AssistantStatus.ANSWERED, AssistantStatus.EXPIRED)) {
                try { recoverEntry(scope, api, item.requestId) }
                catch (_: Exception) {
                    verifyScope(scope)
                    val current = entry(item.requestId)
                    val safeState = when {
                        current.receipt.isNotBlank() -> AssistantStatus.COMMITTED
                        current.state in setOf(AssistantStatus.CONFLICT, AssistantStatus.FAILED, AssistantStatus.EXPIRED, AssistantStatus.CANCELLED) -> current.state
                        else -> AssistantStatus.UNKNOWN
                    }
                    update(scope, current.copy(state = safeState,
                        notice = "暂时无法恢复，请联网核实；不会自动重交操作"))
                }
            }
        }
    }

    suspend fun send(text: String) {
        require(text.isNotBlank() && text.length <= 1000) { "消息须为 1–1000 字" }
        val id = UUID.randomUUID().toString()
        val preparedScope = mutex.withLock {
            bind(); val scope = boundScope; verifyScope(scope); check(!unreadable) { error }
            require(entries.none { it.conversationBody.isNotBlank() && !it.conversationResolved && it.conversationSession == currentSession }) { "请先核实上一条消息的结果，不会自动重复调用模型" }
            val body = JSONObject().put("text", text).put("household_id", requireNotNull(cloud.account).householdId)
                .put("request_id", id).put("household_timezone", JSONObject(capabilities).optString("household_timezone", "Asia/Shanghai"))
            val conversation = JSONObject().put("text", text).put("household_id", requireNotNull(cloud.account).householdId).put("request_id", id)
            activeEntry?.takeIf { it.taskId.isNotBlank() }?.let { conversation.put("task_id", it.taskId).put("revision", it.taskRevision) }
            save(scope, entries + AssistantEntry(id, body.toString(), conversationBody = conversation.toString(), conversationSession = currentSession, transportMode = "discover"))
            scope
        }
        session(id) { scope, api ->
            require(scope == preparedScope) { "家庭已切换，原消息已保留在原家庭" }
            phase = "正在理解并核对库存"
            try {
                dispatchMessage(scope, api, id)
            }
            catch (e: Exception) {
                verifyScope(scope); update(scope, entry(id).copy(state = AssistantStatus.UNKNOWN, notice = "消息结果待核实；恢复时保留原 request_id 和原文")); throw e
            }
        }
    }
    suspend fun recover(id: String) = session(id) { scope, api ->
        var old = entry(id)
        phase = "正在核实原请求结果"
        if (old.transportMode == "discover") { dispatchMessage(scope, api, id); return@session }
        if (old.conversationResolved && old.taskId.isNotBlank() && old.commitBody.isBlank() && old.cancelBody.isBlank() &&
            old.failureCode in setOf("TASK_REVISION_CONFLICT", "TASK_SNAPSHOT_CHANGED", "CANDIDATES_CHANGED", "DRAFT_REVISION_CONFLICT", "INVENTORY_VERSION_CONFLICT")) {
            update(scope, old.copy(state = AssistantStatus.PROCESSING, edits = emptyMap(), checkedPreview = "", controlBody = "", failureCode = ""))
            acceptTask(scope, api, id, api.task(old.taskId))
            update(scope, entry(id).copy(notice = "上一条修改未采用；已读取当前任务，请重新核对并补充。"))
            activeRequestId = id; save(scope, entries); return@session
        }
        if (old.conversationBody.isNotBlank() && !old.conversationResolved) {
            require(old.conversationSession == currentSession) { "原登录会话请求已封存，请核对历史任务后开始新任务" }
            if (old.failureCode == "AI_OUTCOME_UNKNOWN" && old.taskId.isNotBlank()) {
                val task = api.task(old.taskId)
                if (task.optString("status") == "processing") {
                    update(scope, old.copy(state = AssistantStatus.UNKNOWN, notice = ChatMessages.reason("AI_OUTCOME_UNKNOWN")))
                } else {
                    acceptTask(scope, api, id, task); update(scope, entry(id).copy(conversationResolved = true))
                    activeRequestId = id; save(scope, entries)
                }
            } else sendConversation(scope, api, id)
        } else {
            recoverEntry(scope, api, id)
            if (entry(id).taskId.isNotBlank()) { activeRequestId = id; save(scope, entries) }
        }
    }
    suspend fun retryMessage(id: String) = session(id) { scope, api ->
        val old = entry(id)
        require(old.taskId.isBlank() && old.commitBody.isBlank())
        if (old.transportMode == "discover") dispatchMessage(scope, api, id)
        else if (old.conversationBody.isNotBlank()) {
            require(old.conversationSession == currentSession)
            sendConversation(scope, api, id)
        } else acceptTask(scope, api, id, api.message(JSONObject(old.requestBody)))
    }
    private suspend fun dispatchMessage(scope: String, api: AgentClient, id: String) {
        if (conversationEnabled) {
            update(scope, entry(id).copy(transportMode = "conversation"))
            sendConversation(scope, api, id)
        } else {
            require(entry(id).transportMode != "conversation") { "此请求属于新版会话，请等待对应服务恢复，不能转为普通消息重复提取" }
            update(scope, entry(id).copy(conversationBody = "", transportMode = "legacy"))
            acceptTask(scope, api, id, api.message(JSONObject(entry(id).requestBody)))
            activeRequestId = id; save(scope, entries)
        }
    }
    private suspend fun sendConversation(scope: String, api: AgentClient, id: String) {
        require(conversationEnabled) { "当前服务尚未启用会话协议，请保留原请求，勿转换为普通消息重试" }
        var old = entry(id)
        val active = activeEntry
        if (old.transportMode != "reference" && (old.controlBody.isNotBlank() || (JSONObject(capabilities).optBoolean("chat_controls") && active?.state in setOf(AssistantStatus.PENDING, AssistantStatus.UNSUPPORTED) && active?.draftId?.isNotBlank() == true && active.commitBody.isBlank()))) {
            val envelope = if (old.controlBody.isNotBlank()) JSONObject(old.controlBody) else JSONObject().put("task_id", active!!.taskId)
                .put("request", JSONObject().put("text", JSONObject(old.requestBody).getString("text"))
                    .put("task_revision", active.taskRevision).put("draft_revision", active.draftRevision).put("edits", draftEdits(active.edits)))
            update(scope, old.copy(controlBody = envelope.toString()))
            val control = api.control(envelope.getString("task_id"), envelope.getJSONObject("request")); verifyScope(scope)
            checkControl(control, envelope.getString("task_id"), envelope.getJSONObject("request"))
            if (control.getString("kind") != "not_control") {
                val source = entries.last { it.taskId == envelope.getString("task_id") }
                require(source.draftId == control.getString("draft_id") && source.taskRevision == control.getInt("task_revision") && source.draftRevision == control.getInt("draft_revision"))
                val cancelled = control.getString("kind") == "cancel"
                update(scope, entry(id).copy(task = source.task, draft = source.draft, execution = source.execution,
                    edits = if (control.optJSONObject("edits")?.length() != 0) control.getJSONObject("edits").let { e -> e.keys().asSequence().associateWith { if (e.isNull(it)) "" else e.getString(it) } } else source.edits,
                    checkedPreview = control.optJSONObject("preview")?.toString().orEmpty(),
                    conversationReply = control.optString("reply"), conversationResolved = true,
                    state = if (cancelled) AssistantStatus.CANCELLED else source.state))
                activeRequestId = if (cancelled) "" else id
                if (cancelled) referenceLabel = ""
                save(scope, entries); return
            }
            update(scope, entry(id).copy(controlBody = ""))
        }
        old = entry(id)
        val response = if (old.transportMode == "reference") api.referenceMessage(JSONObject(old.conversationBody)) else api.conversation(JSONObject(old.conversationBody))
        verifyScope(scope)
        require(response.getString("protocol_version") == "backend-conversation-1" && response.getString("request_id") == id && response.getBoolean("inventory_written") == false)
        val resolution = response.getJSONObject("resolution")
        val kind = resolution.getString("kind")
        if (kind == "clear_reference") {
            val cancelled = JSONObject(old.requestBody).getString("text").trim().trimEnd('。', '！', '!') in setOf("算了", "不用了", "取消草稿", "取消这次任务", "取消这次操作", "先不做了")
            update(scope, entry(id).copy(state = AssistantStatus.ANSWERED, conversationResolved = true,
                conversationReply = if (cancelled) "已结束当前补充任务，库存没有变动。历史记录仍保留。" else "已开始新任务。原草稿和执行记录仍保留；请告诉我要处理什么。"))
            activeRequestId = ""; referenceLabel = ""
        } else {
            val task = response.getJSONObject("task")
            if (kind == "clarify") require(task.getString("task_id") == JSONObject(old.conversationBody).getString("task_id"))
            val sameDraft = activeEntry?.takeIf { it.taskId == task.getString("task_id") && it.taskRevision == task.getInt("revision") &&
                it.draftId == task.stringOrEmpty("draft_id") && it.commitBody.isBlank() }
            if (sameDraft != null) update(scope, entry(id).copy(draft = sameDraft.draft, edits = sameDraft.edits, checkedPreview = sameDraft.checkedPreview))
            acceptTask(scope, api, id, task)
            update(scope, entry(id).copy(conversationResolved = true,
                conversationReply = if (kind == "needs_input") ChatMessages.reason(resolution.optString("error_code")) else ""))
            activeRequestId = id
            referenceLabel = if (response.optJSONObject("reference") != null) "已选择一个批次，引用有效期内可继续询问" else ""
        }
        save(scope, entries)
    }
    suspend fun validateDraft(id: String) = session(id) { scope, api ->
        val old = entry(id)
        if (JSONObject(capabilities).optBoolean("chat_controls")) {
            phase = "正在核对修改后的草稿"
            val request = JSONObject().put("text", "校验草稿").put("task_revision", old.taskRevision)
                .put("draft_revision", old.draftRevision).put("edits", draftEdits(old.edits))
            val result = api.control(old.taskId, request)
            verifyScope(scope)
            checkControl(result, old.taskId, request)
            require(result.getString("kind") == "edit" && result.getString("draft_id") == old.draftId)
            acceptCheckedPreview(scope, id, result.getJSONObject("preview"))
        } else if (JSONObject(capabilities).optBoolean("execution_preview") && old.action in setOf("OPEN", "DISCARD")) {
            val request = JSONObject().put("task_revision", old.taskRevision).put("draft_revision", old.draftRevision).put("edits", draftEdits(old.edits))
            val result = api.preview(old.draftId, request); verifyScope(scope)
            require(result.getString("draft_id") == old.draftId && result.getString("task_id") == old.taskId &&
                result.getInt("draft_revision") == old.draftRevision && result.getInt("task_revision") == old.taskRevision &&
                result.getBoolean("prospective") && !result.getBoolean("inventory_written")) { "草稿预览修订不匹配" }
            acceptCheckedPreview(scope, id, result)
        }
    }
    private fun acceptCheckedPreview(scope: String, id: String, preview: JSONObject) {
        val current = entry(id)
        val opened = preview.optJSONObject("command")?.stringOrEmpty("opened_at").orEmpty()
        val edits = if (current.edits["opened_at"] in setOf("今天", "昨天") && opened.isNotBlank()) {
            java.time.LocalDate.parse(opened)
            current.edits + ("opened_at" to opened)
        } else current.edits
        update(scope, current.copy(checkedPreview = preview.toString(), edits = edits))
    }

    /** Resolve a real source task first, then bind the exact batch via the public reference API. */
    suspend fun sendForBatch(item: StockItem, text: String) {
        require(InventoryContract.compatible(item)) { "请先在物品资料中核对名称和单位" }
        val expectedScope = cloud.scopeKey
        send("查询名为“${item.name}”的库存批次")
        if (error.isNotBlank()) return
        val source = entries.lastOrNull() ?: return
        val facts = source.result.optJSONArray("facts")?.objects().orEmpty() + source.candidates
        require(facts.any { it.stringOrEmpty("batch_id").ifBlank { it.stringOrEmpty("id") } == item.id }) { "查询结果未包含当前批次，请在助手中核对候选，尚未提交操作" }
        val id = UUID.randomUUID().toString()
        session(id) { scope, api ->
            require(expectedScope == scope && JSONObject(capabilities).optBoolean("trusted_reference_messages")) { "当前服务不能绑定指定批次" }
            val body = JSONObject().put("household_id", requireNotNull(cloud.account).householdId).put("text", text).put("request_id", id)
                .put("source_task_id", source.taskId).put("source_revision", source.taskRevision).put("batch_id", item.id)
                .put("household_timezone", JSONObject(capabilities).optString("household_timezone", "Asia/Shanghai"))
            save(scope, entries + AssistantEntry(id, JSONObject().put("text", text).toString(), conversationBody = body.toString(),
                conversationSession = currentSession, transportMode = "reference"))
            sendConversation(scope, api, id)
        }
    }
    private fun checkControl(result: JSONObject, taskId: String, request: JSONObject) {
        require(result.getString("protocol_version") == "p8-chat-control-1" &&
            result.getString("task_id") == taskId && !result.getBoolean("inventory_written") && result.getInt("model_calls") == 0 &&
            result.getInt("task_revision") == request.getInt("task_revision") &&
            result.getInt("draft_revision") == request.getInt("draft_revision") &&
            result.getString("kind") in setOf("edit", "cancel", "needs_input", "not_control")) { "草稿核对响应不匹配，请恢复任务" }
        result.optJSONObject("preview")?.let {
            require(it.getBoolean("prospective") && !it.getBoolean("inventory_written")) { "草稿预览状态不匹配" }
        }
    }
    private fun draftEdits(values: Map<String, String>) = JSONObject().apply {
        val normalized = values.mapValues { (field, value) ->
            if (field == "opened_at" && value in setOf("今天", "昨天")) {
                java.time.LocalDate.now(java.time.ZoneId.of(JSONObject(capabilities).optString("household_timezone", "Asia/Shanghai")))
                    .minusDays(if (value == "昨天") 1 else 0).toString()
            } else value
        }
        AgentExecutionPolicy.wireEdits(normalized).forEach { (key, value) -> put(key, value ?: JSONObject.NULL) }
    }
    private suspend fun acceptTask(scope: String, api: AgentClient, id: String, task: JSONObject) {
        verifyScope(scope)
        require(task.getString("household_id") == cloud.account?.householdId) { "任务家庭不匹配" }
        val old = entry(id)
        require(old.taskId.isBlank() || old.taskId == task.getString("task_id")) { "任务身份发生变化" }
        var status = when (task.optString("status")) {
            "needs_clarification" -> AssistantStatus.CLARIFICATION
            "needs_confirmation" -> AssistantStatus.PENDING
            "answered" -> AssistantStatus.ANSWERED
            "unsupported" -> AssistantStatus.UNSUPPORTED
            "processing" -> AssistantStatus.PROCESSING
            else -> AssistantStatus.FAILED
        }
        if (status == AssistantStatus.CLARIFICATION && runCatching {
                java.time.OffsetDateTime.parse(task.stringOrEmpty("expires_at")).toInstant().isBefore(java.time.Instant.now())
            }.getOrDefault(true)) status = AssistantStatus.EXPIRED
        if (old.state == AssistantStatus.CONFLICT && status == AssistantStatus.PENDING) status = AssistantStatus.CONFLICT
        if (old.state == AssistantStatus.FAILED && old.commitBody.isNotBlank() && status == AssistantStatus.PENDING) status = AssistantStatus.FAILED
        val resolvedContinuation = old.clarificationBody.isNotBlank() &&
            (task.getInt("revision") > JSONObject(old.clarificationBody).getInt("revision") || task.optString("status") !in setOf("needs_clarification", "processing"))
        update(scope, old.copy(task = task.toString(), state = status,
            clarificationBody = if (resolvedContinuation) "" else old.clarificationBody,
            notice = task.optJSONObject("result")?.stringOrEmpty("error_code").orEmpty()))
        val draftId = entry(id).draftId
        if (draftId.isNotBlank()) {
            val draft = api.draft(draftId); verifyScope(scope)
            val current = entry(id)
            val unchanged = current.draftRevision == draft.optInt("revision")
            update(scope, current.copy(draft = draft.toString(), edits = if (unchanged) current.edits else emptyMap(), checkedPreview = if (unchanged) current.checkedPreview else ""))
            acceptExecution(scope, id, api.execution(draftId))
        }
    }
    private fun acceptExecution(scope: String, id: String, execution: JSONObject) {
        verifyScope(scope)
        val old = entry(id)
        require(execution.getString("draft_id") == old.draftId && execution.getString("task_id") == old.taskId) { "执行对象不匹配" }
        val state = when (execution.getString("status")) {
            "committed" -> AssistantStatus.UNKNOWN // Only a validated formal receipt establishes success.
            "cancelled" -> AssistantStatus.CANCELLED
            "expired" -> AssistantStatus.EXPIRED
            "superseded" -> AssistantStatus.CONFLICT
            "pending" -> when {
                old.state == AssistantStatus.CONFLICT -> AssistantStatus.CONFLICT
                old.state == AssistantStatus.FAILED && old.commitBody.isNotBlank() -> AssistantStatus.FAILED
                old.commitBody.isNotBlank() || old.cancelBody.isNotBlank() -> AssistantStatus.UNKNOWN
                else -> AssistantStatus.PENDING
            }
            else -> AssistantStatus.UNSUPPORTED
        }
        update(scope, old.copy(execution = execution.toString(), state = state, notice = execution.stringOrEmpty("reason_code")))
        execution.optJSONObject("receipt")?.let { acceptReceipt(scope, id, it) }
        // A pending decision is insufficient evidence to clear an uncertain original POST.
        val item = entry(id)
        val caps = JSONObject(capabilities)
        val automatic = item.result.optJSONObject("planning_basis") != null || item.result.stringOrEmpty("quantity_source") == "planning_calculation" || item.result.stringOrEmpty("intent") == "SUGGEST_PURCHASE"
        if (item.state == AssistantStatus.PENDING && (!caps.optJSONObject("actions")!!.optBoolean(item.action) || automatic)) {
            update(scope, item.copy(state = AssistantStatus.UNSUPPORTED, notice = "当前版本暂不支持自动执行；可在库存或清单页面手动核对"))
        }
    }
    private fun acceptReceipt(scope: String, id: String, receipt: JSONObject) {
        verifyScope(scope)
        val old = entry(id); val owner = receipt.getJSONObject("scope"); val account = requireNotNull(cloud.account)
        require(receipt.getString("status") == "committed" && receipt.getString("protocol_version") == "draft-operation-receipt-1" &&
            receipt.getString("draft_id") == old.draftId && receipt.getString("task_id") == old.taskId &&
            receipt.getString("action") == old.action && receipt.getInt("draft_revision") == old.draftRevision &&
            receipt.getInt("task_revision") == old.taskRevision &&
            owner.getString("user_id") == account.userId && owner.getString("household_id") == account.householdId &&
            (old.operationId.isBlank() || receipt.getString("operation_id") == old.operationId)) { "回执身份或操作不匹配，需核实" }
        update(scope, old.copy(receipt = receipt.toString(), state = AssistantStatus.COMMITTED, notice = "", refreshNeeded = true, failureCode = ""))
    }
    private suspend fun refreshReceipt(scope: String, id: String) {
        try {
            refreshHousehold(); verifyScope(scope)
            update(scope, entry(id).copy(refreshNeeded = false, notice = ""))
        } catch (_: Exception) {
            verifyScope(scope)
            update(scope, entry(id).copy(state = AssistantStatus.COMMITTED, refreshNeeded = true, notice = "操作已执行；库存或清单刷新失败，请重新刷新"))
        }
    }
    private suspend fun recoverEntry(scope: String, api: AgentClient, id: String) {
        var old = entry(id)
        if (old.operationId.isNotBlank()) {
            try {
                val receipt = api.operation(old.operationId); acceptReceipt(scope, id, receipt)
                refreshReceipt(scope, id); return
            } catch (e: CloudFailure) { if (e.status != 404) throw e }
        }
        if (old.taskId.isNotBlank()) acceptTask(scope, api, id, api.task(old.taskId))
        old = entry(id)
        if (old.state == AssistantStatus.COMMITTED) refreshReceipt(scope, id)
        else if (old.commitBody.isNotBlank() && old.state == AssistantStatus.UNKNOWN) {
            update(scope, old.copy(notice = "尚无可恢复回执，404 不代表未执行。只能用原 operation_id 和完全相同请求恢复"))
        }
    }
    fun edit(id: String, field: String, value: String) {
        try {
            bind(); verifyScope(boundScope)
            val old = entry(id)
            check(!busy && old.state == AssistantStatus.PENDING && old.commitBody.isBlank() && field in old.editableFields)
            update(boundScope, old.copy(edits = old.edits + (field to value), checkedPreview = "", conversationReply = "修改尚未重新校验，请点击核对后查看预览。"))
        } catch (failure: Exception) { error = failure.message ?: "任务已变化，请重新选择" }
    }
    suspend fun clarify(id: String, answers: Map<String, String>) {
        if (conversationEnabled) {
            val old = entry(id)
            require(old.taskId == activeEntry?.taskId && answers.keys.all { it in old.allowedFields }) { "请先选择当前活动任务" }
            val text = if (answers.containsKey("batch_id")) {
                val index = old.candidates.indexOfFirst { it.stringOrEmpty("id").ifBlank { it.stringOrEmpty("batch_id") } == answers.getValue("batch_id") }
                require(index >= 0); "选择第${index+1}个"
            } else {
                val labels = mapOf("opened_at" to "开封日期", "purchased_at" to "购入日期", "label_expiry" to "有效期", "location" to "位置", "to_location" to "目标位置")
                if (answers.keys == setOf("quantity", "unit")) answers.getValue("quantity")+answers.getValue("unit")
                else answers.entries.joinToString("，") { (key, value) -> (labels[key] ?: "") + value }
            }
            send(text); return
        }
        session(id) { scope, api ->
        phase = "正在补充信息并核对最新库存"
        val old = entry(id)
        require(old.state == AssistantStatus.CLARIFICATION && answers.isNotEmpty() && answers.keys.all { it in old.allowedFields })
        if ("batch_id" in answers) require(old.candidates.any { it.stringOrEmpty("batch_id").ifBlank { it.stringOrEmpty("id") } == answers["batch_id"] }) { "只能选择当前有效候选批次" }
        val latest = api.task(old.taskId); verifyScope(scope)
        require(latest.getInt("revision") == old.taskRevision && latest.getString("status") == "needs_clarification") { "澄清已变化，请恢复任务并重新选择" }
        val body = JSONObject().put("revision", old.taskRevision).put("answers", JSONObject(answers)).toString()
        require(old.clarificationBody.isBlank() || JSONObject(old.clarificationBody).toString() == body) { "先恢复原澄清结果，不能覆盖结果未知的请求" }
        update(scope, old.copy(clarificationBody = body, state = AssistantStatus.PROCESSING))
        acceptTask(scope, api, id, api.clarify(old.taskId, JSONObject(body)))
        activeRequestId = id; save(scope, entries)
        }
    }
    suspend fun retryClarification(id: String) = session(id) { scope, api ->
        val old = entry(id); require(old.clarificationBody.isNotBlank())
        // First recover, then retry only the exact same revision/body if still unresolved.
        recoverEntry(scope, api, id)
        if (entry(id).clarificationBody.isNotBlank()) acceptTask(scope, api, id, api.clarify(old.taskId, JSONObject(old.clarificationBody)))
    }
    suspend fun confirm(id: String) = session(id) { scope, api ->
        phase = "正在提交，请等待服务器回执"
        val old = entry(id)
        require(old.state == AssistantStatus.PENDING && old.commitBody.isBlank() && old.cancelBody.isBlank()) { "请先核实原操作结果" }
        val latest = api.execution(old.draftId); verifyScope(scope)
        acceptExecution(scope, id, latest)
        require(entry(id).state == AssistantStatus.PENDING && latest.getInt("draft_revision") == old.draftRevision && latest.getInt("task_revision") == old.taskRevision) { "草稿状态或修订已变化，请重新核对" }
        val values = old.editableFields.associateWith { old.edits[it] ?: old.command.stringOrEmpty(it) }
        AgentExecutionPolicy.validate(old.action, values, old.editableFields)
        if (old.action == "ADD") require(values["location"].orEmpty().isNotBlank()) { "ADD 必须填写存放位置" }
        val edits = draftEdits(values)
        val body = JSONObject().put("operation_id", UUID.randomUUID().toString()).put("draft_revision", old.draftRevision)
            .put("task_revision", old.taskRevision).put("edits", edits).toString()
        update(scope, entry(id).copy(commitBody = body, state = AssistantStatus.SUBMITTING, notice = ""))
        acceptReceipt(scope, id, api.commit(old.draftId, JSONObject(body)))
        refreshReceipt(scope, id)
    }
    suspend fun retryCommit(id: String) = session(id) { scope, api ->
        phase = "正在核实原操作，避免重复执行"
        val old = entry(id); require(old.commitBody.isNotBlank())
        recoverEntry(scope, api, id)
        if (entry(id).state == AssistantStatus.UNKNOWN) {
            update(scope, entry(id).copy(state = AssistantStatus.SUBMITTING))
            acceptReceipt(scope, id, api.commit(old.draftId, JSONObject(old.commitBody)))
            refreshReceipt(scope, id)
        }
    }
    suspend fun cancel(id: String) = session(id) { scope, api ->
        phase = "正在取消草稿，库存不变"
        val old = entry(id)
        require(old.commitBody.isBlank() && old.state in setOf(AssistantStatus.PENDING, AssistantStatus.UNSUPPORTED, AssistantStatus.UNKNOWN, AssistantStatus.CANCELLED))
        val latest = api.execution(old.draftId); verifyScope(scope)
        if (latest.getString("status") == "cancelled") { acceptExecution(scope, id, latest); clearCancelledReference(scope, api, id); return@session }
        require(latest.getString("status") in setOf("pending", "unavailable") && latest.getInt("draft_revision") == old.draftRevision && latest.getInt("task_revision") == old.taskRevision) { "草稿已变化，请恢复核实" }
        val body = old.cancelBody.ifBlank { JSONObject().put("draft_revision", old.draftRevision).put("task_revision", old.taskRevision).toString() }
        update(scope, old.copy(cancelBody = body, state = AssistantStatus.SUBMITTING))
        val result = api.cancel(old.draftId, JSONObject(body)); verifyScope(scope)
        require(result.getString("status") == "cancelled" && result.getString("draft_id") == old.draftId)
        update(scope, entry(id).copy(state = AssistantStatus.CANCELLED, notice = ""))
        clearCancelledReference(scope, api, id)
    }
    private suspend fun clearCancelledReference(scope: String, api: AgentClient, entryId: String) {
        activeRequestId = ""; referenceLabel = ""; save(scope, entries)
        if (conversationEnabled) {
            val old = entry(entryId)
            if (old.referenceCleared) return
            val body = old.referenceClearBody.ifBlank {
                JSONObject().put("household_id", requireNotNull(cloud.account).householdId).put("text", "开始新任务").put("request_id", UUID.randomUUID().toString())
                    .put("task_id", old.taskId).put("revision", old.taskRevision).toString()
            }
            update(scope, old.copy(referenceClearBody = body, notice = "草稿已取消，会话引用待核实"))
            val response = api.conversation(JSONObject(body)); verifyScope(scope)
            require(response.getString("protocol_version") == "backend-conversation-1" &&
                response.getString("request_id") == JSONObject(body).getString("request_id") &&
                !response.getBoolean("inventory_written") && response.getJSONObject("resolution").getString("kind") == "clear_reference")
            update(scope, entry(entryId).copy(referenceCleared = true, notice = ""))
        }
    }
}
