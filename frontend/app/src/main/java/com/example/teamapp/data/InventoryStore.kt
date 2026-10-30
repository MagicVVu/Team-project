package com.example.teamapp.data

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class InventoryStore(context: Context) {
    val cloud = CloudStore(context)
    // Deliberately excluded from preferences, export and all cloud requests.
    internal val inventoryPreviews = InventoryPreviewStore()
    internal val inventoryPreviewScope get() = cloud.scopeKey.ifBlank { "local" }
    private val preferences = context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE)
    private var readFailed = false
    private var localItems by mutableStateOf<List<StockItem>>(emptyList())
    var items: List<StockItem>
        get() = if (cloud.signedIn) cloud.items else localItems
        private set(value) { localItems = value }
    private var localPurchases by mutableStateOf<List<Purchase>>(emptyList())
    var purchases: List<Purchase>
        get() = if (cloud.signedIn) cloud.shopping.filterNot { it.purchased }.map { Purchase(it.sourceId.ifBlank { "shopping:${it.id}" }, it.quantity) } else localPurchases
        private set(value) { localPurchases = value }
    private var localNickname by mutableStateOf("家庭管理员")
    var nickname: String
        get() = cloud.account?.displayName ?: localNickname
        private set(value) { localNickname = value }
    private var localFamily by mutableStateOf("温暖的家")
    var family: String
        get() = if (cloud.signedIn) cloud.household?.name ?: "请创建或加入家庭" else localFamily
        private set(value) { localFamily = value }
    var locations by mutableStateOf(listOf("冰箱", "厨房", "储物柜", "阳台")); private set
    var reminderDays by mutableIntStateOf(3); private set
    var appearance by mutableStateOf("跟随系统"); private set
    var language by mutableStateOf(preferences.getString("ui_language", "zh-CN").let { if (it == "en") "en" else "zh-CN" }); private set
    var notifications by mutableStateOf(listOf(true, true, true)); private set
    var storageError by mutableStateOf<String?>(null); private set

    init {
        runCatching {
            preferences.getString("state", null)?.let { saved ->
                val json = JSONObject(saved)
                val array = json.getJSONArray("items")
                items = (0 until array.length()).map { i ->
                    val o = array.getJSONObject(i)
                    val status = o.optString("lifecycleStatus", "ACTIVE")
                    StockItem(o.getString("id"), o.getString("name"), o.optDouble("quantity", if (status == "ACTIVE") 1.0 else 0.0), o.getString("unit"), o.getString("category"), o.getString("location"), o.getDouble("minimum"), o.optString("expiry"), o.optString("image"), o.optJSONArray("history")?.strings().orEmpty(), o.optString("purchasedAt"), openedAt = o.optString("openedAt"), lifecycleStatus = status, quantityExact = o.optString("quantityExact"), specification = o.optString("specification"), individualRecord = json.optInt("version", 1) >= 2)
                }.flatMap { it.individualItems() }
                val tasks = json.getJSONArray("purchases")
                purchases = (0 until tasks.length()).map { i -> tasks.getJSONObject(i).let { Purchase(it.getString("itemId"), it.getDouble("quantity")) } }.filter { p -> localItems.any { it.id == p.itemId } }
                nickname = json.optString("nickname", nickname)
                family = json.optString("family", family)
                locations = json.optJSONArray("locations")?.strings() ?: locations
                reminderDays = json.optInt("reminderDays", 3).coerceIn(0, 365)
                appearance = json.optString("appearance", appearance)
                json.optJSONArray("notifications")?.let { notifications = (0..2).map { i -> it.optBoolean(i, true) } }
            }
        }.onFailure { readFailed = true; storageError = "本机数据读取失败，原始数据已保留，请先导出备份，避免覆盖。" }
    }

    private fun stamp(text: String) = "${LocalDateTime.now().format(DateTimeFormatter.ofPattern("MM-dd HH:mm"))} · $text"
    internal fun addPreviewInventoryOnce() {
        if (cloud.signedIn) return
        if (storageError != null || preferences.getBoolean("ring_preview_inventory_v1", false)) return
        val samples = sampleInventory().filter { sample ->
            items.none { it.id == sample.id || it.name.trim().equals(sample.name, true) }
        }
        items = items + samples.flatMap { it.individualItems() }
        persist()
        if (storageError == null) preferences.edit().putBoolean("ring_preview_inventory_v1", true).commit()
    }

    fun saveItem(item: StockItem, duplicateMode: String = "新建"): String {
        require(!cloud.signedIn) { "请通过云端库存操作保存" }
        require(item.name.isNotBlank() && item.unit.isNotBlank() && item.location.isNotBlank())
        require(item.quantity.isFinite() && item.quantity >= 0 && item.minimum.isFinite() && item.minimum >= 0)
        val old = items.firstOrNull { it.id == item.id }
        if (old == null) {
            require(item.quantity > 0)
            val records = item.withIntakeDate().copy(name = item.name.trim()).individualItems().map {
                it.copy(history = (listOf(stamp("首次录入")) + it.history).take(30))
            }
            items = items + records
        } else {
            val updated = item.copy(name = item.name.trim(), quantity = old.quantity, quantityExact = "", individualRecord = true,
                history = (listOf(stamp("更新物品资料")) + old.history).take(30))
            items = items.map { if (it.id == item.id) updated else it }
        }
        persist()
        return "${item.name}已保存"
    }
    fun changeQuantity(id: String, delta: Double) {
        require(!cloud.signedIn) { "请通过云端库存操作保存" }
        updateQuantity(id, delta)
        persist()
    }
    private fun updateQuantity(id: String, delta: Double) {
        val item = items.first { it.id == id }
        if (item.individualRecord && delta > 0) {
            val receipt = item.copy(id = java.util.UUID.randomUUID().toString(), quantity = delta, quantityExact = "", individualRecord = false,
                lifecycleStatus = "ACTIVE", openedAt = "", history = listOf(stamp("新增入库")))
            items = items + receipt.individualItems()
            return
        }
        val next = item.quantity + delta
        require(delta.isFinite() && next.isFinite() && next >= 0) { "消耗数量不能超过现有库存" }
        require(!item.individualRecord || next in listOf(0.0, 1.0)) { "每次只可处理这件物品" }
        items = items.map { if (it.id == id) it.copy(quantity = next, lifecycleStatus = if (next == 0.0) "FINISHED" else "ACTIVE", history = (listOf(stamp("${if (delta >= 0) "入库" else "消耗"} ${kotlin.math.abs(delta).display()} ${it.unit} → ${next.display()} ${it.unit}")) + it.history).take(30)) else it }
    }
    fun deleteItem(id: String) { require(!cloud.signedIn); items = items.filterNot { it.id == id }; purchases = purchases.filterNot { it.itemId == id }; persist() }
    fun plan(id: String, quantity: Double): Boolean {
        require(!cloud.signedIn)
        require(quantity.isFinite() && quantity > 0 && items.any { it.id == id })
        val exists = purchases.any { it.itemId == id }
        purchases = purchases.filterNot { it.itemId == id } + Purchase(id, quantity)
        persist(); return exists
    }
    fun removePlan(id: String) { require(!cloud.signedIn); purchases = purchases.filterNot { it.itemId == id }; persist() }
    fun receive(id: String, quantity: Double) {
        require(!cloud.signedIn)
        require(quantity.isFinite() && quantity > 0)
        require(purchases.any { it.itemId == id }) { "采购任务已完成或已移除" }
        updateQuantity(id, quantity)
        purchases = purchases.filterNot { it.itemId == id }
        persist()
    }
    fun profile(name: String, home: String) { require(!cloud.signedIn); nickname = name.trim().ifBlank { nickname }; family = home.trim().ifBlank { family }; persist() }
    fun addLocation(name: String) { if (name.isNotBlank() && name.trim() !in locations) locations = locations + name.trim(); persist() }
    fun rules(days: Int, minimums: Map<String, Double>) {
        require(!cloud.signedIn)
        require(days in 0..365 && minimums.values.all { it.isFinite() && it >= 0 })
        reminderDays = days; items = items.map { it.copy(minimum = minimums[it.id] ?: it.minimum) }; persist()
    }
    fun updateAppearance(value: String) { appearance = value; persist() }
    fun updateLanguage(value: String): Boolean {
        require(value in setOf("zh-CN", "en"))
        val saved = preferences.edit().putString("ui_language", value).commit()
        if (saved) language = value
        return saved
    }
    fun setNotification(index: Int, value: Boolean) { notifications = notifications.mapIndexed { i, old -> if (i == index) value else old }; persist() }
    fun clear() { require(!cloud.signedIn) { "云端家庭不支持批量清空，请逐项核对后删除" }; items = emptyList(); purchases = emptyList(); storageError = null; readFailed = false; persist() }
    fun export(): String = if (cloud.signedIn) JSONObject().put("mode", "cloud").put("householdId", cloud.account?.householdId)
        .put("items", JSONArray(items.map { it.toCloudJson().apply { remove("quantity") } })).put("shopping", JSONArray(cloud.shopping.map {
            JSONObject().put("id", it.id).put("name", it.name).put("quantity", it.quantity).put("unit", it.unit).put("purchased", it.purchased)
        })).toString(2) else if (readFailed) preferences.getString("state", "{}").orEmpty() else json().toString(2)

    suspend fun saveItemSynced(item: StockItem, initial: StockItem?, mode: String = "新建"): String {
        if (!cloud.signedIn) return saveItem(item, mode)
        cloud.saveItem(item, initial)
        return "${item.name}已保存到家庭库存"
    }
    suspend fun changeQuantitySynced(item: StockItem, delta: Double, operationId: String) {
        if (cloud.signedIn) cloud.adjust(item, delta, operationId) else changeQuantity(item.id, delta)
    }
    suspend fun deleteItemSynced(item: StockItem, operationId: String) {
        if (cloud.signedIn) cloud.delete(item, operationId) else deleteItem(item.id)
    }
    suspend fun planSynced(item: StockItem, quantity: Double, requestId: String) {
        if (cloud.signedIn) cloud.plan(item, quantity, requestId) else plan(item.id, quantity)
    }
    suspend fun profileSynced(name: String, home: String) {
        if (cloud.signedIn) cloud.profile(name, home) else profile(name, home)
    }
    suspend fun rulesSynced(days: Int, minimums: Map<String, Double>) {
        if (cloud.signedIn) { cloud.minimums(minimums); reminderDays = days; persist() } else rules(days, minimums)
    }
    private fun json() = JSONObject().apply {
        put("version", 2); put("nickname", localNickname); put("family", localFamily); put("locations", JSONArray(locations)); put("reminderDays", reminderDays); put("appearance", appearance); put("notifications", JSONArray(notifications))
        put("items", JSONArray().apply { localItems.forEach { i -> put(JSONObject().apply { put("id", i.id); put("name", i.name); put("unit", i.unit); put("category", i.category); put("location", i.location); put("minimum", i.minimum); put("expiry", i.expiry); put("image", i.image); put("purchasedAt", i.purchasedAt); put("openedAt", i.openedAt); put("lifecycleStatus", i.lifecycleStatus); put("specification", i.specification); put("history", JSONArray(i.history)) }) } })
        put("purchases", JSONArray().apply { localPurchases.forEach { put(JSONObject().put("itemId", it.itemId).put("quantity", it.quantity)) } })
    }
    private fun persist() {
        if (storageError != null) return
        if (!preferences.edit().putString("state", json().toString()).commit()) storageError = "保存失败，请检查设备存储空间并导出当前记录。"
    }
    private fun JSONArray.strings() = (0 until length()).map { getString(it) }
}
