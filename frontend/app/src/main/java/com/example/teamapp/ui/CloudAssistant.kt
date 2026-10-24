package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.R
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
    val strings = rememberUiStrings()
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
        if (strings.english) Text(strings.get(R.string.ui_ai_language_note), style = MaterialTheme.typography.bodySmall)
        Text(strings.get(R.string.ui_household_ai___actions_require_confirmation), style = MaterialTheme.typography.labelLarge)
        Text(if (assistant.conversationEnabled) strings.get(R.string.ui_continue_the_current_task_directly__edited) else strings.get(R.string.ui_this_service_handles_separate_tasks__candidate), style = MaterialTheme.typography.bodySmall)
        assistant.activeEntry?.let { Text(strings.get(R.string.ui_current_task, JSONObject(it.requestBody).optString("text").take(50)), style = MaterialTheme.typography.labelMedium) }
        if (assistant.referenceLabel.isNotBlank()) Text(assistant.referenceLabel, style = MaterialTheme.typography.bodySmall)
        if (assistant.conversationEnabled) TextButton(onClick = { send("开始新任务") }, enabled = !assistant.busy) { Text(strings.get(R.string.ui_start_a_new_task)) }
        val caps = JSONObject(assistant.capabilities).optJSONObject("actions")
        Text(if (caps == null) strings.get(R.string.ui_available_actions_have_not_been_verified) else listOf("ADD", "MOVE", "CONSUME", "PLAN_ADD", "OPEN", "DISCARD").joinToString(" · ") {
            "${strings.label(actionLabel(it))}${if (caps.optBoolean(it)) " ✓" else strings.get(R.string.ui_not_supported)}"
        }, style = MaterialTheme.typography.labelSmall, modifier = Modifier.testTag("ai-capabilities"))
        if (assistant.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(strings.label(assistant.phase), style = MaterialTheme.typography.bodySmall) }
        if (assistant.error.isNotBlank() || localError.isNotBlank()) Text(strings.label(localError.ifBlank { assistant.error }), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        LazyColumn(Modifier.weight(1f).testTag("ai-tasks"), state = scroll, verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
            if (assistant.entries.isEmpty()) item { Text(strings.get(R.string.ui_try_a_chinese_request_such_as)) }
            items(assistant.entries, key = { it.requestId }) { entry ->
                AssistantTaskCard(entry, cloud, assistant.busy || cloud.expired,
                    confirm = { assistant.launch { validateDraft(entry.requestId); if (assistant.error.isBlank()) confirmId = entry.requestId } })
            }
        }
        Row(Modifier.fillMaxWidth()) {
            OutlinedTextField(input, { input = it }, label = { Text(strings.get(R.string.ui_enter_a_question)) }, modifier = Modifier.weight(1f).testTag("ai-input"))
            TextButton(onClick = { send(input) }, enabled = !assistant.busy && !cloud.expired && input.isNotBlank(), modifier = Modifier.testTag("ai-send")) { Text(strings.get(R.string.ui_send)) }
        }
        Spacer(Modifier.height(12.dp))
    }
    confirmId?.let { id ->
        val entry = assistant.entries.firstOrNull { it.requestId == id }
        if (entry != null) AlertDialog(onDismissRequest = { confirmId = null },
            title = { Text(strings.get(R.string.ui_confirm, strings.label(actionLabel(entry.action)))) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${strings.label(actionLabel(entry.action))}：${entry.command.stringOrEmpty("name")}")
                    val command = entry.command
                    if (entry.action in setOf("ADD", "CONSUME", "DISCARD", "PLAN_ADD"))
                        Text(strings.get(R.string.ui_quantity_2, command.stringOrEmpty("quantity"), command.stringOrEmpty("unit")) + if (command.optString("discard_mode") == "all") strings.get(R.string.ui__all) else "")
                    if (entry.action == "MOVE") Text(strings.get(R.string.ui_destination, command.stringOrEmpty("to_location")))
                    if (entry.action == "ADD") Text(strings.get(R.string.ui_location_2, command.stringOrEmpty("location")))
                    if (entry.action == "OPEN") Text(strings.get(R.string.ui_opened_on____quantity_unchanged, command.stringOrEmpty("opened_at")))
                    Text(strings.get(R.string.ui_nothing_has_been_executed__the_server))
                }
            },
            confirmButton = { TextButton(onClick = { confirmId = null; assistant.launch { confirm(id) } }, modifier = Modifier.testTag("ai-final-confirm")) { Text(strings.get(R.string.ui_confirm_action)) } },
            dismissButton = { TextButton(onClick = { confirmId = null }) { Text(strings.get(R.string.ui_back_to_review)) } })
    }
}

private fun JSONObject.batchId() = stringOrEmpty("batch_id").ifBlank { stringOrEmpty("id") }
internal fun actionLabel(action: String) = mapOf("ADD" to "添加库存", "MOVE" to "移动", "CONSUME" to "消耗", "PLAN_ADD" to "添加采购", "OPEN" to "开封", "DISCARD" to "丢弃")[action] ?: action
private val fieldLabels = mapOf("name" to "物品名称", "quantity" to "数量", "unit" to "单位", "location" to "存放位置（必填）",
    "to_location" to "目标位置", "purchased_at" to "购入日期（YYYY-MM-DD，可空）", "label_expiry" to "有效日期（YYYY-MM-DD，可空）", "opened_at" to "开封日期")

@Composable
internal fun AssistantTaskCard(entry: AssistantEntry, cloud: CloudStore, disabled: Boolean, confirm: () -> Unit) {
    val strings = rememberUiStrings()
    val assistant = cloud.assistant
    val id = entry.requestId
    val historical = entry.taskId.isNotBlank() && assistant.entries.lastOrNull { it.taskId == entry.taskId }?.requestId != id
    var details by rememberSaveable(id) { mutableStateOf(false) }
    var answers by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    var selectedField by rememberSaveable(id, entry.taskRevision) { mutableStateOf("") }
    Card(Modifier.fillMaxWidth().testTag("ai-task-$id")) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(JSONObject(entry.requestBody).getString("text"), fontWeight = FontWeight.SemiBold)
            Text(if (historical) strings.get(R.string.ui_earlier_message_for_this_task) else strings.label(entry.state.label), color = if (entry.state == AssistantStatus.COMMITTED) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.testTag("ai-state-$id"))
            if (entry.reply.isNotBlank()) {
                if (entry.state in setOf(AssistantStatus.COMMITTED, AssistantStatus.CANCELLED)) Text(strings.get(R.string.ui_ai_reply_when_generated__history), style = MaterialTheme.typography.labelSmall)
                Text(entry.reply)
            }
            if (entry.notice.isNotBlank()) Text(entry.notice, style = MaterialTheme.typography.bodySmall)
            if (entry.errorCode.isNotBlank() && !entry.notice.contains(entry.errorCode)) Text(ChatMessages.reason(entry.errorCode, entry.notice.ifBlank { strings.get(R.string.ui_review_the_current_task_before_continuing) }), style = MaterialTheme.typography.bodySmall)
            if (!historical && entry.state == AssistantStatus.CLARIFICATION) {
                if ("batch_id" in entry.allowedFields) entry.candidates.forEachIndexed { index, c ->
                    OutlinedButton(onClick = { assistant.launch { clarify(id, mapOf("batch_id" to c.batchId())) } }, enabled = !disabled,
                        modifier = Modifier.fillMaxWidth().testTag("ai-candidate-$id-$index")) {
                        Text(strings.get(R.string.ui_______purchased___expires, index + 1, c.stringOrEmpty("name"), c.stringOrEmpty("quantity"), c.stringOrEmpty("unit"), c.stringOrEmpty("location").ifBlank { c.stringOrEmpty("storage_location") }, c.stringOrEmpty("purchased_at").ifBlank { strings.get(R.string.ui_unknown) }, c.stringOrEmpty("label_expiry").ifBlank { strings.get(R.string.ui_unknown) }))
                    }
                }
                entry.allowedFields.filter { it != "batch_id" && it in fieldLabels }.forEach { field ->
                    OutlinedTextField(if (selectedField == field) answers else "", { selectedField = field; answers = it }, label = { Text(strings.label(fieldLabels[field] ?: field)) },
                        enabled = !disabled && entry.clarificationBody.isBlank(), modifier = Modifier.fillMaxWidth().testTag("ai-clarify-$field-$id"))
                }
                if (selectedField.isNotBlank()) TextButton(onClick = { assistant.launch { clarify(id, mapOf(selectedField to answers)) } }, enabled = !disabled && answers.isNotBlank()) { Text(strings.get(R.string.ui_continue_clarification)) }
            }
            if (!historical && entry.draftId.isNotBlank()) {
                val command = entry.command
                Text("${strings.label(actionLabel(entry.action))}：${command.stringOrEmpty("name")}", fontWeight = FontWeight.SemiBold)
                val before = entry.preview.optJSONObject("before")
                val after = entry.preview.optJSONObject("after")
                if (before != null || after != null) Text(strings.get(R.string.ui__not_an_execution_result, if (entry.checkedPreview.isNotBlank()) "已校验的预览" else "生成时的预览") +
                    (before?.let { strings.get(R.string.ui_original, it.stringOrEmpty("quantity"), it.stringOrEmpty("unit"), it.stringOrEmpty("location").ifBlank { it.stringOrEmpty("storage_location") }) } ?: "") +
                    (after?.let { strings.get(R.string.ui_expected, it.stringOrEmpty("quantity"), it.stringOrEmpty("unit"), it.stringOrEmpty("location").ifBlank { it.stringOrEmpty("storage_location") }) } ?: ""),
                    style = MaterialTheme.typography.bodySmall)
                if (entry.action == "OPEN") Text(strings.get(R.string.ui_opened_on____quantity_unchanged_2, command.stringOrEmpty("opened_at")))
                if (entry.action == "DISCARD") Text(if (command.optString("discard_mode") == "all") strings.get(R.string.ui_discard_all___quantity_comes_from) else strings.get(R.string.ui_discard_an_amount_you_specify__this))
                val target = cloud.items.firstOrNull { it.id == command.stringOrEmpty("batch_id") }
                if (entry.action in listOf("MOVE", "CONSUME") && entry.state in setOf(AssistantStatus.PENDING, AssistantStatus.CONFLICT)) {
                    Text(strings.get(R.string.ui_batch___original_version, command.stringOrEmpty("batch_id").take(8), command.optInt("expected_version")), style = MaterialTheme.typography.bodySmall)
                    if (target != null) Text(strings.get(R.string.ui_cached_____server_checks_on_submission, target.quantity.display(), target.unit, target.location))
                    else Text(strings.get(R.string.ui_this_batch_is_not_synced__refresh))
                    if (entry.action == "MOVE") Text(strings.get(R.string.ui_from, target?.location ?: "待核对", entry.edits["to_location"] ?: command.stringOrEmpty("to_location")))
                    if (entry.action == "CONSUME") {
                        val amount = (entry.edits["quantity"] ?: command.stringOrEmpty("quantity")).toBigDecimalOrNull()
                        val unit = entry.edits["unit"] ?: command.stringOrEmpty("unit")
                        Text(strings.get(R.string.ui_consume, amount ?: "待填写", unit))
                        if (target != null && amount != null && unit == target.unit) Text(strings.get(R.string.ui_expected_remaining___subject_to_the_final, java.math.BigDecimal.valueOf(target.quantity).subtract(amount).toPlainString(), unit))
                        else Text(strings.get(R.string.ui_remaining_stock_must_be_calculated_in))
                    }
                }
                if (entry.state == AssistantStatus.PENDING && entry.commitBody.isBlank()) {
                    entry.editableFields.forEach { field ->
                        OutlinedTextField(entry.edits[field] ?: command.stringOrEmpty(field),
                            { value -> assistant.edit(id, field, value) }, label = { Text(strings.label(fieldLabels[field] ?: field)) }, enabled = !disabled,
                            modifier = Modifier.fillMaxWidth().testTag("ai-edit-$field-$id"))
                    }
                    Row {
                        Button(onClick = confirm, enabled = !disabled && JSONObject(assistant.capabilities).optJSONObject("actions")?.optBoolean(entry.action) == true,
                            modifier = Modifier.testTag("ai-confirm-$id")) { Text(strings.get(R.string.ui_review_and_confirm)) }
                        TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled, modifier = Modifier.testTag("ai-cancel-$id")) { Text(strings.get(R.string.ui_cancel_draft)) }
                    }
                } else if (entry.state == AssistantStatus.UNSUPPORTED && entry.commitBody.isBlank()) {
                    Text(strings.get(R.string.ui_draft_quantity____location, command.stringOrEmpty("quantity"), command.stringOrEmpty("unit"), command.stringOrEmpty("location").ifBlank { command.stringOrEmpty("to_location") }))
                    Text(strings.get(R.string.ui_automatic_execution_is_not_supported_here))
                    TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled) { Text(strings.get(R.string.ui_cancel_draft)) }
                }
            }
            if (entry.receipt.isNotBlank()) {
                val receipt = JSONObject(entry.receipt)
                Text(strings.get(R.string.ui_server_confirmed, actionLabel(receipt.getString("action"))), fontWeight = FontWeight.SemiBold, modifier = Modifier.testTag("ai-receipt-$id"))
                val result = receipt.getJSONObject("result")
                val resource = result.optJSONObject("inventory_item") ?: result.optJSONObject("shopping_item")
                resource?.let { Text("${it.stringOrEmpty("name")} · ${it.stringOrEmpty("quantity")} ${it.stringOrEmpty("unit")} ${it.stringOrEmpty("storage_location")}") }
                Text(strings.get(R.string.ui_receipt, receipt.getString("operation_id"), receipt.getString("committed_at")), style = MaterialTheme.typography.labelSmall)
            }
            if (!historical && entry.state == AssistantStatus.CONFLICT) Text(strings.get(R.string.ui_inventory_or_draft_versions_changed__refresh))
            if (!historical && (entry.state in listOf(AssistantStatus.UNKNOWN, AssistantStatus.PROCESSING, AssistantStatus.FAILED, AssistantStatus.CONFLICT) || entry.refreshNeeded)) {
                TextButton(onClick = { assistant.launch { if (entry.taskId.isBlank() && entry.conversationBody.isBlank()) retryMessage(id) else recover(id) } }, enabled = !disabled, modifier = Modifier.testTag("ai-recover-$id")) { Text(if (entry.refreshNeeded) strings.get(R.string.ui_refresh_inventory) else strings.get(R.string.ui_check_and_recover)) }
                if (entry.state == AssistantStatus.UNKNOWN && entry.commitBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryCommit(id) } }, enabled = !disabled) { Text(strings.get(R.string.ui_recover_the_original_confirmation)) }
                if (entry.state == AssistantStatus.UNKNOWN && entry.clarificationBody.isNotBlank()) TextButton(onClick = { assistant.launch { retryClarification(id) } }, enabled = !disabled) { Text(strings.get(R.string.ui_recover_clarification)) }
                if (entry.state == AssistantStatus.UNKNOWN && entry.cancelBody.isNotBlank()) TextButton(onClick = { assistant.launch { cancel(id) } }, enabled = !disabled) { Text(strings.get(R.string.ui_recover_cancellation)) }
            }
            if (entry.taskId.isNotBlank() || entry.errorCode.isNotBlank()) {
                TextButton(onClick = { details = !details }) { Text(if (details) strings.get(R.string.ui_hide_record_details) else strings.get(R.string.ui_record_details)) }
                if (details) Text(strings.get(R.string.ui_task_revision___draft_revision, entry.taskId, entry.taskRevision, entry.draftRevision, entry.errorCode), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
