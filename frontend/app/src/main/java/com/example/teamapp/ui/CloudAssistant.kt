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
internal fun CloudAssistant(cloud: CloudStore, initial: String = "", consumed: () -> Unit = {}, showIntro: Boolean = true) {
    val assistant = cloud.assistant
    val scroll = rememberLazyListState()
    var input by rememberSaveable(cloud.scopeKey) { mutableStateOf("") }
    var localError by remember { mutableStateOf("") }
    var confirmId by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(cloud.scopeKey) { assistant.bind(); assistant.launch { connectAndRecover() } }
    fun send(text: String) {
        if (text.isBlank() || assistant.busy || cloud.expired) return
        if (!assistant.conversationEnabled) {
            val active = assistant.activeEntry?.takeIf { it.state == AssistantStatus.CLARIFICATION }
            val answers = active?.let { ClarificationReplies.resolve(text, it.allowedFields.toSet(), it.candidates.map { c -> c.batchId() }) }
            if (answers != null) { input = ""; assistant.launch { clarify(active.requestId, answers) }; return }
            if (text.trim().startsWith("它") || text.contains("把它")) {
                localError = "当前服务尚未启用连续引用，请写明物品名称或使用候选按钮"; return
            }
        }
        if (text.length > 1000) { localError = "消息最多 1000 字，不会自动截断"; return }
        input = ""; localError = ""; assistant.launch { this.send(text) }
    }
    LaunchedEffect(initial) { if (initial.isNotBlank()) { send(initial); consumed() } }
    LaunchedEffect(assistant.entries.size) {
        if (assistant.entries.isNotEmpty()) scroll.animateScrollToItem(assistant.entries.lastIndex)
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        if (showIntro) MewChatIntro()
        Text("家庭 AI 助手 · 确认后才执行", style = MaterialTheme.typography.labelLarge)
        Text(if (assistant.conversationEnabled) "可以直接补充当前任务；修改草稿后仍需确认才执行。" else "当前服务按独立任务处理；候选按钮和补充表单仍可使用。", style = MaterialTheme.typography.bodySmall)
        assistant.activeEntry?.let { Text("当前任务：${JSONObject(it.requestBody).optString("text").take(50)}", style = MaterialTheme.typography.labelMedium) }
        if (assistant.referenceLabel.isNotBlank()) Text(assistant.referenceLabel, style = MaterialTheme.typography.bodySmall)
        if (assistant.conversationEnabled) TextButton(onClick = { send("开始新任务") }, enabled = !assistant.busy) { Text("开始新任务") }
        val caps = JSONObject(assistant.capabilities).optJSONObject("actions")
        Text(if (caps == null) "执行能力尚未验证" else listOf("ADD", "MOVE", "CONSUME", "PLAN_ADD", "OPEN", "DISCARD").joinToString(" · ") {
            "${actionLabel(it)}${if (caps.optBoolean(it)) " ✓" else " 暂不支持"}"
        }, style = MaterialTheme.typography.labelSmall, modifier = Modifier.testTag("ai-capabilities"))
        if (assistant.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(assistant.phase, style = MaterialTheme.typography.bodySmall) }
        if (assistant.error.isNotBlank() || localError.isNotBlank()) Text(localError.ifBlank { assistant.error }, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        LazyColumn(Modifier.weight(1f).testTag("ai-tasks"), state = scroll, verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
            if (assistant.entries.isEmpty()) item { Text("试试“纸巾还有多少”或“添加两盒牛奶”。") }
            items(assistant.entries, key = { it.requestId }) { entry ->
                AssistantTaskCard(entry, cloud, assistant.busy || cloud.expired,
                    confirm = { assistant.launch { validateDraft(entry.requestId); if (assistant.error.isBlank()) confirmId = entry.requestId } })
            }
        }
        Row(Modifier.fillMaxWidth()) {
            OutlinedTextField(input, { input = it }, label = { Text("输入问题…") }, modifier = Modifier.weight(1f).testTag("ai-input"))
            TextButton(onClick = { send(input) }, enabled = !assistant.busy && !cloud.expired && input.isNotBlank(), modifier = Modifier.testTag("ai-send")) { Text("发送") }
        }
        Spacer(Modifier.height(12.dp))
    }
    confirmId?.let { id ->
        val entry = assistant.entries.firstOrNull { it.requestId == id }
        if (entry != null) AlertDialog(onDismissRequest = { confirmId = null },
            title = { Text("确认${actionLabel(entry.action)}？") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${actionLabel(entry.action)}：${entry.command.stringOrEmpty("name")}")
                    val command = entry.command
                    if (entry.action in setOf("ADD", "CONSUME", "DISCARD", "PLAN_ADD"))
                        Text("数量：${command.stringOrEmpty("quantity")} ${command.stringOrEmpty("unit")}" + if (command.optString("discard_mode") == "all") "（全部）" else "")
                    if (entry.action == "MOVE") Text("目标位置：${command.stringOrEmpty("to_location")}")
                    if (entry.action == "ADD") Text("存放位置：${command.stringOrEmpty("location")}")
                    if (entry.action == "OPEN") Text("开封日期：${command.stringOrEmpty("opened_at")}，数量不变")
                    Text("尚未执行。确认后服务器仍会核对库存和草稿版本；有变化时须重新核对。")
                }
            },
            confirmButton = { TextButton(onClick = { confirmId = null; assistant.launch { confirm(id) } }, modifier = Modifier.testTag("ai-final-confirm")) { Text("确认执行") } },
            dismissButton = { TextButton(onClick = { confirmId = null }) { Text("返回核对") } })
    }
}

private fun JSONObject.batchId() = stringOrEmpty("batch_id").ifBlank { stringOrEmpty("id") }
internal fun actionLabel(action: String) = mapOf("ADD" to "添加库存", "MOVE" to "移动", "CONSUME" to "消耗", "PLAN_ADD" to "添加采购", "OPEN" to "开封", "DISCARD" to "丢弃")[action] ?: action
private val fieldLabels = mapOf("name" to "物品名称", "quantity" to "数量", "unit" to "单位", "location" to "存放位置（必填）",
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期")

@Composable
internal fun AssistantTaskCard(entry: AssistantEntry, cloud: CloudStore, disabled: Boolean, confirm: () -> Unit) {
    val assistant = cloud.assistant
    val id = entry.requestId
    val historical = entry.taskId.isNotBlank() && assistant.entries.lastOrNull { it.taskId == entry.taskId }?.requestId != id
    var details by rememberSaveable(id) { mutableStateOf(false) }
    var answers by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    var selectedField by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    Card(Modifier.fillMaxWidth().testTag("ai-task-$id")) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(JSONObject(entry.requestBody).getString("text"), fontWeight = FontWeight.SemiBold)
            Text(if (historical) "该任务的历史消息" else entry.state.label, color = if (entry.state == AssistantStatus.COMMITTED) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.testTag("ai-state-$id"))
            if (entry.reply.isNotBlank()) {
                if (entry.state in setOf(AssistantStatus.COMMITTED, AssistantStatus.CANCELLED)) Text("AI 生成时的回复（历史记录）", style = MaterialTheme.typography.labelSmall)
                Text(entry.reply)
            }
            if (entry.notice.isNotBlank()) Text(entry.notice, style = MaterialTheme.typography.bodySmall)
            if (entry.errorCode.isNotBlank() && !entry.notice.contains(entry.errorCode)) Text(ChatMessages.reason(entry.errorCode, entry.notice.ifBlank { "请核对当前任务后继续" }), style = MaterialTheme.typography.bodySmall)
            if (!historical && entry.state == AssistantStatus.CLARIFICATION) {
                if ("batch_id" in entry.allowedFields) entry.candidates.forEachIndexed { index, c ->
                    OutlinedButton(onClick = { assistant.launch { clarify(id, mapOf("batch_id" to c.batchId())) } }, enabled = !disabled,
                        modifier = Modifier.fillMaxWidth().testTag("ai-candidate-$id-$index")) {
                        Text("${index + 1}. ${c.stringOrEmpty("name")} · ${c.stringOrEmpty("quantity")} ${c.stringOrEmpty("unit")} · ${c.stringOrEmpty("location").ifBlank { c.stringOrEmpty("storage_location") }}\n购入 ${c.stringOrEmpty("purchased_at").ifBlank { "未知" }} · 有效期 ${c.stringOrEmpty("label_expiry").ifBlank { "未知" }}")
                    }
                }
                entry.allowedFields.filter { it != "batch_id" && it in fieldLabels }.forEach { field ->
                    OutlinedTextField(if (selectedField == field) answers else "", { selectedField = field; answers = it }, label = { Text(fieldLabels[field] ?: field) },
                        enabled = !disabled && entry.clarificationBody.isBlank(), modifier = Modifier.fillMaxWidth().testTag("ai-clarify-$field-$id"))
                }
                if (selectedField.isNotBlank()) TextButton(onClick = { assistant.launch { clarify(id, mapOf(selectedField to answers)) } }, enabled = !disabled && answers.isNotBlank()) { Text("继续澄清") }
            }
            if (!historical && entry.draftId.isNotBlank()) {
                val command = entry.command
                Text("${actionLabel(entry.action)}：${command.stringOrEmpty("name")}", fontWeight = FontWeight.SemiBold)
                val before = entry.preview.optJSONObject("before")
                val after = entry.preview.optJSONObject("after")
                if (before != null || after != null) Text("${if (entry.checkedPreview.isNotBlank()) "已校验的预览" else "生成时的预览"}（尚非执行结果）\n" +
                    (before?.let { "原记录：${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} · ${it.stringOrEmpty("location").ifBlank { it.stringOrEmpty("storage_location") }}\n" } ?: "") +
                    (after?.let { "预计：${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} · ${it.stringOrEmpty("location").ifBlank { it.stringOrEmpty("storage_location") }}" } ?: ""),
                    style = MaterialTheme.typography.bodySmall)
                if (entry.action == "OPEN") Text("开封日期：${command.stringOrEmpty("opened_at")} · 数量不变")
                if (entry.action == "DISCARD") Text(if (command.optString("discard_mode") == "all") "全部丢弃 · 数量取自当前批次，版本变化时需要重新核对" else "定量丢弃 · 数量由你提供；不计入消费统计")
                val target = cloud.items.firstOrNull { it.id == command.stringOrEmpty("batch_id") }
                if (entry.action in listOf("MOVE", "CONSUME") && entry.state in setOf(AssistantStatus.PENDING, AssistantStatus.CONFLICT)) {
                    Text("批次 ${command.stringOrEmpty("batch_id").take(8)} · 原版本 ${command.optInt("expected_version")}", style = MaterialTheme.typography.bodySmall)
                    if (target != null) Text("当前缓存：${target.quantity.display()} ${target.unit} · ${target.location}（提交时由服务器复核）")
                    else Text("当前批次库存未同步，请刷新核对")
                    if (entry.action == "MOVE") Text("原位置 ${target?.location ?: "待核对"} → ${entry.edits["to_location"] ?: command.stringOrEmpty("to_location")}")
                    if (entry.action == "CONSUME") {
                        val amount = (entry.edits["quantity"] ?: command.stringOrEmpty("quantity")).toBigDecimalOrNull()
                        val unit = entry.edits["unit"] ?: command.stringOrEmpty("unit")
                        Text("消耗：${amount ?: "待填写"} $unit")
                        if (target != null && amount != null && unit == target.unit) Text("预计剩余：${java.math.BigDecimal.valueOf(target.quantity).subtract(amount).toPlainString()} $unit（以正式回执为准）")
                        else Text("预计剩余需按库存单位核算，以正式回执为准")
                    }
                }
                if (entry.state == AssistantStatus.PENDING && entry.commitBody.isBlank()) {
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
            if (!historical && entry.state == AssistantStatus.CONFLICT) Text("库存或草稿版本已变化。请刷新库存并重新提问生成新草稿；不会替换版本自动执行。")
            if (!historical && (entry.state in listOf(AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.FAILED, AssistantStatus.CONFLICT) || entry.refreshNeeded)) {
                TextButton(onClick = { assistant.launch { if (entry.taskId.isBlank() && entry.conversationBody.isBlank()) retryMessage(id) else recover(id) } }, enabled = !disabled, modifier = Modifier.testTag("ai-recover-$id")) { Text(if (entry.refreshNeeded) "重新刷新库存" else "核实并恢复") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.commitBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryCommit(id) } }, enabled = !disabled) { Text("用原确认请求恢复提交") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.clarificationBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryClarification(id) } }, enabled = !disabled) { Text("恢复原澄清") }
                if (entry.state == AssistantStatus.UNKNOWN && entry.cancelBody.isNotBlank()) TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled) { Text("恢复原取消请求") }
            }
            if (entry.taskId.isNotBlank() || entry.errorCode.isNotBlank()) {
                TextButton(onClick = { details = !details }) { Text(if (details) "收起记录详情" else "记录详情") }
                if (details) Text("任务 ${entry.taskId}\n修订 ${entry.taskRevision} · 草稿修订 ${entry.draftRevision}\n${entry.errorCode}", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
