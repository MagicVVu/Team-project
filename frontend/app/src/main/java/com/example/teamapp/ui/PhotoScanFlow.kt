package com.example.teamapp.ui

import android.content.Intent
import android.graphics.Bitmap
import android.speech.RecognizerIntent
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.util.UUID

/** Full-screen focused task. Neither OCR, cancellation nor an animation can write stock. */
@Composable
internal fun PhotoScanFlow(
    store: InventoryStore,
    notify: (String) -> Unit,
    close: () -> Unit,
    recognizer: PhotoRecognizer? = null,
    initialImage: String = ""
) {
    val context = LocalContext.current
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val service = remember(context, recognizer) { recognizer ?: LocalPhotoRecognizer(context) }
    var stage by rememberSaveable { mutableStateOf(if (initialImage.isBlank()) "CAMERA" else "PROCESSING") }
    var processingUri by rememberSaveable { mutableStateOf(initialImage) }
    var dateOnly by rememberSaveable { mutableStateOf(false) }
    var requestVersion by rememberSaveable { mutableIntStateOf(0) }
    var resultJson by rememberSaveable { mutableStateOf("") }
    val result = remember(resultJson) { decodePhotoResult(resultJson) }
    var error by rememberSaveable { mutableStateOf("") }
    var importing by remember { mutableStateOf(false) }
    var dateDialog by rememberSaveable { mutableStateOf(false) }
    var dateHint by rememberSaveable { mutableStateOf("") }
    var dateUpdate by rememberSaveable { mutableStateOf("") }
    var dateVersion by rememberSaveable { mutableIntStateOf(0) }
    val flashControl = remember { mutableStateOf<(() -> Unit)?>(null) }
    val flashOn = remember { mutableStateOf(false) }
    val reviewState = rememberSaveableStateHolder()
    var saving by remember { mutableStateOf(false) }

    fun back() {
        if (saving) return
        error = ""
        when {
            stage == "REVIEW" -> close()
            result != null -> { stage = "REVIEW"; dateOnly = false }
            stage == "PROCESSING" || stage == "ERROR" -> stage = "CAMERA"
            else -> close()
        }
    }
    fun acceptPhoto(uri: String) {
        processingUri = uri
        error = ""
        requestVersion++
        stage = "PROCESSING"
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) pickerResult@{ uri ->
        if (stage != "CAMERA") return@pickerResult
        if (uri != null) scope.launch {
            val startedAt = requestVersion
            importing = true
            try {
                // Copy while the picker grant is valid; the draft must survive a process restart.
                val copied = withContext(Dispatchers.IO) {
                    val file = File.createTempFile("import_", ".img", photoDirectory(context))
                    try {
                        context.contentResolver.openInputStream(uri).use { input ->
                            requireNotNull(input)
                            file.outputStream().use { output ->
                                val buffer = ByteArray(8192); var total = 0L
                                while (true) {
                                    val count = input.read(buffer); if (count < 0) break
                                    total += count; require(total <= 25L * 1024 * 1024)
                                    output.write(buffer, 0, count)
                                }
                            }
                        }
                        photoUri(context, file).toString()
                    } catch (failure: Exception) { file.delete(); throw failure }
                }
                if (stage == "CAMERA" && requestVersion == startedAt) acceptPhoto(copied)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { error = strings.tr("无法读取照片，请选择小于25MB的图片或重新拍摄。", "Unable to read the photo. Choose an image under 25MB or take another.") }
            finally { importing = false }
        }
    }
    LaunchedEffect(stage, processingUri, requestVersion) {
        if (stage != "PROCESSING") return@LaunchedEffect
        try {
            val recognized = service.recognize(processingUri, dateOnly)
            if (dateOnly && result != null) {
                dateHint = recognized.draft.expiry
                dateDialog = true
            } else {
                resultJson = encodePhotoResult(recognized)
                dateUpdate = ""; dateVersion = 0
                reviewState.removeState("review")
            }
            stage = "REVIEW"
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            error = strings.tr("这张照片暂时无法识别，照片已保留。", "Couldn't read this photo. Your photo is preserved.")
            stage = "ERROR"
        }
    }
    BackHandler { back() }
    Surface(Modifier.fillMaxSize(), color = scheme.background, contentColor = scheme.onBackground) {
    Column(Modifier.fillMaxSize().background(scheme.background).testTag("photo-scan-flow")) {
        Row(Modifier.fillMaxWidth().height(56.dp).background(scheme.surface), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { back() }, enabled = !saving, modifier = Modifier.testTag("photo-close").semantics { contentDescription = strings.tr("关闭", "Close") }) {
                ScanIcon(if (stage == "REVIEW") "back" else "close")
            }
            Text(when(stage) {
                "PROCESSING" -> strings.tr("正在识别", "Recognizing")
                "REVIEW" -> strings.tr("识别结果", "Review result")
                "ERROR" -> strings.tr("识别未完成", "Recognition incomplete")
                else -> strings.tr(if(dateOnly) "补拍日期" else "拍照识物", if(dateOnly) "Photograph the date" else "Scan an item")
            }, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
            if (stage == "CAMERA") IconButton(onClick = { flashControl.value?.invoke() }, enabled = flashControl.value != null,
                modifier = Modifier.semantics { contentDescription = strings.tr("切换闪光灯", "Toggle flash") }) {
                ScanIcon(if(flashOn.value) "flash" else "flash-off")
            } else if (stage == "REVIEW") TextButton(onClick = { dateOnly = false; stage = "CAMERA" }, enabled = !saving) { Text(strings.tr("重拍", "Retake")) }
            else Spacer(Modifier.width(48.dp))
        }
        if (error.isNotBlank() && stage != "ERROR") Text(error, color = scheme.error, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
        if (importing) LinearProgressIndicator(Modifier.fillMaxWidth())
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when(stage) {
                "CAMERA" -> PhotoCamera(dateOnly, {
                    runCatching { picker.launch(arrayOf("image/*")) }.onFailure { error = strings.tr("无法打开相册，请重试。", "Unable to open photos. Try again.") }
                }, ::acceptPhoto, {
                    if (dateOnly && result != null) { stage = "REVIEW"; dateHint = ""; dateDialog = true }
                    else { resultJson = encodePhotoResult(PhotoRecognitionResult("", "", PhotoDraft(), "", false, false)); reviewState.removeState("review"); stage = "REVIEW" }
                }, flashControl, flashOn)
                "PROCESSING" -> PhotoProcessing(processingUri, dateOnly) { back() }
                "REVIEW" -> if (result != null) reviewState.SaveableStateProvider("review") {
                    PhotoReviewEditor(store, result, dateUpdate, dateVersion, onDate = {
                        dateHint = ""; dateDialog = true
                    }, notify = notify, saved = close, onSaving = { saving = it })
                }
                "ERROR" -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    ScanPhoto(processingUri, Modifier.fillMaxWidth().height(230.dp))
                    MewMascot(MewPose.Retry, Modifier.size(70.dp), description = null)
                    Text(error, textAlign = TextAlign.Center)
                    Button(onClick = { requestVersion++; stage = "PROCESSING" }) { Text(strings.tr("重新识别", "Try recognition again")) }
                    OutlinedButton(onClick = {
                        if (dateOnly && result != null) { stage = "REVIEW"; dateHint = ""; dateDialog = true }
                        else { resultJson = encodePhotoResult(PhotoRecognitionResult(processingUri, processingUri, PhotoDraft(), "", false, false)); stage = "REVIEW" }
                    }) { Text(strings.tr("保留照片，手动填写", "Keep photo and enter details")) }
                    TextButton(onClick = { stage = "CAMERA" }) { Text(strings.tr("重新拍摄", "Retake photo")) }
                }
            }
        }
    }
    }
    if (dateDialog) PhotoDateDialog(dateHint, dismiss = { dateDialog = false }, camera = {
        dateDialog = false; dateOnly = true; stage = "CAMERA"
    }, apply = { value -> dateUpdate = value; dateVersion++; dateDialog = false })
}

@Composable
private fun PhotoProcessing(uri: String, dateOnly: Boolean, cancel: () -> Unit) {
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    val scan by rememberInfiniteTransition(label = "photo-scan").animateFloat(0f, 1f,
        infiniteRepeatable(tween(1800, easing = LinearEasing), RepeatMode.Reverse), label = "scan-line")
    Column(Modifier.fillMaxSize().padding(22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.weight(1f).fillMaxWidth().padding(vertical = 12.dp).clip(RoundedCornerShape(24.dp)).background(scheme.surfaceContainerLow), contentAlignment = Alignment.Center) {
            ScanPhoto(uri, Modifier.fillMaxSize().padding(16.dp))
            Canvas(Modifier.fillMaxSize().padding(18.dp)) {
                drawRoundRect(scheme.primary.copy(alpha = .6f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(18.dp.toPx()),
                    style = Stroke(1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(7.dp.toPx(), 6.dp.toPx()))))
                val y = size.height * (.12f + .76f * scan)
                drawLine(Brush.horizontalGradient(listOf(Color.Transparent, scheme.primary.copy(alpha = .8f), Color.Transparent)),
                    Offset(0f, y), Offset(size.width, y), 2.dp.toPx())
            }
        }
        Text(strings.tr(if(dateOnly) "正在读取日期…" else "正在识别物品…", if(dateOnly) "Reading the date…" else "Recognizing your item…"),
            fontSize = 23.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        Text(strings.tr(if(dateOnly) "核对日期旁的说明文字" else "整理包装上的名称和规格", if(dateOnly) "Checking the printed date label" else "Reading the name and package size"),
            color = scheme.onSurfaceVariant, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
        Row(Modifier.padding(vertical = 24.dp).fillMaxWidth().border(1.dp, scheme.outlineVariant, RoundedCornerShape(18.dp)).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            MewMascot(MewPose.Thinking, Modifier.size(60.dp), description = null)
            Text(strings.tr("Mew 正在看看这是什么", "Mew is taking a closer look"), fontSize = 13.sp, modifier = Modifier.padding(start = 12.dp))
        }
        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        Spacer(Modifier.height(18.dp))
        OutlinedButton(onClick = cancel, modifier = Modifier.fillMaxWidth().testTag("photo-cancel-recognition")) { Text(strings.tr("取消识别", "Cancel recognition")) }
    }
}

@Composable
internal fun ScanPhoto(uri: String, modifier: Modifier = Modifier, onUnavailable: (@Composable () -> Unit)? = null) {
    val context = LocalContext.current
    val bitmap by produceState<Bitmap?>(null, uri) { value = null; value = withContext(Dispatchers.IO) { loadPhotoBitmap(context, uri, 1024) } }
    val value = bitmap
    val appearance by animateFloatAsState(if(value != null) 1f else 0f, tween(320, easing = FastOutSlowInEasing), label = "photo-reveal")
    Box(modifier, contentAlignment = Alignment.Center) {
        if (value != null) Image(value.asImageBitmap(), contentDescription = null, Modifier.fillMaxSize().graphicsLayer {
            alpha = appearance; scaleX = .94f + .06f * appearance; scaleY = scaleX; translationY = (1f - appearance) * 16.dp.toPx()
        }, contentScale = ContentScale.Fit)
        else onUnavailable?.invoke()
    }
}

@Composable
private fun PhotoReviewEditor(store: InventoryStore, result: PhotoRecognitionResult, dateUpdate: String, dateVersion: Int,
    onDate: () -> Unit, notify: (String) -> Unit, saved: () -> Unit, onSaving: (Boolean) -> Unit) {
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val initial = result.draft
    val id = rememberSaveable { UUID.randomUUID().toString() }
    // The current inventory contract has no separate specification field. Keep it visible
    // in the editable name so 250ml and 1L packages cannot be silently collapsed.
    var name by rememberSaveable { mutableStateOf(if(initial.name.isNotBlank() && initial.specification.isNotBlank())
        "${initial.name}（${initial.specification}）" else initial.name) }
    var quantity by rememberSaveable { mutableStateOf("1") }
    var unit by rememberSaveable { mutableStateOf(initial.unit) }
    var category by rememberSaveable { mutableStateOf(initial.category) }
    var location by rememberSaveable { mutableStateOf(store.locations.firstOrNull().orEmpty()) }
    var expiry by rememberSaveable { mutableStateOf(initial.expiry) }
    var supplement by rememberSaveable { mutableStateOf("") }
    var expanded by rememberSaveable { mutableStateOf(false) }
    var minimum by rememberSaveable { mutableStateOf("0") }
    var error by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    var completed by remember { mutableStateOf(false) }
    var duplicate by remember { mutableStateOf<StockItem?>(null) }
    var pending by remember { mutableStateOf<StockItem?>(null) }
    LaunchedEffect(dateVersion) { if (dateVersion > 0) expiry = dateUpdate }
    DisposableEffect(saving) { onSaving(saving); onDispose { onSaving(false) } }
    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { response ->
        val text = response.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (!text.isNullOrBlank()) {
            supplement = text
            store.locations.firstOrNull { text.contains(it) }?.let { location = it }
            error = ""
        }
    }
    fun save(item: StockItem, duplicateMode: String = "新建") {
        if (saving || completed) return
        scope.launch {
            saving = true; error = ""
            try { store.saveItemSynced(item, null, duplicateMode); check(store.storageError == null) { store.storageError.orEmpty() }; completed = true; notify(strings.tr("已加入库存", "Added to inventory")); saved() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { error = failure.message ?: strings.tr("保存失败，信息已保留", "Save failed. Your details are preserved.") }
            finally { saving = false }
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize()) {
    val heroHeight = if (maxHeight < 600.dp) 88.dp else 160.dp
    Column(Modifier.fillMaxSize().imePadding()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 12.dp), horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(strings.tr(if(initial.name.isBlank()) "请补充物品信息" else "已读取包装文字，请核对", if(initial.name.isBlank()) "Add the item details" else "Package text read — please review"),
                color = scheme.onPrimaryContainer, fontSize = 12.sp,
                modifier = Modifier.background(scheme.primaryContainer, CircleShape).padding(horizontal = 14.dp, vertical = 6.dp))
            if (result.displayUri.isNotBlank()) ScanPhoto(result.displayUri, Modifier.fillMaxWidth().height(heroHeight))
            else MewMascot(MewPose.Confirming, Modifier.size(72.dp), description = null)
            if (result.originalUri.isNotBlank() && !result.cutout) Text(strings.tr("已保留原照片", "Original photo preserved"), fontSize = 11.sp, color = scheme.onSurfaceVariant)
            OutlinedTextField(name, { name = it; error = "" }, label = { Text(strings.tr("物品名称", "Item name")) }, singleLine = true,
                modifier = Modifier.fillMaxWidth().testTag("photo-name"), enabled = !saving, textStyle = MaterialTheme.typography.titleLarge)
            if (initial.specification.isNotBlank()) Text(strings.tr("包装规格：", "Package size: ") + initial.specification, color = scheme.onSurfaceVariant, fontSize = 12.sp)
            Surface(shape = RoundedCornerShape(18.dp), color = scheme.surface, border = androidx.compose.foundation.BorderStroke(1.dp, scheme.outlineVariant)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(strings.tr("数量", "Quantity"), fontSize = 13.sp)
                        OutlinedTextField(quantity, { quantity = it; error = "" }, modifier = Modifier.weight(1f).testTag("photo-quantity"),
                            singleLine = true, enabled = !saving, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                        var unitMenu by remember { mutableStateOf(false) }
                        Box {
                            OutlinedButton(onClick = { unitMenu = true }, enabled = !saving, contentPadding = PaddingValues(horizontal = 10.dp)) { Text(unit.ifBlank { strings.tr("单位", "Unit") }) }
                            DropdownMenu(unitMenu, { unitMenu = false }) { InventoryContract.units.forEach { value ->
                                DropdownMenuItem(text = { Text(value) }, onClick = { unit = value; unitMenu = false; error = "" })
                            } }
                        }
                    }
                    PhotoReviewChoice(strings.tr("分类", "Category"), listOf("食品", "日用品", "药品", "其他"), category, translateOptions = true, enabled = !saving) { category = it }
                    PhotoReviewChoice(strings.tr("存放位置", "Location"), store.locations, location, enabled = !saving) { location = it }
                    TextButton(onClick = onDate, enabled = !saving, modifier = Modifier.fillMaxWidth().testTag("photo-expiry")) {
                        Text(if(expiry.isBlank()) strings.tr("有效期未填写 · 补拍 / 填写日期 ›", "No expiry date · Photograph / enter date ›") else strings.tr("有效期  ", "Expiry  ") + expiry + "  ›",
                            color = if(expiry.isBlank()) scheme.tertiary else scheme.onSurface, fontSize = 13.sp)
                    }
                }
            }
            OutlinedTextField(supplement, { supplement = it }, label = { Text(strings.tr("补充一句（可选）", "Add a note (optional)")) },
                placeholder = { Text(strings.tr("例如：放在冰箱里", "For example: put it in the fridge")) }, modifier = Modifier.fillMaxWidth(), enabled = !saving,
                trailingIcon = { IconButton(onClick = {
                    runCatching { voice.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        .putExtra(RecognizerIntent.EXTRA_LANGUAGE, if(strings.english) "en-US" else "zh-CN")) }
                        .onFailure { error = strings.tr("当前设备无法使用语音，可以直接输入。", "Voice input is unavailable. You can type instead.") }
                }, enabled = !saving) { ScanIcon("mic") } })
            if (supplement.isNotBlank()) TextButton(onClick = {
                store.locations.firstOrNull { supplement.contains(it) }?.let { location = it }
                val drafts = parseVoice(supplement)
                val draft = drafts.singleOrNull()
                if (draft != null && draft.quantity.isNotBlank() && InventoryContract.unit(draft.unit) != null) { quantity = draft.quantity; unit = InventoryContract.unit(draft.unit)!! }
                error = strings.tr("已应用明确的数量和位置，请核对。", "Applied explicit quantity and location. Please review.")
            }, enabled = !saving) { Text(strings.tr("应用补充信息", "Apply note"), fontSize = 12.sp) }
            TextButton(onClick = { expanded = !expanded }) { Text(strings.tr(if(expanded) "收起更多设置" else "更多设置", if(expanded) "Less" else "More settings"), fontSize = 12.sp) }
            if (expanded) {
                Field(strings.tr("最低库存", "Minimum stock"), minimum, { minimum = it }, numeric = true)
                if (result.rawText.isNotBlank()) Text(result.rawText, fontSize = 11.sp, color = scheme.onSurfaceVariant)
            }
        }
        Surface(color = scheme.background) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                if(error.isNotBlank()) Text(error, color = scheme.error, fontSize = 12.sp, modifier = Modifier.testTag("photo-review-error"))
                Text(strings.tr("核对后才会加入库存", "Inventory changes only after confirmation"), color = scheme.onSurfaceVariant, fontSize = 11.sp)
                Button(onClick = {
                    focus.clearFocus()
                    val amount = InventoryContract.amount(quantity, positive = true)
                    val min = InventoryContract.amount(minimum.ifBlank { "0" })
                    error = when {
                        name.isBlank() || name.trim().length > 80 -> strings.tr("请填写1至80字的物品名称", "Enter an item name of 1–80 characters")
                        amount == null -> strings.tr("请核对数量，需要有效正数", "Review the quantity; enter a positive number")
                        InventoryContract.unit(unit) == null -> strings.tr("请选择计量单位，包装容量不会自动换算", "Choose a unit; package size is not converted automatically")
                        location.isBlank() -> strings.tr("请选择存放位置", "Choose a location")
                        min == null -> strings.tr("请核对最低库存", "Review minimum stock")
                        expiry.isNotBlank() && runCatching { LocalDate.parse(expiry) }.isFailure -> strings.tr("请核对有效期", "Review the expiry date")
                        else -> ""
                    }
                    if(error.isEmpty()) {
                        val item = StockItem(id = id, name = name.trim(), quantity = amount!!.toDouble(), unit = InventoryContract.unit(unit)!!,
                            category = category, location = location, minimum = min!!.toDouble(), expiry = expiry, image = result.displayUri, quantityExact = quantity.trim())
                        val old = if(store.cloud.signedIn) null else store.items.firstOrNull { it.id != id && it.name.equals(item.name, true) }
                        if(old != null) { duplicate = old; pending = item } else save(item)
                    }
                }, enabled = !saving && !completed && !store.cloud.busy && !store.cloud.expired && store.storageError == null,
                    modifier = Modifier.fillMaxWidth().padding(top = 7.dp).heightIn(min = 48.dp).testTag("photo-confirm")) {
                    Text(strings.tr(if(saving) "正在保存…" else "确认入库", if(saving) "Saving…" else "Confirm and add"))
                }
            }
        }
    }
    }
    duplicate?.let { old ->
        val item = pending
        val compatible = item != null && old.unit == item.unit && old.expiry == item.expiry && old.location == item.location
        AlertDialog(onDismissRequest = { duplicate = null }, title = { Text(strings.tr("已有同名物品", "An item has this name")) },
            text = { Text(if(compatible) strings.tr("是否增加到现有库存？", "Add this quantity to the existing item?") else
                strings.tr("当前本地记录的日期、位置或单位不同。请修改名称后单独保存，避免覆盖原记录。", "The local item's date, location or unit differs. Use a distinct name to keep both records.")) },
            dismissButton = { TextButton(onClick = { duplicate = null }) { Text(strings.tr("返回核对", "Review")) } },
            confirmButton = { if(compatible) TextButton(onClick = { duplicate = null; item?.let { save(it, "入库") } }) { Text(strings.tr("增加库存", "Add stock")) } })
    }
}

@Composable
private fun PhotoReviewChoice(label: String, options: List<String>, value: String, translateOptions: Boolean = false, enabled: Boolean, change: (String) -> Unit) {
    val strings = rememberUiStrings()
    var expanded by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { expanded = true }, enabled = enabled, modifier = Modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 4.dp)) {
            Text(label, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f), textAlign = TextAlign.Start)
            Text(if(translateOptions) strings.label(value) else value, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
            Text("  ›", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        DropdownMenu(expanded, { expanded = false }) { options.forEach { option ->
            DropdownMenuItem(text = { Text(if(translateOptions) strings.label(option) else option) }, onClick = { change(option); expanded = false })
        } }
    }
}

@Composable
private fun PhotoDateDialog(suggestion: String, dismiss: () -> Unit, camera: () -> Unit, apply: (String) -> Unit) {
    val strings = rememberUiStrings()
    var value by rememberSaveable(suggestion) { mutableStateOf(suggestion) }
    var invalid by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = dismiss, title = { Text(strings.tr("核对有效期", "Review expiry date")) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(strings.tr(if(suggestion.isBlank()) "未明确读到有效期时，请填写包装标注的到期日期。" else "请确认读到的是有效期，而不是生产日期。",
                if(suggestion.isBlank()) "Enter the expiry date printed on the package." else "Confirm this is the expiry date, not the production date."), fontSize = 13.sp)
            OutlinedTextField(value, { value = it; invalid = false }, label = { Text("YYYY-MM-DD") }, singleLine = true, isError = invalid, modifier = Modifier.testTag("photo-date-input"))
            TextButton(onClick = camera) { Text(strings.tr("补拍日期", "Photograph the date")) }
        }
    }, dismissButton = { TextButton(onClick = dismiss) { Text(strings.tr("取消", "Cancel")) } }, confirmButton = {
        TextButton(onClick = { if(value.isBlank() || runCatching { LocalDate.parse(value) }.isSuccess) apply(value) else invalid = true }) {
            Text(strings.tr("使用此日期", "Use this date"))
        }
    })
}

private fun encodePhotoResult(result: PhotoRecognitionResult) = JSONObject().apply {
    put("original", result.originalUri); put("display", result.displayUri); put("text", result.rawText)
    put("cutout", result.cutout); put("available", result.textAvailable)
    put("name", result.draft.name); put("spec", result.draft.specification); put("unit", result.draft.unit)
    put("category", result.draft.category); put("expiry", result.draft.expiry)
}.toString()

private fun decodePhotoResult(value: String): PhotoRecognitionResult? = runCatching {
    if(value.isBlank()) null else JSONObject(value).let { json -> PhotoRecognitionResult(json.getString("original"), json.getString("display"),
        PhotoDraft(json.optString("name"), json.optString("spec"), json.optString("unit"), json.optString("category", "其他"), json.optString("expiry")),
        json.optString("text"), json.optBoolean("cutout"), json.optBoolean("available")) }
}.getOrNull()
