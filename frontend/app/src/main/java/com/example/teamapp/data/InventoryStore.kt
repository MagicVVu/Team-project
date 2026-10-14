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
    private val preferences = context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE)
    private var readFailed = false
    var items by mutableStateOf<List<StockItem>>(emptyList()); private set
    var purchases by mutableStateOf<List<Purchase>>(emptyList()); private set
    var nickname by mutableStateOf("家庭管理员"); private set
    var family by mutableStateOf("温暖的家"); private set
    var locations by mutableStateOf(listOf("冰箱", "厨房", "储物柜", "阳台")); private set
    var reminderDays by mutableIntStateOf(3); private set
    var appearance by mutableStateOf("跟随系统"); private set
    var notifications by mutableStateOf(listOf(true, true, true)); private set
    var storageError by mutableStateOf<String?>(null); private set

    init {
        runCatching {
            preferences.getString("state", null)?.let { saved ->
                val json = JSONObject(saved)
                val array = json.getJSONArray("items")
                items = (0 until array.length()).map { i ->
                    val o = array.getJSONObject(i)
                    StockItem(o.getString("id"), o.getString("name"), o.getDouble("quantity"), o.getString("unit"), o.getString("category"), o.getString("location"), o.getDouble("minimum"), o.optString("expiry"), o.optString("image"), o.optJSONArray("history")?.strings().orEmpty())
                }
                val tasks = json.getJSONArray("purchases")
                purchases = (0 until tasks.length()).map { i -> tasks.getJSONObject(i).let { Purchase(it.getString("itemId"), it.getDouble("quantity")) } }.filter { p -> items.any { it.id == p.itemId } }
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
        if (storageError != null || preferences.getBoolean("ring_preview_inventory_v1", false)) return
        val samples = sampleInventory().filter { sample ->
            items.none { it.id == sample.id || it.name.trim().equals(sample.name, true) }
        }
        items = items + samples
        persist()
        if (storageError == null) preferences.edit().putBoolean("ring_preview_inventory_v1", true).commit()
    }

    fun saveItem(item: StockItem, duplicateMode: String = "新建"): String {
        require(item.name.isNotBlank() && item.unit.isNotBlank() && item.location.isNotBlank())
        require(item.quantity.isFinite() && item.quantity >= 0 && item.minimum.isFinite() && item.minimum >= 0)
        val old = items.firstOrNull { it.id == item.id }
        val duplicate = items.firstOrNull { it.id != item.id && it.name.trim().equals(item.name.trim(), true) }
        if (duplicate != null) {
            require(duplicateMode != "新建") { "该物品已在库存中，请选择入库或盘点。" }
            require(duplicate.unit == item.unit) { "计量单位不同，请先在详情中核对并修改。" }
            val quantity = if (duplicateMode == "入库") duplicate.quantity + item.quantity else item.quantity
            require(quantity.isFinite())
            items = items.map { if (it.id == duplicate.id) it.copy(quantity = quantity, history = (listOf(stamp("$duplicateMode → ${quantity.display()} ${it.unit}")) + it.history).take(30)) else it }
        } else {
            val updated = item.copy(name = item.name.trim(), history = (listOf(stamp(if (old == null) "首次录入 ${item.quantity.display()} ${item.unit}" else "更新记录 → ${item.quantity.display()} ${item.unit}")) + (old?.history ?: emptyList())).take(30))
            items = if (old == null) items + updated else items.map { if (it.id == item.id) updated else it }
        }
        persist()
        return "${item.name}已保存"
    }
    fun changeQuantity(id: String, delta: Double) {
        updateQuantity(id, delta)
        persist()
    }
    private fun updateQuantity(id: String, delta: Double) {
        val item = items.first { it.id == id }
        val next = item.quantity + delta
        require(delta.isFinite() && next.isFinite() && next >= 0) { "消耗数量不能超过现有库存" }
        items = items.map { if (it.id == id) it.copy(quantity = next, history = (listOf(stamp("${if (delta >= 0) "入库" else "消耗"} ${kotlin.math.abs(delta).display()} ${it.unit} → ${next.display()} ${it.unit}")) + it.history).take(30)) else it }
    }
    fun deleteItem(id: String) { items = items.filterNot { it.id == id }; purchases = purchases.filterNot { it.itemId == id }; persist() }
    fun plan(id: String, quantity: Double): Boolean {
        require(quantity.isFinite() && quantity > 0 && items.any { it.id == id })
        val exists = purchases.any { it.itemId == id }
        purchases = purchases.filterNot { it.itemId == id } + Purchase(id, quantity)
        persist(); return exists
    }
    fun removePlan(id: String) { purchases = purchases.filterNot { it.itemId == id }; persist() }
    fun receive(id: String, quantity: Double) {
        require(quantity.isFinite() && quantity > 0)
        require(purchases.any { it.itemId == id }) { "采购任务已完成或已移除" }
        updateQuantity(id, quantity)
        purchases = purchases.filterNot { it.itemId == id }
        persist()
    }
    fun profile(name: String, home: String) { nickname = name.trim().ifBlank { nickname }; family = home.trim().ifBlank { family }; persist() }
    fun addLocation(name: String) { if (name.isNotBlank() && name.trim() !in locations) locations = locations + name.trim(); persist() }
    fun rules(days: Int, minimums: Map<String, Double>) {
        require(days in 0..365 && minimums.values.all { it.isFinite() && it >= 0 })
        reminderDays = days; items = items.map { it.copy(minimum = minimums[it.id] ?: it.minimum) }; persist()
    }
    fun updateAppearance(value: String) { appearance = value; persist() }
    fun setNotification(index: Int, value: Boolean) { notifications = notifications.mapIndexed { i, old -> if (i == index) value else old }; persist() }
    fun clear() { items = emptyList(); purchases = emptyList(); storageError = null; readFailed = false; persist() }
    fun export(): String = if (readFailed) preferences.getString("state", "{}").orEmpty() else json().toString(2)
    private fun json() = JSONObject().apply {
        put("version", 1); put("nickname", nickname); put("family", family); put("locations", JSONArray(locations)); put("reminderDays", reminderDays); put("appearance", appearance); put("notifications", JSONArray(notifications))
        put("items", JSONArray().apply { items.forEach { i -> put(JSONObject().apply { put("id", i.id); put("name", i.name); put("quantity", i.quantity); put("unit", i.unit); put("category", i.category); put("location", i.location); put("minimum", i.minimum); put("expiry", i.expiry); put("image", i.image); put("history", JSONArray(i.history)) }) } })
        put("purchases", JSONArray().apply { purchases.forEach { put(JSONObject().put("itemId", it.itemId).put("quantity", it.quantity)) } })
    }
    private fun persist() {
        if (storageError != null) return
        if (!preferences.edit().putString("state", json().toString()).commit()) storageError = "保存失败，请检查设备存储空间并导出当前记录。"
    }
    private fun JSONArray.strings() = (0 until length()).map { getString(it) }
}
