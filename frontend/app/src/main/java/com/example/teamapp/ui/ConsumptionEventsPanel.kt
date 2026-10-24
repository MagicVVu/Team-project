package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneId

@Composable
internal fun ConsumptionEventsPanel(cloud: CloudStore, initialBatch: String = "") {
    val s = rememberUiStrings()
    val scope = rememberCoroutineScope()
    var rows by remember(cloud.scopeKey) { mutableStateOf<List<JSONObject>>(emptyList()) }
    var total by remember(cloud.scopeKey) { mutableIntStateOf(0) }
    var nextOffset by remember(cloud.scopeKey) { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var timezone by remember { mutableStateOf("") }
    var batch by rememberSaveable(cloud.scopeKey) { mutableStateOf(initialBatch) }
    var receipt by remember { mutableStateOf<JSONObject?>(null) }
    fun load(reset: Boolean) {
        if (loading) return
        loading = true
        scope.launch {
            try {
                timezone = cloud.capabilities().getString("household_timezone")
                val offset = if (reset) 0 else nextOffset
                val page = cloud.readHousehold("consumption-events?limit=100&offset=$offset")
                val incoming = page.getJSONArray("items").objects()
                rows = ((if (reset) emptyList() else rows) + incoming).distinctBy { it.getString("id") }
                total = page.getInt("total"); error = ""
                nextOffset = if (incoming.isEmpty()) total else page.optInt("offset", offset) + incoming.size
            } catch (failure: Exception) { error = failure.message.orEmpty() }
            finally { loading = false }
        }
    }
    LaunchedEffect(cloud.scopeKey) { load(true) }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 18.dp).testTag("consumption-events"), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
        item {
            Text(s.tr("真实消费流水", "Recorded consumption"), style = MaterialTheme.typography.titleLarge)
            Text(s.tr("这里只展示 Consumed；丢弃和盘点调整不计入。分页事件不能证明每日记录完整，未记录日期不补零。", "Consumed events only; discards and adjustments are excluded. A paged ledger does not prove complete daily coverage. Missing dates are not zero."), style = MaterialTheme.typography.bodySmall)
            Text(s.tr("家庭时区：", "Household timezone: ") + timezone)
            ContractChoice(s.tr("批次筛选", "Batch"), listOf(Triple("", "全部批次", "All batches")) + cloud.items.map { Triple(it.id, "${it.name} · ${it.location} · ${it.id.take(8)}", "${it.name} · ${it.location} · ${it.id.take(8)}") }, batch) { batch = it }
            OutlinedButton(onClick = { load(true) }, enabled = !loading) { Text(s.tr("刷新流水", "Refresh ledger")) }
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (error.isNotBlank()) Text(if (s.english) "Could not read the ledger. Your records remain unchanged." else error, color = MaterialTheme.colorScheme.error)
            Text(s.tr("已读取 ${rows.size} / $total 条消费事件", "Loaded ${rows.size} of $total consumption events"), style = MaterialTheme.typography.labelMedium)
            if (nextOffset >= total && rows.size < total) Text(s.tr("分页期间记录可能变化，已读取条目不足总数，请刷新核对。", "Records may have changed during paging. Fewer unique events were loaded than the total; refresh to verify."), style = MaterialTheme.typography.bodySmall)
        }
        val visible = rows.filter { batch.isBlank() || it.getString("inventory_item_id") == batch }
        if (!loading && visible.isEmpty()) item { Text(s.tr("当前已读取的数据中没有匹配的消费事件。", "No matching event in the data loaded so far.")) }
        items(visible, key = { it.getString("id") }) { event ->
            val itemId = event.getString("inventory_item_id")
            AlignmentCard(cloud.items.firstOrNull { it.id == itemId }?.name ?: itemId) {
                Text("${event.getString("quantity")} ${event.getString("unit")}", style = MaterialTheme.typography.titleMedium)
                val time = runCatching { OffsetDateTime.parse(event.getString("occurred_at")).atZoneSameInstant(ZoneId.of(timezone)).toString() }.getOrElse { event.getString("occurred_at") }
                Text(time, style = MaterialTheme.typography.bodySmall)
                Text(s.tr("操作前 → 操作后：", "Before → after: ") + "${event.optJSONObject("before")?.stringOrEmpty("quantity")} → ${event.optJSONObject("after")?.stringOrEmpty("quantity")} ${event.getString("unit")}")
                Text(s.tr("事件：", "Event: ") + event.getString("id"), style = MaterialTheme.typography.labelSmall)
                TextButton(onClick = { scope.launch { runCatching { cloud.operationReceipt(event.getString("operation_id")) }.onSuccess { receipt = it }.onFailure { error = it.message.orEmpty() } } }) { Text(s.tr("查看原业务回执", "View original receipt")) }
            }
        }
        if (nextOffset < total) item { OutlinedButton(onClick = { load(false) }, enabled = !loading, modifier = Modifier.fillMaxWidth()) { Text(s.tr("继续读取消费事件", "Load more consumption events")) } }
    }
    receipt?.let { value -> AlertDialog(onDismissRequest = { receipt = null }, title = { Text(s.tr("业务回执", "Operation receipt")) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(s.tr("状态：已执行", "Status: committed")); Text(value.getString("action")); Text(value.getString("committed_at"))
            Text(value.getString("operation_id")); Text(s.tr("关联事件：", "Event IDs: ") + value.getJSONArray("event_ids").toString())
        } }, confirmButton = { TextButton(onClick = { receipt = null }) { Text(s.tr("关闭", "Close")) } }) }
}
