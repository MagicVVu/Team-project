package com.example.teamapp.ui

import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.theme.LocalLightDesign
import java.io.File
import java.time.LocalDate

@Composable
internal fun AddFlow(store: InventoryStore, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    val context = LocalContext.current
    var image by rememberSaveable { mutableStateOf("") }
    var cameraUri by rememberSaveable { mutableStateOf("") }
    var transcript by rememberSaveable { mutableStateOf("") }
    var draftSource by rememberSaveable { mutableStateOf("") }
    val drafts = remember(draftSource) { if (draftSource.isBlank()) emptyList() else parseVoice(draftSource) }
    var index by rememberSaveable { mutableIntStateOf(0) }
    var review by rememberSaveable { mutableStateOf(mode == "手动添加") }
    var error by rememberSaveable { mutableStateOf("") }
    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
                .onSuccess { image = uri.toString(); review = true; error = "" }
                .onFailure { error = "无法保留照片访问权限，请重新选图或手动填写。" }
        }
    }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success) { image = cameraUri; review = true; error = "" } else error = "拍摄已取消，没有修改库存。"
    }
    val speech = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            transcript = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (transcript.isBlank()) error = "未识别到语音，请重试或手动输入。" else error = ""
        } else error = "语音输入已取消或未识别成功，可重试或手动输入。"
    }
    if (review) {
        val draft = drafts.getOrNull(index)
        Column(Modifier.fillMaxSize()) {
            if (drafts.isNotEmpty()) Text("逐项确认 ${index + 1} / ${drafts.size} · 每项确认后才保存", modifier = Modifier.padding(horizontal = 22.dp))
            key(index, image, mode) {
                Editor(store, initial = null, image = image, draft = draft, notify = notify, onSaved = {
                    if (index + 1 < drafts.size) index++ else close()
                }, cancel = { review = false; draftSource = ""; index = 0 }, sourceText = transcript)
            }
        }
    } else {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (LocalLightDesign.current) DesignAddIntro(mode)
            if (mode == "拍照添加") {
                Text("用照片记录家里的物品", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("拍照将打开系统相机，照片仅用于本机库存记录。初版未接入图像识别，请自行填写并核对名称、数量。")
                Button(onClick = {
                    runCatching {
                        val directory = File(context.filesDir, "photos").apply { mkdirs() }
                        val file = File.createTempFile("stock_", ".jpg", directory)
                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                        cameraUri = uri.toString(); camera.launch(uri)
                    }.onFailure { error = "设备无法打开相机，请选图或手动填写。" }
                }, modifier = Modifier.fillMaxWidth()) { Text("打开相机拍照") }
                OutlinedButton(onClick = { runCatching { photoPicker.launch(arrayOf("image/*")) }.onFailure { error = "设备无法打开图库，请手动填写。" } }, modifier = Modifier.fillMaxWidth()) { Text("选择已有照片") }
            } else {
                Text("说出需要录入的物品", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("例如：添加两盒纯牛奶，三袋面包。系统语音服务将使用麦克风，可能需要联网；识别后逐项核对，不自动入库。")
                Button(onClick = {
                    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM).putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN").putExtra(RecognizerIntent.EXTRA_PROMPT, "说出物品、数量和单位")
                    runCatching { speech.launch(intent) }.onFailure { error = "设备未安装可用的语音识别服务，请手动输入。" }
                }, modifier = Modifier.fillMaxWidth()) { Text("开始语音输入 / 重新输入") }
                OutlinedTextField(transcript, { transcript = it; error = "" }, label = { Text("识别文字 / 手动输入") }, minLines = 3, modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    draftSource = transcript; index = 0
                    if (parseVoice(transcript).isEmpty()) error = "请先说出或输入物品信息" else review = true
                }, modifier = Modifier.fillMaxWidth()) { Text("解析并逐项核对") }
                Text("仅提取简单的名称、数量与单位。缺少或不确定的信息必须由你补全。", style = MaterialTheme.typography.bodySmall)
            }
            if (error.isNotBlank()) Text(error, color = Red)
            TextButton(onClick = { draftSource = ""; image = ""; transcript = ""; review = true }) { Text("改为手动填写") }
        }
    }
}

@Composable
internal fun Editor(store: InventoryStore, initial: StockItem?, image: String = "", draft: VoiceDraft? = null, notify: (String) -> Unit, onSaved: () -> Unit, cancel: (() -> Unit)? = null, sourceText: String = "") {
    val itemId = rememberSaveable { initial?.id ?: java.util.UUID.randomUUID().toString() }
    var name by rememberSaveable { mutableStateOf(initial?.name ?: draft?.name.orEmpty()) }
    var quantity by rememberSaveable { mutableStateOf(initial?.quantity?.display() ?: draft?.quantity.orEmpty()) }
    var unit by rememberSaveable { mutableStateOf(initial?.unit ?: draft?.unit.orEmpty()) }
    var category by rememberSaveable { mutableStateOf(initial?.category ?: "食品") }
    var location by rememberSaveable { mutableStateOf(initial?.location ?: draft?.location?.takeIf { it.isNotBlank() } ?: store.locations.firstOrNull().orEmpty()) }
    var minimum by rememberSaveable { mutableStateOf(initial?.minimum?.display() ?: "0") }
    var expiry by rememberSaveable { mutableStateOf(initial?.expiry.orEmpty()) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var duplicate by remember { mutableStateOf<StockItem?>(null) }
    var pending by remember { mutableStateOf<StockItem?>(null) }
    var generalError by remember { mutableStateOf("") }
    fun save(item: StockItem, mode: String = "新建") {
        runCatching { store.saveItem(item, mode) }.onSuccess { notify(it); onSaved() }.onFailure { generalError = it.message ?: "保存失败" }
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (initial == null) "核对物品信息" else "编辑物品信息", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        if (sourceText.isNotBlank()) Text("原始识别文字：$sourceText", style = MaterialTheme.typography.bodySmall)
        Photo(initial?.image ?: image)
        Text("* 为必填项。未确认前不会更改库存。", style = MaterialTheme.typography.bodySmall)
        Field("物品名称 *", name, { name = it }, errors["name"])
        Field("数量 *", quantity, { quantity = it }, errors["quantity"], numeric = true)
        Field("单位 *（如盒、袋、瓶、个）", unit, { unit = it }, errors["unit"])
        Text("类别", style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf("食品", "日用品", "其他").forEach { c -> FilterChip(selected = category == c, onClick = { category = c }, label = { Text(c) }) } }
        Choice("存放位置 *", store.locations, location) { location = it }
        if (errors["location"] != null) Text(errors["location"]!!, color = Red)
        Field("最低库存（选填，默认 0）", minimum, { minimum = it }, errors["minimum"], numeric = true)
        Field("有效期（选填，YYYY-MM-DD）", expiry, { expiry = it }, errors["expiry"])
        if (generalError.isNotBlank()) Text(generalError, color = Red)
        Button(onClick = {
            val q = if (initial == null) positiveNumber(quantity) else nonNegativeNumber(quantity)
            val m = nonNegativeNumber(minimum.ifBlank { "0" })
            errors = buildMap {
                if (name.isBlank()) put("name", "请填写物品名称")
                if (q == null) put("quantity", if (initial == null) "请输入有效正数" else "数量不能为负数")
                if (unit.isBlank()) put("unit", "请核对计量单位")
                if (location.isBlank()) put("location", "请选择存放位置")
                if (m == null) put("minimum", "最低库存必须是有效非负数")
                if (expiry.isNotBlank() && runCatching { LocalDate.parse(expiry) }.isFailure) put("expiry", "请填写有效日期，如 2026-10-20")
            }
            if (errors.isEmpty()) {
                val item = StockItem(itemId, name.trim(), q!!, unit.trim(), category, location, m!!, expiry, initial?.image ?: image)
                val existing = store.items.firstOrNull { it.id != itemId && it.name.equals(item.name, true) }
                if (existing != null) {
                    if (initial != null) generalError = "已有同名物品，请使用不同名称；合并入库请从添加入口操作。" else { duplicate = existing; pending = item }
                } else save(item)
            }
        }, modifier = Modifier.fillMaxWidth()) { Text(if (initial == null) "确认添加" else "保存修改") }
        cancel?.let { TextButton(onClick = it) { Text("返回输入 / 放弃未确认项") } }
        Spacer(Modifier.height(16.dp))
    }
    duplicate?.let { old ->
        AlertDialog(onDismissRequest = { duplicate = null }, title = { Text("该物品已在库存中") }, text = { Text("${old.name}现有 ${old.quantity.display()} ${old.unit}。\n新增入库会累加数量；盘点会以填写数量替换现有数量。原有分类、位置、阈值和有效期保留，可在详情中编辑。") }, dismissButton = { TextButton(onClick = { duplicate = null }) { Text("取消") } }, confirmButton = {
            Column { TextButton(onClick = { pending?.let { save(it, "入库") }; duplicate = null }) { Text("新增入库") }; TextButton(onClick = { pending?.let { save(it, "盘点") }; duplicate = null }) { Text("更新盘点结果") } }
        })
    }
}

@Composable
internal fun Field(label: String, value: String, change: (String) -> Unit, error: String? = null, numeric: Boolean = false) {
    OutlinedTextField(value, change, label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth(), isError = error != null, supportingText = { if (error != null) Text(error) }, keyboardOptions = KeyboardOptions(keyboardType = if (numeric) KeyboardType.Decimal else KeyboardType.Text))
}

@Composable
internal fun Choice(label: String, options: List<String>, selected: String, change: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box { OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) { Text("$label：${selected.ifBlank { "请选择" }}  ▾") }; DropdownMenu(expanded, { expanded = false }) { options.forEach { option -> DropdownMenuItem(text = { Text(option) }, onClick = { change(option); expanded = false }) } } }
}
