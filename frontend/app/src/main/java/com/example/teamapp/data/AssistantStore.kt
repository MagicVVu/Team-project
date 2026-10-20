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
<<<<<<< HEAD
<<<<<<< HEAD
    private var selectedReference: Pair<String, String>? = null
    private var newTaskRequested = false
    private var activeTaskRequestId = ""
<<<<<<< Updated upstream
    var referenceLabel by mutableStateOf(""); private set
=======
>>>>>>> Stashed changes
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
    var entries by mutableStateOf<List<AssistantEntry>>(emptyList()); private set
    var capabilities by mutableStateOf<String>("{}"); private set
    var busy by mutableStateOf(false); private set
    var error by mutableStateOf(""); private set
    var referenceLabel by mutableStateOf(""); private set
    private var unreadable = false

    fun launch(block: suspend AssistantStore.() -> Unit) = work.launch { runCatching { block() } }
    fun bind() {
        if (boundScope == cloud.scopeKey) return
        boundScope = cloud.scopeKey; entries = emptyList(); capabilities = "{}"; error = ""; unreadable = false
        if (boundScope.isBlank()) return
        try {
            entries = prefs.getString(boundScope, null)?.let { JSONArray(it).objects().map(AssistantEntry::fromJson) }.orEmpty()
        } catch (_: Exception) {
            unreadable = true; error = "任务缓存无法读取，原始记录已保留。请核对服务器回执，勿重复执行。"
        }
    }
    fun clearAccount(account: CloudAccount?) {
        // Detach active identity only. Preserve durable requests/receipts across logout.
        // A later authenticated login may GET-recover the same scoped outbox, never auto-POST.
        boundScope = ""; entries = emptyList(); capabilities = "{}"
    }
    private fun verifyScope(scope: String) {
        check(scope == cloud.scopeKey && scope == boundScope && !cloud.expired && cloud.signedIn) { "账号或家庭已切换，请重新选择当前家庭任务" }
    }
    private fun save(scope: String, next: List<AssistantEntry>) {
        verifyScope(scope)
        check(prefs.edit().putString(scope, JSONArray(next.map { it.toJson() }).toString()).commit()) {
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
            busy = true; error = ""
            val api = clientFactory(a)
            val caps = api.capabilities(); verifyScope(scope); capabilities = caps.toString()
            block(scope, api)
        } catch (failure: Exception) {
            if (scope == cloud.scopeKey && boundScope == scope) {
                val code = (failure as? CloudFailure)?.errorCode.orEmpty()
                error = listOfNotNull(failure.message, code.takeIf { it.isNotBlank() }).joinToString(" · ")
                if (id != null && entries.any { it.requestId == id }) {
                    val old = entry(id)
                    val state = when {
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
        } finally { busy = false }
    }

    suspend fun connectAndRecover() = session { scope, api ->
        for (item in entries.toList()) {
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
<<<<<<< HEAD
<<<<<<< HEAD
        bind()
        if (text.trim() == "开始新任务") {
            selectedReference = null; referenceLabel = ""; newTaskRequested = true; error = "已清除活动引用，请输入新的库存任务"; return
        }
        val active = entries.firstOrNull { it.requestId == activeTaskRequestId }
<<<<<<< Updated upstream
        val explicitTopic = !Regex("它|这一批|这批|这个").containsMatchIn(text) &&
            (text.startsWith("添加") || text.startsWith("新增") ||
                (cloud.items.any { text.contains(it.name) } && Regex("消耗|丢弃|开封|移到|移动|放到|还有多少|在哪里|在什么地方").containsMatchIn(text)))
        if (explicitTopic) { newTaskRequested = true; selectedReference = null; referenceLabel = "" }
=======
>>>>>>> Stashed changes
        if (!newTaskRequested && active == null && entries.any { it.state in setOf(AssistantStatus.CLARIFICATION, AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.SUBMITTING) }) {
            error = "存在未完成的历史任务，请明确选择任务或核实原请求"; return
        }
        if (!newTaskRequested && active?.state == AssistantStatus.CLARIFICATION) {
<<<<<<< Updated upstream
            val answers = ClarificationReplies.resolve(text, active.allowedFields.toSet(), active.candidates.map { it.stringOrEmpty("batch_id").ifBlank { it.stringOrEmpty("id") } }, active.clarificationEdits["batch_id"])
            if (answers == null) { error = "无法唯一确定补充内容，请使用当前任务的字段或批次选择"; return }
            clarify(active.requestId, answers); return
        }
        if (active?.state in setOf(AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.SUBMITTING)) { error = "原请求结果待核实，请先恢复任务，避免创建重复任务"; return }
        val pronoun = Regex("它|这一批|这批|这个").containsMatchIn(text)
        val source = selectedReference?.let { selected -> entries.firstOrNull { it.requestId == selected.first } }
        val batch = selectedReference?.second
=======
            val answers = ClarificationReplies.resolve(text, active.allowedFields.toSet(), active.candidates.map {
                it.stringOrEmpty("batch_id").ifBlank { it.stringOrEmpty("id") }
            }, active.clarificationEdits["batch_id"])
            if (answers == null) { error = "无法唯一确定补充内容，请使用当前任务的字段或批次选择"; return }
            clarify(active.requestId, answers); return
        }
        if (active?.state in setOf(AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.SUBMITTING)) {
            error = "原请求结果待核实，请先恢复任务，避免创建重复任务"; return
        }
        val pronoun = Regex("它|这一批|这批|这个").containsMatchIn(text)
        val explicit = selectedReference
        val source = if (explicit != null) entries.firstOrNull { it.requestId == explicit.first } else null
        val facts = source?.result?.optJSONArray("facts")?.objects().orEmpty()
        val batch = explicit?.second ?: facts.singleOrNull()?.stringOrEmpty("id")
>>>>>>> Stashed changes
        if (pronoun && (source == null || batch.isNullOrBlank())) { error = "请先明确选择当前结果中的一个批次"; return }
        if (!pronoun) { selectedReference = null; referenceLabel = "" }
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
        val id = UUID.randomUUID().toString()
        val preparedScope = mutex.withLock {
            bind(); val scope = boundScope; verifyScope(scope); check(!unreadable) { error }
            val body = JSONObject().put("text", text).put("household_id", requireNotNull(cloud.account).householdId)
                .put("request_id", id).put("household_timezone", "Asia/Shanghai")
            save(scope, entries + AssistantEntry(id, body.toString()))
<<<<<<< HEAD
<<<<<<< HEAD
            check(prefs.edit().putString(scope + ":active", id).commit()) { "无法保存活动任务，已停止发送" }
<<<<<<< Updated upstream
            activeTaskRequestId = id; newTaskRequested = false
=======
            activeTaskRequestId = id
            newTaskRequested = false
>>>>>>> Stashed changes
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
            scope
        }
        session(id) { scope, api ->
            require(scope == preparedScope) { "家庭已切换，原消息已保留在原家庭" }
            val body = JSONObject(entry(id).requestBody)
            try { acceptTask(scope, api, id, api.message(body)) }
            catch (e: Exception) {
                verifyScope(scope); update(scope, entry(id).copy(state = AssistantStatus.UNKNOWN, notice = "消息结果待核实；恢复时保留原 request_id 和原文")); throw e
            }
        }
    }
    suspend fun recover(id: String) = session(id) { scope, api -> recoverEntry(scope, api, id) }
    suspend fun retryMessage(id: String) = session(id) { scope, api ->
        val old = entry(id)
        require(old.taskId.isBlank() && old.commitBody.isBlank())
<<<<<<< HEAD
<<<<<<< HEAD
        acceptTask(scope, api, id, submitMessage(api, JSONObject(old.requestBody)))
    }
    private suspend fun submitMessage(api: AgentClient, body: JSONObject): JSONObject {
        if (!body.has("source_task_id")) return api.message(body)
        require(JSONObject(capabilities).optBoolean("trusted_reference_messages")) { "服务器尚未开放受信对象引用" }
        return api.referenceMessage(body)
    }
    fun selectReference(id: String, batch: String) {
        bind(); verifyScope(boundScope)
<<<<<<< Updated upstream
        val fact = entry(id).result.optJSONArray("facts")?.objects().orEmpty().single { it.stringOrEmpty("id") == batch }
        selectedReference = id to batch; referenceLabel = "当前对象：${fact.stringOrEmpty("name")} · ${batch.take(8)}"
    }
    fun selectTask(id: String) {
        bind(); verifyScope(boundScope); require(entry(id).state == AssistantStatus.CLARIFICATION)
=======
        val old = entry(id)
        require(old.result.optJSONArray("facts")?.objects().orEmpty().any { it.stringOrEmpty("id") == batch })
        selectedReference = id to batch
        referenceLabel = "当前对象：${old.result.optJSONArray("facts")?.objects().orEmpty().first { it.stringOrEmpty("id") == batch }.stringOrEmpty("name")} · ${batch.take(8)}"
    }
    fun selectTask(id: String) {
        bind(); verifyScope(boundScope)
        require(entry(id).state == AssistantStatus.CLARIFICATION)
>>>>>>> Stashed changes
        check(prefs.edit().putString(boundScope + ":active", id).commit())
        activeTaskRequestId = id; selectedReference = null; referenceLabel = ""; newTaskRequested = false
=======
        acceptTask(scope, api, id, api.message(JSONObject(old.requestBody)))
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
        acceptTask(scope, api, id, api.message(JSONObject(old.requestBody)))
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
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
            update(scope, current.copy(draft = draft.toString(), edits = if (current.draftRevision == draft.optInt("revision")) current.edits else emptyMap()))
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
            update(boundScope, old.copy(edits = old.edits + (field to value)))
        } catch (failure: Exception) { error = failure.message ?: "任务已变化，请重新选择" }
    }
    fun editClarification(id: String, field: String, value: String) {
        bind(); verifyScope(boundScope)
        val old = entry(id)
        if (busy || old.state != AssistantStatus.CLARIFICATION || old.clarificationBody.isNotBlank() || field !in old.allowedFields) return
        update(boundScope, old.copy(clarificationEdits = old.clarificationEdits + (field to value)))
    }
    suspend fun clarify(id: String, answers: Map<String, String>) = session(id) { scope, api ->
        val old = entry(id)
        require(old.state == AssistantStatus.CLARIFICATION && answers.isNotEmpty() && answers.keys.all { it in old.allowedFields })
        if ("batch_id" in answers) require(old.candidates.any { it.stringOrEmpty("batch_id").ifBlank { it.stringOrEmpty("id") } == answers["batch_id"] }) { "只能选择当前有效候选批次" }
        val latest = api.task(old.taskId); verifyScope(scope)
        require(latest.getInt("revision") == old.taskRevision && latest.getString("status") == "needs_clarification") { "澄清已变化，请恢复任务并重新选择" }
        val body = JSONObject().put("revision", old.taskRevision).put("answers", JSONObject(answers)).toString()
        require(old.clarificationBody.isBlank() || JSONObject(old.clarificationBody).toString() == body) { "先恢复原澄清结果，不能覆盖结果未知的请求" }
        update(scope, old.copy(clarificationBody = body, state = AssistantStatus.PROCESSING))
        acceptTask(scope, api, id, api.clarify(old.taskId, JSONObject(body)))
    }
    suspend fun retryClarification(id: String) = session(id) { scope, api ->
        val old = entry(id); require(old.clarificationBody.isNotBlank())
        // First recover, then retry only the exact same revision/body if still unresolved.
        recoverEntry(scope, api, id)
        if (entry(id).clarificationBody.isNotBlank()) acceptTask(scope, api, id, api.clarify(old.taskId, JSONObject(old.clarificationBody)))
    }
    suspend fun confirm(id: String) = session(id) { scope, api ->
        val old = entry(id)
        require(old.state == AssistantStatus.PENDING && old.commitBody.isBlank() && old.cancelBody.isBlank()) { "请先核实原操作结果" }
        val latest = api.execution(old.draftId); verifyScope(scope)
        acceptExecution(scope, id, latest)
        require(entry(id).state == AssistantStatus.PENDING && latest.getInt("draft_revision") == old.draftRevision && latest.getInt("task_revision") == old.taskRevision) { "草稿状态或修订已变化，请重新核对" }
        val values = old.editableFields.associateWith { old.edits[it] ?: old.command.stringOrEmpty(it) }
        AgentExecutionPolicy.validate(old.action, values, old.editableFields)
        if (old.action == "ADD") require(values["location"].orEmpty().isNotBlank()) { "ADD 必须填写存放位置" }
        val edits = JSONObject().apply { values.forEach { (k, v) -> put(k, if (k in listOf("purchased_at", "label_expiry") && v.isBlank()) JSONObject.NULL else v) } }
        val body = JSONObject().put("operation_id", UUID.randomUUID().toString()).put("draft_revision", old.draftRevision)
            .put("task_revision", old.taskRevision).put("edits", edits).toString()
        update(scope, entry(id).copy(commitBody = body, state = AssistantStatus.SUBMITTING, notice = ""))
        acceptReceipt(scope, id, api.commit(old.draftId, JSONObject(body)))
        refreshReceipt(scope, id)
    }
    suspend fun retryCommit(id: String) = session(id) { scope, api ->
        val old = entry(id); require(old.commitBody.isNotBlank())
        recoverEntry(scope, api, id)
        if (entry(id).state == AssistantStatus.UNKNOWN) {
            update(scope, entry(id).copy(state = AssistantStatus.SUBMITTING))
            acceptReceipt(scope, id, api.commit(old.draftId, JSONObject(old.commitBody)))
            refreshReceipt(scope, id)
        }
    }
    suspend fun cancel(id: String) = session(id) { scope, api ->
        val old = entry(id)
        require(old.commitBody.isBlank() && old.state in setOf(AssistantStatus.PENDING, AssistantStatus.UNSUPPORTED, AssistantStatus.UNKNOWN))
        val latest = api.execution(old.draftId); verifyScope(scope)
        if (latest.getString("status") == "cancelled") { acceptExecution(scope, id, latest); return@session }
        require(latest.getString("status") in setOf("pending", "unavailable") && latest.getInt("draft_revision") == old.draftRevision && latest.getInt("task_revision") == old.taskRevision) { "草稿已变化，请恢复核实" }
        val body = old.cancelBody.ifBlank { JSONObject().put("draft_revision", old.draftRevision).put("task_revision", old.taskRevision).toString() }
        update(scope, old.copy(cancelBody = body, state = AssistantStatus.SUBMITTING))
        val result = api.cancel(old.draftId, JSONObject(body)); verifyScope(scope)
        require(result.getString("status") == "cancelled" && result.getString("draft_id") == old.draftId)
        update(scope, entry(id).copy(state = AssistantStatus.CANCELLED, notice = ""))
    }
}
