package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.R
import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.theme.appearanceFade
import java.time.LocalDate
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException

private data class AddReviewStep(
    val version: Int,
    val index: Int,
    val draft: VoiceDraft?,
    val total: Int,
    val sourceText: String
)

@Composable
internal fun AddFlow(store: InventoryStore, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    if (mode == "拍照添加") {
        PhotoScanFlow(store, notify, close)
        return
    }
    val strings = rememberUiStrings()
    val context = LocalContext.current
    val focus = LocalFocusManager.current
    var transcript by rememberSaveable { mutableStateOf("") }
    var draftSource by rememberSaveable { mutableStateOf("") }
    val drafts = remember(draftSource) { if (draftSource.isBlank()) emptyList() else parseVoice(draftSource) }
    var index by rememberSaveable { mutableIntStateOf(0) }
    var review by rememberSaveable { mutableStateOf(mode == "手动添加") }
    var reviewVersion by rememberSaveable { mutableIntStateOf(0) }
    var error by rememberSaveable { mutableStateOf("") }
    val speech = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            transcript = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (transcript.isBlank()) error = "未识别到语音，请重试或手动输入。" else error = ""
        } else error = "语音输入已取消或未识别成功，可重试或手动输入。"
    }
    // Keep each outgoing review bound to its own draft while the next item enters.
    val reviewStep = if (review) AddReviewStep(reviewVersion, index, drafts.getOrNull(index), drafts.size, transcript) else null
    AppMotionContent(reviewStep, Modifier.fillMaxSize(), label = "add-step") { step ->
    if (step != null) {
        Column(Modifier.fillMaxSize()) {
            if (step.total > 0) Text(strings.get(R.string.ui_review_____each_item_is, step.index + 1, step.total), modifier = Modifier.padding(horizontal = 22.dp))
            key(step.index, mode) {
                Editor(store, initial = null, draft = step.draft, notify = notify, onSaved = {
                    focus.clearFocus()
                    if (step.index + 1 < step.total) index = step.index + 1 else close()
                }, cancel = { focus.clearFocus(); reviewVersion++; review = false; draftSource = ""; index = 0 }, sourceText = step.sourceText)
            }
        }
    } else {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            MewAddIntro(mode)
                Text(strings.get(R.string.ui_say_what_you_want_to_add), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                ModeNotice(strings.get(R.string.ui_speak_chinese__for_example____the))
                Button(onClick = {
                    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM).putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN").putExtra(RecognizerIntent.EXTRA_PROMPT, "说出物品、数量和单位")
                    runCatching { speech.launch(intent) }.onFailure { error = "设备未安装可用的语音识别服务，请手动输入。" }
                }, modifier = Modifier.fillMaxWidth()) { Text(strings.get(R.string.ui_start___retry_voice_input)) }
                OutlinedTextField(transcript, { transcript = it; error = "" }, label = { Text(strings.get(R.string.ui_recognized_text___manual_input)) }, minLines = 3, modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    focus.clearFocus()
                    draftSource = transcript; index = 0
                    if (parseVoice(transcript).isEmpty()) error = "请先说出或输入物品信息" else review = true
                }, modifier = Modifier.fillMaxWidth()) { Text(strings.get(R.string.ui_parse_and_review_items)) }
                Text(strings.get(R.string.ui_only_simple_names__quantities_and_units), style = MaterialTheme.typography.bodySmall)
            MotionErrorText(error)
            TextButton(onClick = { focus.clearFocus(); draftSource = ""; transcript = ""; review = true }) { Text(strings.get(R.string.ui_enter_manually)) }
        }
    }
    }
}

@Composable
internal fun Editor(store: InventoryStore, initial: StockItem?, image: String = "", draft: VoiceDraft? = null, notify: (String) -> Unit, onSaved: () -> Unit, cancel: (() -> Unit)? = null, sourceText: String = "") {
    val strings = rememberUiStrings()
    val scope = rememberCoroutineScope()
    var submitting by remember { mutableStateOf(false) }
    val itemId = rememberSaveable { initial?.id ?: java.util.UUID.randomUUID().toString() }
    var name by rememberSaveable { mutableStateOf(initial?.name ?: draft?.name.orEmpty()) }
    var quantity by rememberSaveable { mutableStateOf(initial?.quantity?.display() ?: draft?.quantity.orEmpty()) }
    var unit by rememberSaveable { mutableStateOf(initial?.unit ?: draft?.unit.orEmpty()) }
    var category by rememberSaveable { mutableStateOf(initial?.category?.let(InventoryContract::categoryLabel) ?: "食品") }
    var location by rememberSaveable { mutableStateOf(initial?.location ?: draft?.location?.takeIf { it.isNotBlank() } ?: store.locations.firstOrNull().orEmpty()) }
    var minimum by rememberSaveable { mutableStateOf(initial?.minimum?.display() ?: "0") }
    var expiry by rememberSaveable { mutableStateOf(initial?.expiry.orEmpty()) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var duplicate by remember { mutableStateOf<StockItem?>(null) }
    var pending by remember { mutableStateOf<StockItem?>(null) }
    var generalError by remember { mutableStateOf("") }
    var groupingInput by remember { mutableStateOf<ProductGroupingInput?>(null) }
    fun save(item: StockItem, mode: String = "新建") {
        if (!submitting) scope.launch {
            submitting = true
            try { store.saveItemSynced(item, initial, mode); notify(strings.get(R.string.ui_saved)); onSaved() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { generalError = failure.message ?: "保存失败" }
            finally { submitting = false }
        }
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (initial == null) strings.get(R.string.ui_review_item) else strings.get(R.string.ui_edit_item), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        if (sourceText.isNotBlank()) Text(strings.get(R.string.ui_original_transcript, sourceText), style = MaterialTheme.typography.bodySmall)
        Photo(initial?.image ?: image)
        if (store.cloud.signedIn) Text(strings.get(R.string.ui_save_to_the_current_household__items), style = MaterialTheme.typography.bodySmall)
        else if (LocalLightDesign.current) Text(strings.get(R.string.ui___required__inventory_changes_only_after), style = MaterialTheme.typography.bodySmall)
        else DarkNotice(strings.get(R.string.ui___required__inventory_changes_only_after))
        Field(strings.get(R.string.ui_item_name), name, { name = it }, errors["name"], enabled = !submitting)
        Field(strings.get(R.string.ui_quantity), quantity, { quantity = it }, errors["quantity"], numeric = true, enabled = !submitting)
        Field(strings.get(R.string.ui_unit____e_g__box__bag__bottle), unit, { unit = it }, errors["unit"], enabled = !submitting)
        Text(strings.get(R.string.ui_category), style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf("食品", "日用品", "药品", "其他").forEach { c -> FilterChip(selected = category == c, onClick = { category = c }, enabled = !submitting, label = { Text(if (c == "药品") strings.tr("药品", "Medicine") else strings.label(c)) }) } }
        Choice(strings.get(R.string.ui_location), store.locations, location, enabled = !submitting) { location = it }
        MotionErrorText(errors["location"])
        Field(strings.get(R.string.ui_minimum_stock__optional__default_0), minimum, { minimum = it }, errors["minimum"], numeric = true, enabled = !submitting)
        Field(strings.get(R.string.ui_expiry_date__optional__yyyy_mm_dd), expiry, { expiry = it }, errors["expiry"], enabled = !submitting)
        MotionErrorText(generalError)
        Button(onClick = {
            val q = if (initial == null) positiveNumber(quantity) else nonNegativeNumber(quantity)
            val m = nonNegativeNumber(minimum.ifBlank { "0" })
            errors = buildMap {
                if (name.isBlank()) put("name", "请填写物品名称")
                else if (name.trim().length > 80) put("name", strings.tr("最多 80 字；旧名称不会自动截断，请核对后修改", "Up to 80 characters. Review legacy names explicitly; they are not truncated."))
                if (q == null) put("quantity", if (initial == null) "请输入有效正数" else "数量不能为负数")
                if (InventoryContract.unit(unit) == null) put("unit", strings.tr("请核对单位：${InventoryContract.units.joinToString("、")}；不猜测容量换算", "Review the unit: ${InventoryContract.units.joinToString(", ")}. No guessed capacity conversions."))
                if (location.isBlank()) put("location", "请选择存放位置")
                if (m == null) put("minimum", "最低库存必须是有效非负数")
                if (expiry.isNotBlank() && runCatching { LocalDate.parse(expiry) }.isFailure) put("expiry", "请填写有效日期，如 2026-10-20")
            }
            if (errors.isEmpty()) {
                val item = StockItem(itemId, name.trim(), q!!, InventoryContract.unit(unit)!!, category, location, m!!, expiry, initial?.image ?: image,
                    purchasedAt = initial?.purchasedAt.orEmpty(), version = initial?.version ?: 1,
                    openedAt = initial?.openedAt.orEmpty(), lifecycleStatus = initial?.lifecycleStatus ?: "ACTIVE", quantityExact = quantity.trim())
                val existing = store.items.firstOrNull { it.id != itemId && it.name.equals(item.name, true) }
                if (existing != null && !store.cloud.signedIn) {
                    if (initial != null) generalError = "已有同名物品，请使用不同名称；合并入库请从添加入口操作。" else { duplicate = existing; pending = item }
                } else if (initial == null && store.cloud.signedIn) {
                    generalError = ""; submitting = true
                    groupingInput = ProductGroupingInput(item, store.cloud.scopeKey)
                } else save(item)
            }
        }, enabled = !submitting && !store.cloud.busy && !store.cloud.expired, modifier = Modifier.fillMaxWidth().testTag("inventory-editor-confirm")) { Text(if (submitting) strings.get(R.string.ui_saving) else if (initial == null) strings.get(R.string.ui_confirm_add) else strings.get(R.string.ui_save_changes)) }
        cancel?.let { TextButton(onClick = it, enabled = !submitting) { Text(strings.get(R.string.ui_back___discard_unconfirmed_items)) } }
        Spacer(Modifier.height(16.dp))
    }
    duplicate?.let { old ->
        AlertDialog(onDismissRequest = { duplicate = null }, modifier = Modifier.appearanceFade(), title = { Text(strings.get(R.string.ui_this_item_is_already_in_inventory)) }, text = { Text(strings.get(R.string.ui_currently_has___adding_stock_increases, old.name, old.quantity.display(), old.unit)) }, dismissButton = { TextButton(onClick = { duplicate = null }) { Text(strings.get(R.string.ui_cancel)) } }, confirmButton = {
            Column { TextButton(onClick = { pending?.let { save(it, "入库") }; duplicate = null }) { Text(strings.get(R.string.ui_add_to_stock)) }; TextButton(onClick = { pending?.let { save(it, "盘点") }; duplicate = null }) { Text(strings.get(R.string.ui_update_stocktake)) } }
        })
    }
    ProductGroupingFlow(store.cloud, groupingInput, clear = { groupingInput = null }, busy = { if (initial == null) submitting = it },
        error = { generalError = it }, saved = { savedId ->
            notify(strings.tr("已加入库存", "Added to inventory"))
            if (savedId == itemId) onSaved() else generalError = strings.tr("上次物品已保存，请再次确认当前物品。", "The previous item is saved. Confirm the current item again.")
        })
}

@Composable
internal fun Field(label: String, value: String, change: (String) -> Unit, error: String? = null, numeric: Boolean = false, enabled: Boolean = true) {
    OutlinedTextField(value, change, label = { Text(label) }, singleLine = true,
        modifier = Modifier.fillMaxWidth().animateContentSize(tween(AppMotion.Duration, easing = AppMotion.easing)),
        isError = error != null, enabled = enabled, supportingText = { MotionErrorText(error) },
        keyboardOptions = KeyboardOptions(keyboardType = if (numeric) KeyboardType.Decimal else KeyboardType.Text))
}

@Composable
internal fun Choice(label: String, options: List<String>, selected: String, translateOptions: Boolean = false, enabled: Boolean = true, change: (String) -> Unit) {
    val strings = rememberUiStrings()
    var expanded by remember { mutableStateOf(false) }
    val arrowRotation by animateFloatAsState(if (expanded) 180f else 0f,
        tween(AppMotion.Quick, easing = AppMotion.easing), label = "choice-arrow")
    Box {
        OutlinedButton(onClick = { expanded = true }, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
            AppMotionContent(selected, label = "choice-value") { value -> Text(strings.get(R.string.ui_choice_value, label, if (value.isBlank()) strings.get(R.string.ui_select) else if (translateOptions) strings.label(value) else value)) }
            Text("▾", Modifier.padding(start = 8.dp).rotate(arrowRotation))
        }
        DropdownMenu(expanded && enabled, { expanded = false }) {
            options.forEach { option -> DropdownMenuItem(text = { Text(if (translateOptions) strings.label(option) else option) }, onClick = { change(option); expanded = false }) }
        }
    }
}

@Composable
internal fun MotionErrorText(message: String?, modifier: Modifier = Modifier) {
    val strings = rememberUiStrings()
    val visible = !message.isNullOrBlank()
    var retainedMessage by remember { mutableStateOf(message.orEmpty()) }
    SideEffect { if (visible) retainedMessage = message.orEmpty() }
    AnimatedVisibility(
        visible = visible, modifier = modifier,
        enter = fadeIn(tween(AppMotion.Quick)) + expandVertically(tween(AppMotion.Duration, easing = AppMotion.easing)),
        exit = fadeOut(tween(AppMotion.Quick)) + shrinkVertically(tween(AppMotion.Duration, easing = AppMotion.easing))
    ) {
        Text(strings.label(if (visible) message.orEmpty() else retainedMessage), color = Red)
    }
}
