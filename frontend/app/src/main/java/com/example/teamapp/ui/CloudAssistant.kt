package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import org.json.JSONObject

@Composable
internal fun CloudAssistant(cloud: CloudStore, initial: String = "", consumed: () -> Unit = {}) {
    val assistant = cloud.assistant
    val scroll = rememberLazyListState()
    var input by rememberSaveable(cloud.scopeKey) { mutableStateOf("") }
    var localError by remember { mutableStateOf("") }
    var confirmId by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(cloud.scopeKey) { assistant.bind(); assistant.launch { connectAndRecover() } }
    fun send(text: String) {
        if (text.isBlank() || assistant.busy || cloud.expired) return
        val active = assistant.entries.lastOrNull()?.takeIf { it.state == AssistantStatus.CLARIFICATION }
        val ordinal = mapOf("第一个" to 0, "第二个" to 1, "第三个" to 2)[text.trim().removeSuffix("。").removeSuffix("！")]
        if (ordinal != null) {
            val candidate = active?.candidates?.getOrNull(ordinal)
            if (candidate != null && "batch_id" in active.allowedFields) {
                input = ""; assistant.launch { clarify(active.requestId, mapOf("batch_id" to candidate.batchId())) }
            } else localError = "当前没有对应的有效候选列表，请重新选择具体物品"
            return
        }
        if (text.trim().startsWith("它") || text.contains("把它")) {
            localError = "当前版本不支持跨提问的“它”，请写出物品名称，或从当前候选批次中选择"
            return
        }
        if (text.length > 1000) { localError = "消息最多 1000 字，不会自动截断"; return }
        input = ""; localError = ""; assistant.launch { this.send(text) }
    }
    LaunchedEffect(initial) { if (initial.isNotBlank()) { send(initial); consumed() } }
    LaunchedEffect(assistant.entries.size) {
        if (assistant.entries.isNotEmpty()) scroll.animateScrollToItem(assistant.entries.lastIndex)
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        Text("家庭 AI 助手 · 确认后才执行", style = MaterialTheme.typography.labelLarge)
        Text("开封、丢弃、自动预测采购及跨提问引用暂不支持。可在库存或清单页面手动管理。", style = MaterialTheme.typography.bodySmall)
        val caps = JSONObject(assistant.capabilities).optJSONObject("actions")
        Text(if (caps == null) "执行能力尚未验证" else listOf("ADD", "MOVE", "CONSUME", "PLAN_ADD", "OPEN", "DISCARD").joinToString(" · ") {
            "${actionLabel(it)}${if (caps.optBoolean(it)) " ✓" else " 暂不支持"}"
        }, style = MaterialTheme.typography.labelSmall, modifier = Modifier.testTag("ai-capabilities"))
        if (assistant.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (assistant.error.isNotBlank() || localError.isNotBlank()) Text(localError.ifBlank { assistant.error }, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        LazyColumn(Modifier.weight(1f).testTag("ai-tasks"), state = scroll, verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
            if (assistant.entries.isEmpty()) item { Text("试试“纸巾还有多少”或“添加两盒牛奶”。") }
            items(assistant.entries, key = { it.requestId }) { entry ->
                AssistantTaskCard(entry, cloud, assistant.busy || cloud.expired,
                    confirm = { confirmId = entry.requestId })
            }
        }
        Row(Modifier.fillMaxWidth()) {
            OutlinedTextField(input, { input = it }, label = { Text("继续问问…") }, modifier = Modifier.weight(1f).testTag("ai-input"))
            TextButton(onClick = { send(input) }, enabled = !assistant.busy && !cloud.expired && input.isNotBlank(), modifier = Modifier.testTag("ai-send")) { Text("发送") }
        }
        Spacer(Modifier.height(12.dp))
    }
    confirmId?.let { id ->
        val entry = assistant.entries.firstOrNull { it.requestId == id }
        if (entry != null) AlertDialog(onDismissRequest = { confirmId = null },
            title = { Text("确认${actionLabel(entry.action)}？") },
            text = { Text("确认后由服务器校验库存版本并执行。若其他成员已更新库存，需要重新核对。") },
            confirmButton = { TextButton(onClick = { confirmId = null; assistant.launch { confirm(id) } }, modifier = Modifier.testTag("ai-final-confirm")) { Text("确认执行") } },
            dismissButton = { TextButton(onClick = { confirmId = null }) { Text("返回核对") } })
    }
}

private fun JSONObject.batchId() = stringOrEmpty("batch_id").ifBlank { stringOrEmpty("id") }
internal fun actionLabel(action: String) = mapOf("ADD" to "添加库存", "MOVE" to "移动", "CONSUME" to "消耗", "PLAN_ADD" to "添加采购", "OPEN" to "开封", "DISCARD" to "丢弃")[action] ?: action
private val fieldLabels = mapOf("name" to "物品名称", "quantity" to "数量", "unit" to "单位", "location" to "存放位置（必填）",
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< Updated upstream
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期", "discard_mode" to "丢弃模式")
=======
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期", "discard_mode" to "丢弃模式（partial / all）")
>>>>>>> Stashed changes
=======
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期")
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期")
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)

@Composable
internal fun AssistantTaskCard(entry: AssistantEntry, cloud: CloudStore, disabled: Boolean, confirm: () -> Unit) {
    val assistant = cloud.assistant
    val id = entry.requestId
    var answers by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    var selectedField by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    Card(Modifier.fillMaxWidth().testTag("ai-task-$id")) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(JSONObject(entry.requestBody).getString("text"), fontWeight = FontWeight.SemiBold)
            Text(entry.state.label, color = if (entry.state == AssistantStatus.COMMITTED) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.testTag("ai-state-$id"))
            if (entry.reply.isNotBlank()) {
                if (entry.state in setOf(AssistantStatus.COMMITTED, AssistantStatus.CANCELLED)) Text("AI 生成时的回复（历史记录）", style = MaterialTheme.typography.labelSmall)
                Text(entry.reply)
            }
            if (entry.notice.isNotBlank()) Text(entry.notice, style = MaterialTheme.typography.bodySmall)
            if (entry.errorCode.isNotBlank() && !entry.notice.contains(entry.errorCode)) Text("原因：${entry.errorCode}", style = MaterialTheme.typography.bodySmall)
            if (entry.state == AssistantStatus.CLARIFICATION) {
                if ("batch_id" in entry.allowedFields) entry.candidates.forEachIndexed { index, c ->
                    OutlinedButton(onClick = { assistant.launch { clarify(id, mapOf("batch_id" to c.batchId())) } }, enabled = !disabled,
                        modifier = Modifier.fillMaxWidth().testTag("ai-candidate-$id-$index")) {
                        Text("${index + 1}. ${c.stringOrEmpty("name")} · ${c.stringOrEmpty("quantity")} ${c.stringOrEmpty("unit")} · ${c.stringOrEmpty("location").ifBlank { c.stringOrEmpty("storage_location") }}\n购入 ${c.stringOrEmpty("purchased_at").ifBlank { "未知" }} · 有效期 ${c.stringOrEmpty("label_expiry").ifBlank { "未知" }} · 版本 ${c.optInt("version")} · ${c.batchId().take(8)}")
                    }
                }
                entry.allowedFields.filter { it != "batch_id" && it in fieldLabels }.forEach { field ->
                    OutlinedTextField(if (selectedField == field) answers else "", { selectedField = field; answers = it }, label = { Text(fieldLabels[field] ?: field) },
                        enabled = !disabled && entry.clarificationBody.isBlank(), modifier = Modifier.fillMaxWidth().testTag("ai-clarify-$field-$id"))
                }
                if (selectedField.isNotBlank()) TextButton(onClick = { assistant.launch { clarify(id, mapOf(selectedField to answers)) } }, enabled = !disabled && answers.isNotBlank()) { Text("继续澄清") }
            }
            if (entry.draftId.isNotBlank()) {
                val command = entry.command
                Text("${actionLabel(entry.action)}：${command.stringOrEmpty("name")}", fontWeight = FontWeight.SemiBold)
                val before = entry.preview.optJSONObject("before")
                val after = entry.preview.optJSONObject("after")
                if (before != null || after != null) Text("生成时的预览（尚非执行结果）\n" +
                    (before?.let { "原记录：${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} · ${it.stringOrEmpty("location")}\n" } ?: "") +
                    (after?.let { "原草稿预计：${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} · ${it.stringOrEmpty("location")}" } ?: ""),
                    style = MaterialTheme.typography.bodySmall)
                val target = cloud.items.firstOrNull { it.id == command.stringOrEmpty("batch_id") }
                if (entry.action in listOf("MOVE", "CONSUME") && entry.state in setOf(AssistantStatus.PENDING, AssistantStatus.CONFLICT)) {
                    Text("批次 ${command.stringOrEmpty("batch_id").take(8)} · 原版本 ${command.optInt("expected_version")}", style = MaterialTheme.typography.bodySmall)
                    if (target != null) Text("当前缓存：${target.quantity.display()} ${target.unit} · ${target.location}（提交时由服务器复核）")
                    else Text("当前批次库存未同步，请刷新核对")
                    if (entry.action == "MOVE") Text("原位置 ${target?.location ?: "待核对"} → ${entry.edits["to_location"] ?: command.stringOrEmpty("to_location")}")
<<<<<<< HEAD
<<<<<<< HEAD
                    if (entry.action == "OPEN") Text("开封日期：${before?.stringOrEmpty("opened_at")?.ifBlank { "未开封" } ?: "待核对"} → ${entry.edits["opened_at"] ?: command.stringOrEmpty("opened_at")}；数量与位置不变")
<<<<<<< Updated upstream
                    if (entry.action == "DISCARD") Text("丢弃模式：${entry.edits["discard_mode"] ?: command.stringOrEmpty("discard_mode")}；all 使用草稿生成时的整批量，提交时重新核对")
=======
                    if (entry.action == "DISCARD") Text("丢弃模式：${entry.edits["discard_mode"] ?: command.stringOrEmpty("discard_mode")}；all 必须与服务器当前整批数量一致")
>>>>>>> Stashed changes
                    if (entry.action in listOf("CONSUME", "DISCARD")) {
=======
                    if (entry.action == "CONSUME") {
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
                    if (entry.action == "CONSUME") {
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
                        val amount = (entry.edits["quantity"] ?: command.stringOrEmpty("quantity")).toBigDecimalOrNull()
                        val unit = entry.edits["unit"] ?: command.stringOrEmpty("unit")
                        Text("消耗：${amount ?: "待填写"} $unit")
                        if (target != null && amount != null && unit == target.unit) Text("预计剩余：${java.math.BigDecimal.valueOf(target.quantity).subtract(amount).toPlainString()} $unit（以正式回执为准）")
                        else Text("预计剩余需按库存单位核算，以正式回执为准")
                    }
                }
                if (entry.state == AssistantStatus.PENDING && entry.commitBody.isBlank()) {
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< Updated upstream
                    if (entry.action == "DISCARD") Row {
                        TextButton(onClick = { assistant.edit(id, "discard_mode", "partial") }, enabled = !disabled) { Text("丢弃指定数量") }
                        TextButton(onClick = {
                            assistant.edit(id, "discard_mode", "all")
                            assistant.edit(id, "quantity", before!!.getString("quantity"))
                            assistant.edit(id, "unit", before.getString("unit"))
                        }, enabled = !disabled && before != null && before.has("quantity") && before.has("unit")) { Text("丢弃本批全部") }
=======
                    if (entry.action == "DISCARD") {
                        Row {
                            TextButton(onClick = { assistant.edit(id, "discard_mode", "partial") }, enabled = !disabled) { Text("丢弃指定数量") }
                            TextButton(onClick = {
                                assistant.edit(id, "discard_mode", "all")
                                assistant.edit(id, "quantity", before!!.getString("quantity"))
                                assistant.edit(id, "unit", before.getString("unit"))
                            }, enabled = !disabled && before != null && before.has("quantity") && before.has("unit")) { Text("丢弃本批全部") }
                        }
>>>>>>> Stashed changes
                    }
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
                    entry.editableFields.forEach { field ->
                        OutlinedTextField(entry.edits[field] ?: command.stringOrEmpty(field),
                            { value -> assistant.edit(id, field, value) }, label = { Text(fieldLabels[field] ?: field) }, enabled = !disabled,
                            modifier = Modifier.fillMaxWidth().testTag("ai-edit-$field-$id"))
                    }
                    Row {
                        Button(onClick = confirm, enabled = !disabled && JSONObject(assistant.capabilities).optJSONObject("actions")?.optBoolean(entry.action) == true,
                            modifier = Modifier.testTag("ai-confirm-$id")) { Text("核对并确认") }
                        TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled, modifier = Modifier.testTag("ai-cancel-$id")) { Text("取消草稿") }
                    }
                } else if (entry.state == AssistantStatus.UNSUPPORTED && entry.commitBody.isBlank()) {
                    Text("草稿数量：${command.stringOrEmpty("quantity")} ${command.stringOrEmpty("unit")} · 位置：${command.stringOrEmpty("location").ifBlank { command.stringOrEmpty("to_location") }}")
                    Text("当前版本暂不支持自动执行，请前往库存或清单页面核对。")
                    TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled) { Text("取消草稿") }
                }
            }
            if (entry.receipt.isNotBlank()) {
                val receipt = JSONObject(entry.receipt)
                Text("服务器已确认${actionLabel(receipt.getString("action"))}", fontWeight = FontWeight.SemiBold, modifier = Modifier.testTag("ai-receipt-$id"))
                val result = receipt.getJSONObject("result")
                val resource = result.optJSONObject("inventory_item") ?: result.optJSONObject("shopping_item")
                resource?.let { Text("${it.stringOrEmpty("name")} · ${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} ${it.stringOrEmpty("storage_location")}") }
                Text("操作凭证 ${receipt.getString("operation_id")}\n${receipt.getString("committed_at")}", style = MaterialTheme.typography.labelSmall)
            }
            if (entry.state == AssistantStatus.CONFLICT) Text("库存或草稿版本已变化。请刷新库存并重新提问生成新草稿；不会替换版本自动执行。")
            if (entry.state in listOf(AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.FAILED, AssistantStatus.CONFLICT) || entry.refreshNeeded) {
                TextButton(onClick = { assistant.launch { if (entry.taskId.isBlank()) retryMessage(id) else recover(id) } }, enabled = !disabled, modifier = Modifier.testTag("ai-recover-$id")) { Text(if (entry.refreshNeeded) "重新刷新库存" else "核实并恢复") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.commitBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryCommit(id) } }, enabled = !disabled) { Text("用原确认请求恢复提交") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.clarificationBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryClarification(id) } }, enabled = !disabled) { Text("恢复原澄清") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.cancelBody.isNotBlank()) TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled) { Text("恢复原取消请求") }
            }
        }
    }
}
