package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit

private val factsSections = listOf(
    Triple("preferences", "补货偏好", "Restock preferences"), Triple("stock_verification", "库存盘点", "Stock verification"),
    Triple("coverage", "记录完整性", "Recording coverage"), Triple("risk_facts", "标签与储存", "Label & storage"))

@Composable
internal fun PlanningFactsPanel(cloud: CloudStore, item: StockItem, initialSection: String = "preferences", adjust: () -> Unit = {}) {
    val s = rememberUiStrings()
    val facts = cloud.planningFacts
    var section by rememberSaveable(cloud.scopeKey, item.id) { mutableStateOf(initialSection) }
    LaunchedEffect(cloud.scopeKey, item.id) { facts.bind(); facts.load(item.id) }
    val document = facts.document(item.id)
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp).testTag("planning-facts-panel"),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(item.name, style = MaterialTheme.typography.titleLarge)
        Text("${item.quantityText} ${item.unit} · ${item.location}", style = MaterialTheme.typography.bodyMedium)
        if (!cloud.signedIn) { Text(s.tr("资料与盘点属于家庭云端功能，请先登录。", "Sign in to manage household planning facts.")); return@Column }
        ContractChoice(s.tr("资料分区", "Section"), factsSections, section) { section = it }
        if (facts.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (facts.error.isNotBlank()) Text(if (s.english) s.tr("", "Could not complete the request. ") + alignmentReason(facts.errorCode, true) else facts.error,
            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("planning-facts-error"))
        if (facts.notice.isNotBlank()) Text(if (s.english) "Request recorded. Refresh to verify the latest facts; stock quantities are unchanged." else facts.notice,
            color = MaterialTheme.colorScheme.primary)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { facts.launch { load(item.id) } }, enabled = !facts.busy) { Text(s.tr("读取最新资料", "Refresh facts")) }
            if (facts.pending[item.id] != null) OutlinedButton(onClick = { facts.launch { replay(item.id) } }, enabled = !facts.busy,
                modifier = Modifier.testTag("planning-replay")) { Text(s.tr("核实原请求", "Recover original")) }
        }
        if (facts.pending[item.id] != null) Text(s.tr("上次写入结果待核实。保留原操作 ID 和原正文，不会新建请求。", "A write is unresolved. Recovery replays the exact original ID and body."))
        if (document != null) {
            Text(s.tr("家庭时区：", "Household timezone: ") + document.getString("household_timezone"), style = MaterialTheme.typography.labelMedium)
            val invalid = document.optJSONArray("invalidated_sections")
            if (invalid != null && invalid.length() > 0) Text(s.tr("待重新核对：", "Review required: ") + (0 until invalid.length()).joinToString { index ->
                val key = invalid.getString(index); factsSections.firstOrNull { it.first == key }?.let { s.tr(it.second, it.third) } ?: key
            }, color = MaterialTheme.colorScheme.error)
            key(cloud.scopeKey, item.id, section) { FactsEditor(cloud, item, section, document, adjust) }
        }
    }
}

@Composable
private fun FactsEditor(cloud: CloudStore, item: StockItem, section: String, document: JSONObject, adjust: () -> Unit) {
    val s = rememberUiStrings()
    val facts = cloud.planningFacts
    val initial = remember { JSONObject(document.toString()) }
    val values = remember { mutableStateMapOf<String, String>().apply {
        val block = initial.optJSONObject(section)
        block?.keys()?.forEach { put(it, block.stringOrEmpty(it)) }
        if (section == "risk_facts" && block == null) put("category", InventoryContract.category(item.category))
        if (section == "stock_verification") { put("quantity", item.quantityText); put("unit", item.unit) }
    } }
    var reviewedFacts by remember { mutableIntStateOf(initial.getInt("facts_version")) }
    var reviewedInventory by remember { mutableIntStateOf(initial.getInt("inventory_version")) }
    var source by rememberSaveable { mutableStateOf("") }
    var localError by remember { mutableStateOf("") }
    var clear by remember { mutableStateOf(false) }
    var calendar by remember { mutableStateOf(false) }
    var physicallyChecked by remember { mutableStateOf(false) }
    val stale = reviewedFacts != document.getInt("facts_version") || reviewedInventory != document.getInt("inventory_version") || item.version != document.getInt("inventory_version")
    val enabled = !facts.busy && !cloud.expired && facts.pending[item.id] == null && !stale
    fun value(key: String) = values[key].orEmpty()
    @Composable fun edit(key: String, zh: String, en: String, numeric: Boolean = false) {
        Field(s.tr(zh, en), value(key), { values[key] = it }, numeric = numeric)
    }
    @Composable fun choice(key: String, zh: String, en: String, options: List<Triple<String, String, String>>) {
        ContractChoice(s.tr(zh, en), options, value(key)) { values[key] = it }
    }
    val triState = listOf(Triple("", "未知", "Unknown"), Triple("true", "是", "Yes"), Triple("false", "否", "No"))
    document.optJSONObject("provenance")?.optJSONObject(section)?.takeIf { section != "coverage" }?.let { provenance ->
        Text(s.tr("最近核对来源：", "Last verified by: ") + provenance.stringOrEmpty("source") + " · " + provenance.stringOrEmpty("recorded_at"),
            style = MaterialTheme.typography.bodySmall)
    }
    if (stale) AlignmentCard(s.tr("资料版本已更新", "Facts have changed")) {
        Text(s.tr("你的输入仍保留。请读取并核对最新资料，确认后才可继续保存。", "Your entries are preserved. Review the latest facts before saving."))
        val latest = document.optJSONObject(section)
        if (latest == null) Text(s.tr("此分区当前未设置", "This section is currently unset"))
        else latest.keys().forEach { field ->
            val label = when(field) {
                "minimum_stock" -> s.tr("规划最低库存", "Planning minimum")
                "coverage_days" -> s.tr("覆盖天数", "Coverage days")
                "lead_days" -> s.tr("提前期", "Lead days")
                "order_unit" -> s.tr("订货单位", "Order unit")
                "pack_size" -> s.tr("包装量", "Pack size")
                "quantity" -> s.tr("已核对数量", "Verified quantity")
                "unit" -> s.tr("单位", "Unit")
                "source" -> s.tr("核对来源", "Source")
                "checked_at" -> s.tr("核对时间", "Checked at")
                else -> field
            }
            Text("$label: " + latest.stringOrEmpty(field).ifBlank { s.tr("未知", "Unknown") }, style = MaterialTheme.typography.bodySmall)
        }
        OutlinedButton(onClick = { reviewedFacts = document.getInt("facts_version"); reviewedInventory = document.getInt("inventory_version"); physicallyChecked = false },
            enabled = item.version == document.getInt("inventory_version")) {
            Text(s.tr("已核对最新版本，保留输入", "Reviewed latest version; keep my entries"))
        }
        if (item.version != document.getInt("inventory_version")) {
            OutlinedButton(onClick = { facts.launch { cloud.refresh(); load(item.id) } }, enabled = !facts.busy && !cloud.busy) { Text(s.tr("刷新库存并保留表单", "Refresh stock and keep this form")) }
        }
    }
    AlignmentCard(factsSections.first { it.first == section }.let { s.tr(it.second, it.third) }) {
        when(section) {
            "preferences" -> {
                Text(s.tr("规划阈值优先于原最低库存。原阈值：${item.minimum.display()} ${item.unit}；修改原阈值后须重新核对。", "Planning preferences override the legacy minimum (${item.minimum.display()} ${item.unit}). Review after stock-rule changes."), style = MaterialTheme.typography.bodySmall)
                edit("minimum_stock", "规划最低库存（可未知）", "Planning minimum (optional)", true)
                edit("coverage_days", "希望覆盖天数（1–365）", "Coverage days (1–365)", true)
                edit("lead_days", "提前期（0–365）", "Lead days (0–365)", true)
                edit("order_unit", "订货单位（与包装量成对填写）", "Order unit (pair with pack size)")
                edit("pack_size", "每订货单位含多少库存单位", "Stock units in one order unit", true)
            }
            "stock_verification" -> {
                val proof = document.optJSONObject("stock_verification")
                Text(proof?.let { "${it.stringOrEmpty("checked_at")} · ${it.stringOrEmpty("source")} · v${it.optInt("inventory_version")}" }
                    ?: s.tr("尚无有效盘点证明", "No stock verification recorded"), style = MaterialTheme.typography.bodySmall)
                Text(s.tr("盘点证明不会改数量。若实际数量不同，请先盘点修正，再刷新并重新核对。", "Verification does not change stock. Correct discrepancies, refresh, then verify again."))
                edit("quantity", "实际核对数量", "Counted quantity", true)
                Text(s.tr("单位：", "Unit: ") + item.unit)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(physicallyChecked, { physicallyChecked = it })
                    Text(s.tr("我已实际盘点当前批次", "I physically counted this batch"))
                }
                OutlinedButton(onClick = adjust, enabled = !facts.busy) { Text(s.tr("盘点修正库存", "Correct stock count")) }
            }
            "coverage" -> {
                val coverage = document.optJSONArray("coverage") ?: JSONArray()
                Text(s.tr("没有消费事件不代表零消费。请逐日核对；今天和未来不可声明完整。", "No event does not mean zero consumption. Verify completed household dates explicitly."))
                Text(s.tr("已登记 ${coverage.length()} 天；以下显示最近 28 天。", "${coverage.length()} dates recorded; showing the latest 28."), style = MaterialTheme.typography.bodySmall)
                coverage.objects().sortedByDescending { it.getString("day") }.take(28).forEach { day ->
                    Text("${day.getString("day")} · " + s.tr(
                        if (day.getBoolean("records_complete")) "记录完整" else "记录不完整", if (day.getBoolean("records_complete")) "Complete" else "Incomplete") +
                        (if (day.getBoolean("stockout")) s.tr(" · 缺货", " · Stockout") else "") +
                        (if (day.getBoolean("unexplained_adjustment")) s.tr(" · 不明调整", " · Unexplained adjustment") else ""), style = MaterialTheme.typography.bodySmall)
                }
                edit("start", "核对开始日期 YYYY-MM-DD", "Start date YYYY-MM-DD")
                OutlinedButton(onClick = { calendar = true }) { Text(s.tr("日历选择已结束日期", "Choose a completed date")) }
                edit("end", "结束日期（空白为单日）", "End date (blank for one date)")
                choice("records_complete", "这些日期记录是否完整", "Are these dates fully recorded?", triState)
                choice("stockout", "这些日期是否缺货", "Was there a stockout?", triState)
                choice("unexplained_adjustment", "是否存在无法解释的调整", "Any unexplained adjustment?", triState)
                Text(s.tr("选择“不完整”可撤销对应日期的完整性声明，不会删除其他日期。", "Choose Incomplete to revoke these dates; other dates remain unchanged."), style = MaterialTheme.typography.bodySmall)
            }
            "risk_facts" -> {
                choice("category", "规划分类", "Planning category", listOf(Triple("unknown", "未知", "Unknown"), Triple("food", "食品", "Food"), Triple("household", "日用品", "Household"), Triple("medicine", "药品", "Medicine")))
                choice("label_date_type", "标签日期类型", "Package date type", listOf(Triple("unknown", "未知", "Unknown"), Triple("use_by", "食用期限", "Use by"), Triple("best_before", "最佳食用期", "Best before"), Triple("expiry", "有效期", "Expiry")))
                choice("label_context_valid", "已核实标签日期及适用条件", "Label date and context verified", triState)
                val storage = listOf(Triple("", "未知", "Unknown"), Triple("ambient", "常温", "Ambient"), Triple("refrigerated", "冷藏", "Refrigerated"), Triple("frozen", "冷冻", "Frozen"))
                choice("storage_condition", "实际储存条件", "Actual storage", storage)
                choice("label_storage_condition", "包装要求的储存条件", "Storage required on label", storage)
                choice("is_opened", "是否已开封", "Is it opened?", triState)
                Text(s.tr("储存条件不从位置名称推断。实际开封日期须走正式开封操作。", "Storage is not inferred from location. Record opening dates through the Open batch action."), style = MaterialTheme.typography.bodySmall)
            }
        }
        Field(s.tr("核对来源（必填）", "Verification source (required)"), source, { source = it })
        if (localError.isNotBlank()) Text(localError, color = MaterialTheme.colorScheme.error)
        Button(onClick = {
            try {
                require(source.isNotBlank() && source.length <= 200) { s.tr("请填写核对来源，最多 200 字", "Enter a source, up to 200 characters") }
                val payload: Any = when(section) {
                    "preferences" -> JSONObject().apply {
                        for (key in listOf("minimum_stock", "pack_size")) {
                            val raw = value(key); if (raw.isBlank()) put(key, JSONObject.NULL) else {
                                require(InventoryContract.amount(raw, positive = key == "pack_size") != null) { s.tr("数量须有效且最多六位小数", "Use a valid amount with up to six decimals") }; put(key, raw)
                            }
                        }
                        for (key in listOf("coverage_days", "lead_days")) {
                            val raw = value(key)
                            val n = raw.toIntOrNull()
                            require(raw.isBlank() || n != null && n in (if (key == "coverage_days") 1..365 else 0..365)) { s.tr("请核对天数范围", "Review the day ranges") }
                            put(key, n ?: JSONObject.NULL)
                        }
                        val rawUnit = value("order_unit"); val pack = value("pack_size")
                        require(rawUnit.isBlank() == pack.isBlank()) { s.tr("订货单位与包装量须一起填写", "Order unit and pack size must be paired") }
                        require(rawUnit.isBlank() || InventoryContract.unit(rawUnit) != null) { s.tr("请使用支持的订货单位", "Use a supported order unit") }
                        put("order_unit", InventoryContract.unit(rawUnit) ?: JSONObject.NULL)
                    }
                    "stock_verification" -> {
                        require(physicallyChecked && InventoryContract.amount(value("quantity")) != null) { s.tr("请实际盘点并核对数量", "Count the stock and check the quantity") }
                        require(InventoryContract.unit(item.unit) != null) { s.tr("请先核对库存单位", "Review the stock unit first") }
                        JSONObject().put("quantity", value("quantity")).put("unit", InventoryContract.unit(item.unit))
                    }
                    "coverage" -> {
                        val start = LocalDate.parse(value("start")); val end = LocalDate.parse(value("end").ifBlank { value("start") })
                        val today = LocalDate.now(ZoneId.of(document.getString("household_timezone")))
                        val count = ChronoUnit.DAYS.between(start, end) + 1
                        require(count in 1..366 && end < today) { s.tr("每次 1–366 个已结束日期，不含今天或未来", "Choose 1–366 completed dates, excluding today and the future") }
                        require(listOf("records_complete", "stockout", "unexplained_adjustment").all { value(it) in listOf("true", "false") }) { s.tr("请明确核对三个记录状态", "Explicitly confirm all three recording states") }
                        JSONArray().apply { repeat(count.toInt()) { offset -> put(JSONObject().put("day", start.plusDays(offset.toLong()).toString())
                            .put("records_complete", value("records_complete").toBoolean()).put("stockout", value("stockout").toBoolean())
                            .put("unexplained_adjustment", value("unexplained_adjustment").toBoolean())) } }
                    }
                    else -> JSONObject().apply {
                        for (key in listOf("category", "label_date_type")) put(key, value(key).ifBlank { "unknown" })
                        for (key in listOf("label_context_valid", "is_opened")) put(key, value(key).takeIf { it in listOf("true", "false") }?.toBoolean() ?: JSONObject.NULL)
                        for (key in listOf("storage_condition", "label_storage_condition")) put(key, value(key).ifBlank { null } ?: JSONObject.NULL)
                        require(!(value("label_context_valid") == "true" && item.expiry.isBlank())) { s.tr("请先编辑库存并填写标签日期", "Edit the item and enter its package date first") }
                        require(!(item.openedAt.isNotBlank() && value("is_opened") == "false")) { s.tr("已有开封日期，不能否认已开封", "An existing opening date cannot be denied") }
                    }
                }
                localError = ""; facts.launch { save(item.id, section, payload, source, reviewedInventory, reviewedFacts) }
            } catch (failure: Exception) { localError = failure.message ?: s.tr("请核对表单", "Review the form") }
        }, enabled = enabled, modifier = Modifier.fillMaxWidth().testTag("planning-save")) { Text(s.tr("确认保存资料", "Confirm and save facts")) }
        if (section != "coverage") TextButton(onClick = { clear = true }, enabled = enabled && source.isNotBlank()) { Text(s.tr("清除此分区资料", "Clear this section")) }
    }
    if (clear) Confirm(s.tr("清除资料", "Clear facts"), s.tr("只清除此分区，不修改库存，也不清除其他分区。", "Only this section will be cleared. Stock and other sections stay intact."), { clear = false }) {
        clear = false; facts.launch { save(item.id, section, null, source, reviewedInventory, reviewedFacts) }
    }
    if (calendar) {
        CoverageDateDialog(LocalDate.now(ZoneId.of(document.getString("household_timezone"))), value("start"),
            dismiss = { calendar = false }, selected = { values["start"] = it.toString(); values["end"] = ""; calendar = false })
    }
}
