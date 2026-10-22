package com.example.teamapp.data

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID

/** Server is authoritative. Guest state is never uploaded or overwritten by this store. */
class CloudStore(context: Context) {
    private val credentials = CloudCredentials(context)
    private val cache = context.getSharedPreferences("magicvvu_cloud_cache", Context.MODE_PRIVATE)
    private val mutex = Mutex()
    // Upgrades can retain an old tunnel session. Never forward its token to a new
    // origin or delete its encrypted envelope/cache; ask the user to log in again.
    var account by mutableStateOf(credentials.load()?.takeIf { saved ->
        runCatching { CloudApi.validateAddress(saved.address) }.isSuccess
    }); private set
    var households by mutableStateOf<List<CloudHousehold>>(emptyList()); private set
    var items by mutableStateOf<List<StockItem>>(emptyList()); private set
    var shopping by mutableStateOf<List<CloudShoppingItem>>(emptyList()); private set
    var busy by mutableStateOf(false); private set
    var expired by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    var lastSync by mutableStateOf(""); private set
    val signedIn get() = account != null
    val household get() = households.firstOrNull { it.id == account?.householdId }
    val scopeKey get() = account?.let { "${it.address}|${it.userId}|${it.householdId}" }.orEmpty()
    val assistant = AssistantStore(context, this)
    private val root get() = "/api/v1/households/${requireNotNull(account).householdId}"

    init { loadCache() }
    private fun cacheKey(a: CloudAccount) = "${a.address}|${a.userId}|${a.householdId}"
    private fun loadCache() {
        items = emptyList(); shopping = emptyList(); lastSync = ""
        val a = account ?: return
        runCatching {
            cache.getString(cacheKey(a), null)?.let { saved ->
                val json = JSONObject(saved)
                items = json.getJSONArray("inventory").objects().map { it.toStock().let { item -> item.copy(image = cache.getString("photo|${cacheKey(a)}|${item.id}", "").orEmpty()) } }
                shopping = json.getJSONArray("shopping").objects().map { it.toShopping() }
                lastSync = json.optString("lastSync")
                households = listOf(CloudHousehold(a.householdId, json.optString("householdName", "云端家庭"), "member"))
            }
        }.onFailure { items = emptyList(); shopping = emptyList(); error = "云端缓存不可读，请联网刷新；本机游客数据仍保留" }
    }

    private suspend fun guarded(expireOnUnauthorized: Boolean = true, block: suspend () -> Unit) = mutex.withLock {
        busy = true
        error = null
        try { block() }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            if (expireOnUnauthorized && failure is CloudFailure && failure.status == 401 && account != null) {
                expired = true
                credentials.save(null)
            }
            error = failure.message ?: "同步失败，请刷新后重试"
            throw failure
        } finally { busy = false }
    }

    suspend fun login(address: String, phone: String, password: String, name: String? = null) = guarded(expireOnUnauthorized = false) {
        CloudApi.validateAddress(address)
        val api = CloudApi(address)
        if (name != null) api.register(phone.trim(), password, name.trim())
        val authenticated = api.login(phone.trim(), password)
        val homes = CloudApi(authenticated.address, authenticated.token).households()
        val next = authenticated.copy(householdId = homes.firstOrNull()?.id.orEmpty())
        credentials.save(next)
        account = next
        households = homes
        items = emptyList(); shopping = emptyList(); lastSync = ""; expired = false
        // Authentication succeeds independently of a subsequent inventory refresh.
        if (next.householdId.isNotBlank()) runCatching { refreshData() }.onFailure { error = "登录成功，家庭数据暂未同步：${it.message.orEmpty()}" }
    }

    suspend fun refresh() {
        if (!signedIn || expired) return
        guarded {
            val current = requireNotNull(account)
            val api = CloudApi(current.address, current.token)
            val user = api.request("GET", "/api/v1/users/me")
            val homes = api.households()
            val selected = homes.firstOrNull { it.id == current.householdId } ?: homes.firstOrNull()
            val next = current.copy(displayName = user.getString("display_name"), householdId = selected?.id.orEmpty())
            if (current.householdId != next.householdId) { items = emptyList(); shopping = emptyList(); lastSync = "" }
            credentials.save(next)
            account = next; households = homes
            if (selected != null) refreshData()
        }
    }

    private suspend fun refreshData() {
        val a = requireNotNull(account)
        require(a.householdId.isNotEmpty()) { "请先创建或加入家庭" }
        val api = CloudApi(a.address, a.token)
        val stockJson = api.pages("$root/inventory-items")
        val shoppingJson = api.pages("$root/shopping-list/items?status=all")
        val stock = stockJson.map { it.toStock().let { item -> item.copy(image = cache.getString("photo|${cacheKey(a)}|${item.id}", "").orEmpty()) } }
        val plans = shoppingJson.map { it.toShopping() }
        val synced = LocalDateTime.now().format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss"))
        val json = JSONObject().put("inventory", JSONArray(stockJson)).put("shopping", JSONArray(shoppingJson))
            .put("lastSync", synced).put("householdName", household?.name ?: "云端家庭")
        check(cache.edit().putString(cacheKey(a), json.toString()).commit()) { "服务器已读取，但设备无法保存缓存，请检查存储空间" }
        items = stock; shopping = plans; lastSync = synced
    }

    private suspend fun mutate(action: suspend (CloudApi) -> Unit) {
        val expectedScope = scopeKey
        guarded {
            require(expectedScope == scopeKey && !expired) { "账号或家庭已切换，请重新操作" }
            val a = requireNotNull(account)
            require(a.householdId.isNotBlank()) { "请先创建或加入家庭" }
            action(CloudApi(a.address, a.token))
            refreshData()
        }
    }

    suspend fun selectHousehold(id: String) = guarded {
        require(households.any { it.id == id }) { "请刷新家庭列表" }
        val next = requireNotNull(account).copy(householdId = id)
        credentials.save(next)
        account = next
        val homes = households
        loadCache()
        households = homes
        refreshData()
    }
    suspend fun createHousehold(name: String) = guarded {
        val a = requireNotNull(account)
        val created = CloudApi(a.address, a.token).request("POST", "/api/v1/households", JSONObject().put("name", name.trim()))
        val homes = CloudApi(a.address, a.token).households()
        val next = a.copy(householdId = created.getString("id"))
        credentials.save(next); account = next; households = homes
        items = emptyList(); shopping = emptyList(); lastSync = ""
        refreshData()
    }
    suspend fun joinHousehold(code: String) = guarded {
        val a = requireNotNull(account)
        val joined = CloudApi(a.address, a.token).request("POST", "/api/v1/households/join", JSONObject().put("invite_code", code.trim()))
        val next = a.copy(householdId = joined.getString("id"))
        val homes = CloudApi(a.address, a.token).households()
        credentials.save(next); account = next; households = homes
        items = emptyList(); shopping = emptyList(); lastSync = ""
        refreshData()
    }
    suspend fun invitation(): String {
        var code = ""
        mutate { code = it.request("POST", "$root/invitations").getString("invite_code") }
        return code
    }
    suspend fun members(): List<String> {
        val a = requireNotNull(account)
        return CloudApi(a.address, a.token).request("GET", "$root/members").getJSONArray("items").objects().map { "${it.getString("display_name")} · ${it.getString("role")}" }
    }
    suspend fun logout() = guarded {
        val a = account
        assistant.clearAccount(a)
        // Remove local access first even if the server is unreachable; never restore another user's cache.
        credentials.save(null); account = null; households = emptyList(); items = emptyList(); shopping = emptyList(); lastSync = ""; expired = false
        if (a != null) runCatching { CloudApi(a.address, a.token).request("POST", "/api/v1/auth/logout") }
    }
    suspend fun saveItem(item: StockItem, initial: StockItem?) = mutate { api ->
        if (initial == null) api.request("POST", "$root/inventory-items", item.toCloudJson())
        else {
            val json = item.toCloudJson().apply { remove("id"); put("expected_version", initial.version); put("operation_id", UUID.randomUUID().toString()) }
            api.request("PATCH", "$root/inventory-items/${item.id}", json)
        }
        if (item.image.isNotBlank()) check(cache.edit().putString("photo|${cacheKey(requireNotNull(account))}|${item.id}", item.image).commit()) { "物品已保存，照片引用保存失败，请刷新核对" }
    }
    suspend fun adjust(item: StockItem, delta: Double, operationId: String) = mutate {
        it.request("POST", "$root/inventory-items/${item.id}/adjustments", versionBody(item, operationId).put("delta", BigDecimal.valueOf(delta).toPlainString()))
    }
    suspend fun delete(item: StockItem, operationId: String) = mutate {
        it.request("DELETE", "$root/inventory-items/${item.id}", versionBody(item, operationId))
    }
    suspend fun plan(item: StockItem, quantity: Double, requestId: String) = mutate { api ->
        val existing = shopping.firstOrNull { !it.purchased && it.sourceId == item.id }
        if (existing != null) api.request("PATCH", "$root/shopping-list/items/${existing.id}", JSONObject().put("quantity", BigDecimal.valueOf(quantity).toPlainString()))
        else api.request("POST", "$root/shopping-list/items", JSONObject().put("id", requestId).put("source_inventory_item_id", item.id)
            .put("name", item.name).put("quantity", BigDecimal.valueOf(quantity).toPlainString()).put("unit", item.unit))
    }
    suspend fun saveShopping(id: String, name: String, quantity: Double, unit: String, creating: Boolean) = mutate {
        val json = JSONObject().put("name", name.trim()).put("quantity", BigDecimal.valueOf(quantity).toPlainString()).put("unit", unit.trim())
        if (creating) json.put("id", id)
        it.request(if (creating) "POST" else "PATCH", "$root/shopping-list/items" + if (creating) "" else "/$id", json)
    }
    suspend fun removeShopping(id: String) = mutate { it.request("DELETE", "$root/shopping-list/items/$id") }
    suspend fun purchase(id: String, quantity: Double, location: String, expiry: String) = mutate {
        it.request("POST", "$root/shopping-list/items/$id/purchase", JSONObject().put("actual_quantity", BigDecimal.valueOf(quantity).toPlainString())
            .put("storage_location", location.trim().ifBlank { null } ?: JSONObject.NULL).put("expires_on", expiry.trim().ifBlank { null } ?: JSONObject.NULL))
    }
    suspend fun profile(name: String, home: String) {
        mutate { api ->
            val a = requireNotNull(account)
            if (name != a.displayName) {
                val user = api.request("PATCH", "/api/v1/users/me", JSONObject().put("display_name", name.trim()))
                val next = a.copy(displayName = user.getString("display_name"))
                credentials.save(next); account = next
            }
            if (home != household?.name) {
                api.request("PATCH", root, JSONObject().put("name", home.trim()))
                households = api.households()
            }
        }
    }
    suspend fun minimums(values: Map<String, Double>) = mutate { api ->
        items.filter { values[it.id] != null && values[it.id] != it.minimum }.forEach { item ->
            api.request("PATCH", "$root/inventory-items/${item.id}", versionBody(item).put("minimum_quantity", BigDecimal.valueOf(values.getValue(item.id)).toPlainString()))
        }
    }
    @Deprecated("Use assistant entries for structured task, draft and receipt state")
    suspend fun ask(text: String): String {
        assistant.send(text)
        return assistant.entries.lastOrNull()?.reply.orEmpty().ifBlank { assistant.error.ifBlank { "服务暂时无法回答，请恢复原任务" } }
    }
}
