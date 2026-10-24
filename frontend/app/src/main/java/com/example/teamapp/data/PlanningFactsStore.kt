package com.example.teamapp.data

import android.content.Context
import androidx.compose.runtime.*
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.util.UUID

/** A single scoped version, queue and durable outbox for all four facts sections. */
class PlanningFactsStore(context: Context, private val cloud: CloudStore,
    private val apiFactory: (CloudAccount) -> CloudApi = { CloudApi(it.address, it.token) }) {
    private val prefs = context.getSharedPreferences("mewstow_planning_facts_v1", Context.MODE_PRIVATE)
    private val work = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val queue = Mutex()
    private var bound = ""
    private var unreadable = false
    var documents by mutableStateOf<Map<String, String>>(emptyMap()); private set
    var pending by mutableStateOf<Map<String, String>>(emptyMap()); private set
    var busy by mutableStateOf(false); private set
    var error by mutableStateOf(""); private set
    var errorCode by mutableStateOf(""); private set
    var notice by mutableStateOf(""); private set
    var timezone by mutableStateOf(""); private set
    fun bind() {
        if (bound == cloud.scopeKey) return
        bound = cloud.scopeKey; documents = emptyMap(); pending = emptyMap(); error = ""; errorCode = ""; notice = ""; timezone = ""; unreadable = false
        if (bound.isNotBlank()) runCatching {
            val saved = JSONObject(prefs.getString("$bound|pending", "{}")!!)
            pending = saved.keys().asSequence().associateWith { saved.getString(it) }
        }.onFailure { unreadable = true; error = "资料请求缓存不可读，原记录已保留；请勿重复提交" }
    }
    fun launch(block: suspend PlanningFactsStore.() -> Unit) = work.launch {
        val scope = cloud.scopeKey
        try { block() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { if (scope == cloud.scopeKey) error = failure.message ?: "无法完成请求，请核对后重试" }
    }
    fun document(id: String) = documents[id]?.let(::JSONObject)
    private fun verify(scope: String) {
        check(scope.isNotBlank() && scope == cloud.scopeKey && scope == bound && !cloud.expired) { "账号或家庭已切换，请重新核对" }
    }
    private suspend fun operation(block: suspend (String, CloudApi, String) -> Unit) = queue.withLock {
        bind(); val scope = bound
        busy = true; error = ""; errorCode = ""; notice = ""
        try {
            verify(scope)
            check(!unreadable) { "资料请求缓存不可读，原记录已保留；请勿重复提交" }
            val a = requireNotNull(cloud.account)
            require(a.householdId.isNotBlank()) { "请先选择家庭" }
            val api = apiFactory(a)
            val capabilities = api.verifiedCapabilities(); verify(scope)
            check(capabilities.optString("planning_facts_protocol") == "backend-planning-facts-1") { "当前服务尚未提供资料与盘点功能" }
            timezone = capabilities.getString("household_timezone")
            block(scope, api, "/api/v1/households/${a.householdId}/inventory-items")
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { if (scope == cloud.scopeKey && bound == scope) {
            errorCode = (failure as? CloudFailure)?.errorCode.orEmpty()
            error = failure.message ?: "无法读取资料，请保留表单后重试"
        } }
        finally { busy = false }
    }
    private suspend fun read(scope: String, api: CloudApi, root: String, id: String) {
        val result = api.request("GET", "$root/$id/planning-facts"); verify(scope)
        check(result.getString("protocol_version") == "backend-planning-facts-1" &&
            result.getString("household_id") == cloud.account?.householdId && result.getString("inventory_item_id") == id) { "资料作用域不匹配" }
        documents = documents + (id to result.toString()); timezone = result.getString("household_timezone")
    }
    suspend fun load(id: String) = operation { scope, api, root -> read(scope, api, root, id) }
    private fun persist(scope: String, next: Map<String, String>) {
        verify(scope)
        check(prefs.edit().putString("$scope|pending", JSONObject(next).toString()).commit()) { "设备无法保存原始请求，已停止发送" }
        pending = next
    }
    suspend fun save(id: String, section: String, value: Any?, source: String, reviewedInventoryVersion: Int, reviewedFactsVersion: Int) = operation { scope, api, root ->
        require(section in setOf("preferences", "coverage", "stock_verification", "risk_facts"))
        require(source.isNotBlank() && source.length <= 200) { "请填写核对来源" }
        require(pending[id] == null) { "请先核实上一次资料写入，不会覆盖结果未知的请求" }
        val current = requireNotNull(document(id)) { "请先读取当前资料及版本" }
        require(current.getInt("inventory_version") == reviewedInventoryVersion && current.getInt("facts_version") == reviewedFactsVersion) { "资料已更新，请明确核对最新版本后再保存" }
        val body = JSONObject().put("operation_id", UUID.randomUUID().toString())
            .put("expected_inventory_version", current.getInt("inventory_version"))
            .put("expected_facts_version", current.getInt("facts_version")).put("source", source)
            .put(section, value ?: JSONObject.NULL)
        persist(scope, pending + (id to body.toString()))
        write(scope, api, root, id)
    }
    suspend fun replay(id: String) = operation { scope, api, root ->
        require(pending[id] != null) { "没有需要核实的原始请求" }
        write(scope, api, root, id)
    }
    private suspend fun write(scope: String, api: CloudApi, root: String, id: String) {
        val body = JSONObject(requireNotNull(pending[id]))
        try {
            val result = api.request("PATCH", "$root/$id/planning-facts", body); verify(scope)
            check(!result.getBoolean("inventory_written") && result.getString("household_id") == cloud.account?.householdId &&
                result.getString("inventory_item_id") == id) { "资料回执不匹配，保留原请求等待核实" }
            persist(scope, pending - id)
            documents = documents + (id to result.toString())
            notice = "资料已保存；库存数量未改变"
            try { read(scope, api, root, id) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { verify(scope); notice = "资料已保存，最新状态暂未刷新；请刷新核对，不要重复新建请求" }
        } catch (failure: CloudFailure) {
            verify(scope)
            if (failure.status in setOf(400, 401, 403, 404, 409, 422) && failure.errorCode != "OPERATION_ID_CONFLICT") {
                persist(scope, pending - id)
                if (failure.status == 409) runCatching { read(scope, api, root, id) }
            }
            throw failure
        }
    }
}
