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
class CloudStore(context: Context, private val apiFactory: (String, String) -> CloudApi = { address, token -> CloudApi(address, token) }) {
    private val credentials = CloudCredentials(context)
    private val cache = context.getSharedPreferences("magicvvu_cloud_cache", Context.MODE_PRIVATE)
    private val groupingOutbox = context.getSharedPreferences("mewstow_inventory_grouping_outbox_v1", Context.MODE_PRIVATE)
    private val mutex = Mutex()
    // Upgrades can retain an old tunnel session. Never forward its token to a new
    // origin or delete its encrypted envelope/cache; ask the user to log in again.
    var account by mutableStateOf(credentials.load()?.takeIf { saved ->
        runCatching { CloudApi.validateAddress(saved.address) }.isSuccess
    }); private set
    var households by mutableStateOf<List<CloudHousehold>>(emptyList()); private set
    var items by mutableStateOf<List<StockItem>>(emptyList()); private set
    var shopping by mutableStateOf<List<CloudShoppingItem>>(emptyList()); private set
    var products by mutableStateOf<List<CloudProduct>>(emptyList()); private set
    var productError by mutableStateOf<String?>(null); private set
    val unlinkedItems get() = items.filter { item -> products.none { p -> p.batches.any { it.id == item.id } } }
    var busy by mutableStateOf(false); private set
    var expired by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    var lastSync by mutableStateOf(""); private set
    val signedIn get() = account != null
    val household get() = households.firstOrNull { it.id == account?.householdId }
    val scopeKey get() = account?.let { "${it.address}|${it.userId}|${it.householdId}" }.orEmpty()
    val assistant = AssistantStore(context, this)
    val planningFacts = PlanningFactsStore(context, this) { apiFactory(it.address, it.token) }
    suspend fun capabilities(): JSONObject {
        val a = requireNotNull(account); val expected = scopeKey
        val result = apiFactory(a.address, a.token).verifiedCapabilities()
        check(expected == scopeKey && !expired) { "家庭已切换，请重新核对" }
        return result
    }
    private val root get() = "/api/v1/households/${requireNotNull(account).householdId}"

    init { loadCache() }
    private fun cacheKey(a: CloudAccount) = "${a.address}|${a.userId}|${a.householdId}"
    private fun productWithPhotos(json: JSONObject, a: CloudAccount): CloudProduct = json.toCloudProduct().let { product ->
        product.copy(batches = product.batches.map { item ->
            item.copy(image = cache.getString("photo|${cacheKey(a)}|${item.id}", "").orEmpty())
        })
    }
    private fun loadCache() {
        items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""
        val a = account ?: return
        runCatching {
            cache.getString(cacheKey(a), null)?.let { saved ->
                val json = JSONObject(saved)
                items = json.getJSONArray("inventory").objects().map { it.toStock().let { item -> item.copy(image = cache.getString("photo|${cacheKey(a)}|${item.id}", "").orEmpty()) } }
                shopping = json.getJSONArray("shopping").objects().map { it.toShopping() }
                products = json.optJSONArray("products")?.objects()?.map { productWithPhotos(it, a) }.orEmpty()
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
        val api = apiFactory(address, "")
        if (name != null) api.register(phone.trim(), password, name.trim())
        val authenticated = api.login(phone.trim(), password)
        val homes = apiFactory(authenticated.address, authenticated.token).households()
        val next = authenticated.copy(householdId = homes.firstOrNull()?.id.orEmpty())
        credentials.save(next)
        account = next
        households = homes
        items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""; expired = false
        // Authentication succeeds independently of a subsequent inventory refresh.
        if (next.householdId.isNotBlank()) runCatching { refreshData() }.onFailure { error = "登录成功，家庭数据暂未同步：${it.message.orEmpty()}" }
    }

    suspend fun refresh() {
        if (!signedIn || expired) return
        guarded {
            val current = requireNotNull(account)
            val api = apiFactory(current.address, current.token)
            val user = api.request("GET", "/api/v1/users/me")
            val homes = api.households()
            val selected = homes.firstOrNull { it.id == current.householdId } ?: homes.firstOrNull()
            val next = current.copy(displayName = user.getString("display_name"), householdId = selected?.id.orEmpty())
            if (current.householdId != next.householdId) { items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = "" }
            credentials.save(next)
            account = next; households = homes
            if (selected != null) refreshData()
        }
    }

    private suspend fun refreshData() {
        val a = requireNotNull(account)
        require(a.householdId.isNotEmpty()) { "请先创建或加入家庭" }
        val api = apiFactory(a.address, a.token)
        val stockJson = api.pages("$root/inventory-items")
        val shoppingJson = api.pages("$root/shopping-list/items?status=all")
        val stock = stockJson.map { it.toStock().let { item -> item.copy(image = cache.getString("photo|${cacheKey(a)}|${item.id}", "").orEmpty()) } }
        val plans = shoppingJson.map { it.toShopping() }
        val productJson = try { api.pages("$root/inventory-products").also { productError = null } }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { productError = failure.message ?: "商品加载失败"; null }
        val catalogue = productJson?.map { productWithPhotos(it, a) }
        val synced = LocalDateTime.now().format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss"))
        val json = JSONObject().put("inventory", JSONArray(stockJson)).put("shopping", JSONArray(shoppingJson))
            .put("lastSync", synced).put("householdName", household?.name ?: "云端家庭")
        if (productJson != null) json.put("products", JSONArray(productJson))
        else cache.getString(cacheKey(a), null)?.let { previous -> JSONObject(previous).optJSONArray("products")?.let { json.put("products", it) } }
        check(cache.edit().putString(cacheKey(a), json.toString()).commit()) { "服务器已读取，但设备无法保存缓存，请检查存储空间" }
        items = stock; shopping = plans; lastSync = synced
        if (catalogue != null) products = catalogue
    }

    private suspend fun mutate(action: suspend (CloudApi) -> Unit) {
        val expectedScope = scopeKey
        guarded {
            require(expectedScope == scopeKey && !expired) { "账号或家庭已切换，请重新操作" }
            val a = requireNotNull(account)
            require(a.householdId.isNotBlank()) { "请先创建或加入家庭" }
            action(apiFactory(a.address, a.token))
            try { refreshData() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { error = "操作已提交，最新家庭数据暂未刷新；请刷新核对，不要重复提交" }
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
        val created = apiFactory(a.address, a.token).request("POST", "/api/v1/households", JSONObject().put("name", name.trim()))
        val homes = apiFactory(a.address, a.token).households()
        val next = a.copy(householdId = created.getString("id"))
        credentials.save(next); account = next; households = homes
        items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""
        refreshData()
    }
    suspend fun joinHousehold(code: String) = guarded {
        val a = requireNotNull(account)
        val joined = apiFactory(a.address, a.token).request("POST", "/api/v1/households/join", JSONObject().put("invite_code", code.trim()))
        val next = a.copy(householdId = joined.getString("id"))
        val homes = apiFactory(a.address, a.token).households()
        credentials.save(next); account = next; households = homes
        items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""
        refreshData()
    }
    suspend fun invitation(): String {
        var code = ""
        mutate { code = it.request("POST", "$root/invitations").getString("invite_code") }
        return code
    }
    suspend fun members(): List<CloudMember> {
        val a = requireNotNull(account)
        return apiFactory(a.address, a.token).request("GET", "$root/members").getJSONArray("items").objects().map {
            CloudMember(it.getString("user_id"), it.getString("display_name"), it.getString("role"), it.stringOrEmpty("joined_at"))
        }
    }
    suspend fun readHousehold(path: String): JSONObject {
        val scope = scopeKey
        val a = requireNotNull(account)
        require(a.householdId.isNotBlank() && !expired)
        val result = apiFactory(a.address, a.token).request("GET", "$root/$path")
        check(scope == scopeKey && !expired) { "家庭已切换，请重新读取" }
        return result
    }
    suspend fun reviewProductGrouping(item: StockItem): ProductGroupingReview {
        val expectedScope = scopeKey
        require(expectedScope.isNotBlank() && signedIn && !expired) { "请登录并选择家庭" }
        val name = java.net.URLEncoder.encode(item.name, "UTF-8")
        val rows = mutableListOf<JSONObject>()
        var offset = 0
        do {
            val result = readHousehold("inventory-product-matches?name=$name&limit=200&offset=$offset")
            check(expectedScope == scopeKey && !expired) { "账号或家庭已切换，请重新核对物品归类" }
            check(result.getString("protocol_version") == "inventory-product-matches-1") { "服务器尚未提供物品归类功能" }
            val page = result.getJSONArray("items").objects()
            rows.addAll(page)
            offset += page.size
            check(page.isNotEmpty() || rows.size == result.getInt("total")) { "相似物品列表不完整，请刷新后重新核对" }
        } while (offset < result.getInt("total"))
        val matches = rows.map { it.toProductGroupingMatch() }
        check(matches.map { it.inventoryItemId }.distinct().size == matches.size) { "相似物品返回重复记录，请重新核对" }
        return ProductGroupingReview(expectedScope, item, matches)
    }
    fun pendingProductGrouping(): ProductGroupingWrite? {
        if (scopeKey.isBlank()) return null
        val saved = groupingOutbox.getString(scopeKey, null) ?: return null
        // Invalid data is not discarded: it must continue to block another create.
        val json = JSONObject(saved)
        return ProductGroupingWrite(scopeKey, json.getString("body"), json.optString("image"))
    }
    suspend fun createGroupedInventory(review: ProductGroupingReview, match: ProductGroupingMatch?) {
        require(review.scope == scopeKey && signedIn && !expired) { "账号或家庭已切换，请重新核对物品归类" }
        require(match == null || match in review.candidates) { "请选择本次核对过的库存物品" }
        check(pendingProductGrouping() == null) { "上次保存结果尚未核实，请先用原请求重试" }
        val body = groupedInventoryBody(review.item, match).toString()
        val pending = ProductGroupingWrite(review.scope, body, review.item.image)
        check(groupingOutbox.edit().putString(review.scope, JSONObject().put("body", body).put("image", pending.image).toString()).commit()) {
            "设备未能保存原请求，尚未提交，请检查存储空间"
        }
        replayGroupedInventory(pending)
    }
    suspend fun replayGroupedInventory(pending: ProductGroupingWrite) {
        require(pending.scope == scopeKey && signedIn && !expired) { "账号或家庭已切换，请回到原家庭核实保存结果" }
        check(pendingProductGrouping() == pending) { "原请求已改变，请重新打开保存结果核实" }
        mutate { api ->
            require(pending.scope == scopeKey && !expired) { "账号或家庭已切换，请回到原家庭核实保存结果" }
            try {
                val receipt = api.request("POST", "$root/inventory-items", JSONObject(pending.body))
                check(receipt.getString("id") == pending.itemId) { "服务器返回的批次与原请求不一致，请保留原请求核实" }
            } catch (failure: CloudFailure) {
                if (failure.status in setOf(400, 409, 422) && !failure.errorCode.contains("OPERATION_ID_CONFLICT")) {
                    // Auth/access errors cannot rule out an earlier successful, timed-out request.
                    // Network/5xx and operation-ID conflicts also retain the original body.
                    check(groupingOutbox.edit().remove(pending.scope).commit()) { "请求被拒绝，但设备未能更新核实状态，请保留原请求" }
                }
                throw failure
            }
            if (pending.image.isNotBlank()) check(cache.edit()
                .putString("photo|${cacheKey(requireNotNull(account))}|${pending.itemId}", pending.image).commit()) {
                "物品已保存，照片引用保存失败，请用原请求核实"
            }
            check(groupingOutbox.edit().remove(pending.scope).commit()) { "物品已保存，设备未能更新状态，请用原请求核实" }
        }
    }
    suspend fun operationReceipt(id: String): JSONObject {
        val a = requireNotNull(account); val scope = scopeKey
        val receipt = apiFactory(a.address, a.token).request("GET", "/api/v1/operations/${UUID.fromString(id)}")
        check(scope == scopeKey && receipt.getString("operation_id") == id &&
            receipt.getJSONObject("scope").getString("household_id") == a.householdId) { "回执家庭不匹配" }
        return receipt
    }
    suspend fun manageFamily(action: String, memberId: String = "", confirmation: String = "") {
        guarded {
            val a = requireNotNull(account); val api = apiFactory(a.address, a.token)
            val memberPath = "$root/members/${if (memberId.isBlank()) "" else UUID.fromString(memberId)}"
            when(action) {
                "leave" -> api.request("POST", "$root/leave")
                "remove" -> api.request("DELETE", memberPath)
                "admin", "member" -> api.request("PATCH", memberPath, JSONObject().put("role", action))
                "transfer" -> api.request("POST", "$root/transfer-ownership", JSONObject().put("new_owner_user_id", memberId))
                "dissolve" -> api.request("DELETE", root, JSONObject().put("confirmation_name", confirmation))
                else -> error("不支持的家庭操作")
            }
            if (action in setOf("leave", "dissolve")) {
                households = households.filterNot { it.id == a.householdId }
                val next = a.copy(householdId = "")
                credentials.save(next); account = next; items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""
                assistant.bind(); planningFacts.bind()
            }
            try {
                val homes = api.households()
                val next = requireNotNull(account).copy(householdId = homes.firstOrNull { it.id == account?.householdId }?.id ?: homes.firstOrNull()?.id.orEmpty())
                credentials.save(next); account = next; households = homes
                if (next.householdId.isNotBlank()) refreshData()
            } catch (failure: Exception) {
                error = "家庭操作已提交，刷新暂未完成；请刷新核对，勿重复提交"
            }
        }
    }
    suspend fun logout() = guarded {
        val a = account
        assistant.clearAccount(a)
        // Remove local access first even if the server is unreachable; never restore another user's cache.
        credentials.save(null); account = null; households = emptyList(); items = emptyList(); shopping = emptyList(); products = emptyList(); productError = null; lastSync = ""; expired = false
        if (a != null) runCatching { apiFactory(a.address, a.token).request("POST", "/api/v1/auth/logout") }
    }
    suspend fun saveItem(item: StockItem, initial: StockItem?) = mutate { api ->
        require(item.name.length <= 80 && InventoryContract.unit(item.unit) != null) { "AI 支持的名称最多 80 字；请核对计量单位，旧记录不会自动截断或猜测换算" }
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
        require(item.name.length <= 80 && InventoryContract.amount(BigDecimal.valueOf(quantity).toPlainString(), 3, true) != null && InventoryContract.unit(item.unit) != null) { "采购名称最多 80 字、数量最多三位小数，请核对单位" }
        val existing = shopping.firstOrNull { !it.purchased && it.sourceId == item.id }
        if (existing != null) api.request("PATCH", "$root/shopping-list/items/${existing.id}", JSONObject().put("quantity", BigDecimal.valueOf(quantity).toPlainString()))
        else api.request("POST", "$root/shopping-list/items", JSONObject().put("id", requestId).put("source_inventory_item_id", item.id)
            .put("name", item.name).put("quantity", BigDecimal.valueOf(quantity).toPlainString()).put("unit", item.unit))
    }
    suspend fun saveShopping(id: String, name: String, quantity: Double, unit: String, creating: Boolean, sourceId: String = "") = mutate {
        require(name.trim().length in 1..80 && InventoryContract.unit(unit) != null && InventoryContract.amount(BigDecimal.valueOf(quantity).toPlainString(), 3, true) != null) { "请核对名称、单位及最多三位小数的采购数量" }
        val json = JSONObject().put("name", name.trim()).put("quantity", BigDecimal.valueOf(quantity).toPlainString()).put("unit", InventoryContract.unit(unit))
        if (creating) json.put("id", id)
        if (creating && sourceId.isNotBlank()) {
            require(items.any { item -> item.id == sourceId && item.name.trim() == name.trim() && InventoryContract.unit(item.unit) == InventoryContract.unit(unit) }) { "关联批次的名称或单位不匹配，请重新核对；新物品请明确选择暂无关联" }
            json.put("source_inventory_item_id", sourceId)
        }
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
