package com.example.teamapp.ui

import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.*
import com.example.teamapp.R
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.theme.appearanceFade
import com.example.teamapp.ui.ring.RingInventoryPage
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal val Red: Color
    @Composable get() = if (LocalLightDesign.current) Color(0xFFB44848) else MaterialTheme.colorScheme.error
internal fun emoji(item: StockItem) = when { item.name.contains("奶") -> "🥛"; item.name.contains("蛋") -> "🥚"; item.name.contains("苹果") -> "🍎"; item.name.contains("面包") -> "🍞"; item.category == "日用品" -> "🧴"; else -> "🥬" }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MagicApp(store: InventoryStore, onOpenAuth: () -> Unit = {}) {
    val lightDesign = LocalLightDesign.current
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var panel by rememberSaveable { mutableStateOf<String?>(null) }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var initialQuestion by rememberSaveable { mutableStateOf("") }
    val conversation = rememberSaveable(store.cloud.scopeKey, saver = listSaver<androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, String>(
        save = { messages -> messages.flatMap { listOf(it.first, if (it.second) "user" else "assistant") } },
        restore = { saved -> mutableStateListOf<Pair<String, Boolean>>().apply { saved.chunked(2).forEach { add(it[0] to (it[1] == "user")) } } }
    )) { mutableStateListOf<Pair<String, Boolean>>() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val pageStates = rememberSaveableStateHolder()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var closingPanel by remember { mutableStateOf(false) }
    fun closePanel() {
        if (closingPanel || panel == null) return
        focus.clearFocus()
        closingPanel = true
        scope.launch {
            try {
                sheetState.hide()
                if (!sheetState.isVisible) panel = null
            } finally { closingPanel = false }
        }
    }
    fun selectTab(value: Int) { focus.clearFocus(); tab = value }
    val notify: (String) -> Unit = { message -> scope.launch { snackbar.showSnackbar(if (store.cloud.signedIn) message else store.storageError ?: message) } }
    val openItem: (StockItem) -> Unit = { selected = it.id; panel = "详情" }
    val item = store.items.firstOrNull { it.id == selected }
    // A deleted item's sheet keeps its last frame while sliding off screen.
    var retainedItem by remember(selected) { mutableStateOf(item) }
    SideEffect { if (item != null) retainedItem = item }
    val sheetItem = item ?: retainedItem
    val pageTravel = with(LocalDensity.current) { 28.dp.roundToPx() }
    BackHandler(panel != null) { closePanel() }
    AssistantPullLayer(tab, panel == null, store, conversation, snackbar, notify) { headerModifier ->
        Scaffold(snackbarHost = { SnackbarHost(snackbar) }, bottomBar = {
            if (lightDesign) DesignNavigation(tab) { selectTab(it) } else {
                DarkNavigation(tab) { selectTab(it) }
            }
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding)) {
                AppHeader(tab, store, { panel = "提醒" }, headerModifier)
                CloudStatus(store, onOpenAuth)
                if (store.storageError != null && !store.cloud.signedIn) {
                    Text(store.storageError!!, color = Red, modifier = Modifier.padding(22.dp))
                    Button(onClick = { panel = "隐私与安全" }, modifier = Modifier.padding(horizontal = 22.dp)) { Text("导出数据 / 数据管理") }
                } else AnimatedContent(tab, Modifier.weight(1f).fillMaxWidth(), transitionSpec = {
                    val direction = if (targetState > initialState) 1 else -1
                    (fadeIn(tween(AppMotion.Duration)) + slideInHorizontally(tween(AppMotion.Page, easing = AppMotion.easing)) { direction * pageTravel })
                        .togetherWith(fadeOut(tween(AppMotion.Quick)) + slideOutHorizontally(tween(AppMotion.Duration, easing = AppMotion.easing)) { -direction * pageTravel / 2 })
                        .using(null)
                }, label = "main-page") { page ->
                    pageStates.SaveableStateProvider(page) {
                        Box(Modifier.fillMaxSize().motionInput(page == tab)) {
                            when (page) {
                                0 -> Home(store, openItem, { selectTab(1) }, { panel = it }, { initialQuestion = it; panel = "AI 智能管家" })
                                1 -> RingInventoryPage(store, openItem, { panel = "手动添加" })
                                2 -> Shopping(store, { id, p -> selected = id; panel = p }, notify)
                                3 -> Profile(store) { if (it == "登录 / 注册") onOpenAuth() else panel = it }
                            }
                        }
                    }
                }
            }
        }
    }
    if (panel != null) {
        ModalBottomSheet(onDismissRequest = { panel = null }, sheetState = sheetState, modifier = Modifier.appearanceFade(),
            containerColor = if (lightDesign) BottomSheetDefaults.ContainerColor else MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface) {
            Column(Modifier.fillMaxWidth().fillMaxHeight(0.92f).imePadding().motionInput(!closingPanel)) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    AppMotionContent(panel.orEmpty(), Modifier.weight(1f), label = "panel-title") { title ->
                        Text(when (title) {
                            "AI 智能管家" -> stringResource(R.string.brand_assistant_title)
                            "库存检测规则" -> "库存规则"
                            else -> title
                        },
                            style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    }
                    TextButton(onClick = { closePanel() }) { Text("关闭") }
                }
                if (!lightDesign) HorizontalDivider(color = DarkLine, modifier = Modifier.padding(top = 10.dp))
                AppMotionContent(panel.orEmpty(), Modifier.weight(1f).fillMaxWidth(), label = "panel-content") { route ->
                    when (route) {
                        "AI 智能管家" -> Chat(store, conversation, initialQuestion, { initialQuestion = "" }, notify)
                        "拍照添加", "语音添加", "手动添加" -> AddFlow(store, route, notify) { closePanel() }
                        "编辑物品" -> sheetItem?.let { Editor(store, it, notify = notify, onSaved = { focus.clearFocus(); panel = "详情" }) }
                        "详情" -> sheetItem?.let { Detail(store, it, { panel = it }, notify) { closePanel() } }
                        "加入采购清单", "调整采购数量", "购买入库", "增加库存", "消耗库存" -> sheetItem?.let { QuantityAction(store, it, route, notify) { closePanel() } }
                        "提醒" -> Attention(store, openItem)
                        else -> SettingsPanel(store, route, notify) { closePanel() }
                    }
                }
            }
        }
    }
}

@Composable
private fun Home(store: InventoryStore, open: (StockItem) -> Unit, all: () -> Unit, panel: (String) -> Unit, ask: (String) -> Unit) {
    if (LocalLightDesign.current) DesignHome(store, open, all, panel, ask)
    else DarkHome(store, open, all, panel, ask)
}

@Composable
internal fun StockRow(item: StockItem, days: Int, action: () -> Unit) {
    if (LocalLightDesign.current) DesignStockRow(item, days, action)
    else DarkStockRow(item, days, action)
}

@Composable
private fun Shopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    if (store.cloud.signedIn) CloudShopping(store, action, notify)
    else if (LocalLightDesign.current) DesignShopping(store, action, notify)
    else DarkShopping(store, action, notify)
}

@Composable
private fun Profile(store: InventoryStore, open: (String) -> Unit) {
    if (LocalLightDesign.current) DesignProfile(store, open)
    else DarkProfile(store, open)
}

@Composable
internal fun Empty(title: String, subtitle: String) {
    MewEmptyState(title, subtitle)
}

@Composable
private fun Attention(store: InventoryStore, open: (StockItem) -> Unit) {
    val rows = store.items.filter { val s = it.status(store.reminderDays); (s.low && store.notifications[0]) || (s.soon && store.notifications[1]) || (s.expired && store.notifications[2]) }.sortedBy { it.status(store.reminderDays).priority }
    LazyColumn(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text("App 内提醒 · 开关只影响提醒，库存状态保持真实", style = MaterialTheme.typography.bodySmall) }
        if (rows.isEmpty()) item { Empty("当前没有需要处理的提醒", "可在「我的 → 消息通知」管理提醒类别") }
        items(rows, key = { it.id }) { item -> Column(Modifier.animateItem()) { StockRow(item, store.reminderDays) { open(item) }; Text(reasons(item, store.reminderDays), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(8.dp)) } }
    }
}

internal fun reasons(item: StockItem, days: Int, concise: Boolean = false): String {
    val s = item.status(days)
    return buildList {
        if (s.low) add(if (concise) "缺 ${(item.minimum - item.quantity).display()} ${item.unit}" else "剩余 ${item.quantity.display()} ${item.unit}，低于最低库存 ${item.minimum.display()} ${item.unit}")
        if (s.expired) add(if (concise) "已过期 ${-s.days!!} 天，请核对处理" else "有效期 ${item.expiry}，已过期 ${-s.days!!} 天，请核对处理")
        if (s.soon) add(if (concise) "剩余 ${s.days} 天到期" else "有效期 ${item.expiry}，剩余 ${s.days} 天")
        if (!s.attention) add("当前库存状态正常")
        if (item.expiry.isBlank()) add("未设置有效期")
    }.joinToString(if (concise) "；" else "\n")
}

@Composable
private fun Detail(store: InventoryStore, item: StockItem, open: (String) -> Unit, notify: (String) -> Unit, close: () -> Unit) {
    var deleting by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val operationId = rememberSaveable(item.id) { java.util.UUID.randomUUID().toString() }
    if (!LocalLightDesign.current) DarkDetail(store, item, open) { deleting = true } else {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Photo(item.image)
        Text("${emoji(item)} ${item.name}", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("${item.quantity.display()} ${item.unit}", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
        Text("${item.category} · ${item.location}\n最低库存：${item.minimum.display()} ${item.unit}\n有效期：${item.expiry.ifBlank { "未设置" }}")
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) { Text(reasons(item, store.reminderDays, concise = true), modifier = Modifier.fillMaxWidth().padding(12.dp)) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { OutlinedButton(onClick = { open("编辑物品") }) { Text("编辑") }; OutlinedButton(onClick = { open("增加库存") }) { Text("入库") }; OutlinedButton(onClick = { open("消耗库存") }) { Text("消耗") } }
        Button(onClick = { open(if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }, modifier = Modifier.fillMaxWidth()) { Text("加入清单 / 调整") }
        Text("数量记录", fontWeight = FontWeight.Bold)
        item.history.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
        TextButton(onClick = { deleting = true }) { Text("删除物品", color = Red) }
    }
    }
    if (deleting) Confirm("删除${item.name}？", if (store.cloud.signedIn) "从当前库存移除该批次，服务器保留购买来源及历史。已有采购项保留，供家庭成员核对。" else "库存记录、数量历史和对应采购任务将一起删除。", { deleting = false }) {
        scope.launch { runCatching { store.deleteItemSynced(item, operationId) }.onSuccess { notify("已删除${item.name}"); close() }.onFailure { notify(it.message ?: "删除失败") }; deleting = false }
    }
}

@Composable
private fun QuantityAction(store: InventoryStore, item: StockItem, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    val scope = rememberCoroutineScope()
    val operationId = rememberSaveable(item.id, mode) { java.util.UUID.randomUUID().toString() }
    var submitting by remember { mutableStateOf(false) }
    var quantity by rememberSaveable(item.id, mode) { mutableStateOf(if (mode == "加入采购清单") maxOf(item.minimum - item.quantity, 1.0).display() else if (mode == "调整采购数量") store.purchases.firstOrNull { it.itemId == item.id }?.quantity?.display().orEmpty() else "") }
    var error by remember { mutableStateOf("") }
    Column(Modifier.padding(22.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(item.name, style = MaterialTheme.typography.titleLarge)
        Text("当前库存 ${item.quantity.display()} ${item.unit}")
        ModeNotice(if (mode == "购买入库") "已购买？请核对实际购入数量。计划数量不会自动入库。" else if (mode.contains("采购")) "核对计划购买数量，确认后保存至清单。" else "核对本次数量后确认，库存将同步更新。")
        OutlinedTextField(quantity, { quantity = it; error = "" }, label = { Text("${if (mode == "购买入库") "实际购入" else "本次"}数量（${item.unit}）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), isError = error.isNotBlank(), supportingText = { MotionErrorText(error) }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            val amount = positiveNumber(quantity)
            if (amount == null) error = "请输入有效正数" else if (!submitting) scope.launch {
                submitting = true
                try {
                    when (mode) {
                        "购买入库" -> store.receive(item.id, amount)
                        "增加库存" -> store.changeQuantitySynced(item, amount, operationId)
                        "消耗库存" -> store.changeQuantitySynced(item, -amount, operationId)
                        else -> store.planSynced(item, amount, operationId)
                    }
                    notify(if (mode == "购买入库" || mode == "增加库存") "${item.name}已增加 ${amount.display()} ${item.unit}" else if (mode == "消耗库存") "已记录消耗 ${amount.display()} ${item.unit}" else "采购计划已保存"); close()
                } catch (failure: Exception) { error = failure.message ?: "保存失败" }
                finally { submitting = false }
            }
        }, enabled = !submitting && !store.cloud.busy && !store.cloud.expired, modifier = Modifier.fillMaxWidth()) { Text(if (submitting) "正在保存…" else if (mode == "购买入库") "确认入库" else "确认保存") }
    }
}

@Composable
internal fun Chat(store: InventoryStore, conversation: androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, initial: String, consumed: () -> Unit, notify: (String) -> Unit, showIntro: Boolean = true) {
    if (store.cloud.signedIn) {
        key(store.cloud.scopeKey) { CloudAssistant(store.cloud, initial, consumed, showIntro = showIntro) }
        return
    }
    val lightDesign = LocalLightDesign.current
    var input by rememberSaveable { mutableStateOf("") }
    var confirming by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var asking by remember { mutableStateOf(false) }
    fun send(text: String) {
        if (text.isNotBlank() && !asking) {
            conversation.add(text to true); input = ""
            conversation.add(answerInventory(text, store.items, store.reminderDays) to false)
        }
    }
    LaunchedEffect(initial) { if (initial.isNotBlank()) { send(initial); consumed() } }
    Column(Modifier.padding(horizontal = 22.dp)) {
        if (showIntro) MewChatIntro()
        if (store.cloud.signedIn) Text("服务器家庭库存问答 · AI 草稿尚未执行，库存操作请核对后确认", style = MaterialTheme.typography.bodySmall)
        else if (!showIntro) Text("依据本机库存 · 补货需确认", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        else if (LocalLightDesign.current) Text("本地库存问答 · 每次提问重新读取当前记录\n历史回答保留当时快照，请追问以获取最新数量。", style = MaterialTheme.typography.bodySmall)
        else DarkNotice("本地库存问答 · 每次提问重新读取当前记录\n历史回答保留当时快照，请追问以获取最新数量。")
        val scroll = androidx.compose.foundation.lazy.rememberLazyListState()
        LaunchedEffect(conversation.size) { if (conversation.isNotEmpty()) scroll.animateScrollToItem(conversation.lastIndex) }
        LazyColumn(Modifier.weight(1f).padding(vertical = 8.dp), state = scroll, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (conversation.isEmpty()) item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().padding(12.dp)) {
                        Text("想查点什么？", fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 24.sp)
                    }
                }
            }
            if (showIntro && conversation.isEmpty() && !lightDesign) item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuggestionChip(onClick = { send("哪些快过期了？") }, label = { Text("临期物品", fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                    SuggestionChip(onClick = { send("需要补什么？") }, label = { Text("补货建议", fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                }
            }
            itemsIndexed(conversation.toList(), key = { index, _ -> "message-$index" }) { _, (message, user) -> Card(colors = CardDefaults.cardColors(containerColor = if (user) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant), modifier = Modifier.animateItem().fillMaxWidth().padding(start = if (user) 32.dp else 0.dp, end = if (user) 0.dp else 18.dp)) { Column(Modifier.padding(14.dp)) { Text(if (user) "你" else "✦ Mew", style = MaterialTheme.typography.labelSmall); Text(message) } } }
        }
        TextButton(onClick = { confirming = true }, enabled = store.items.any { it.status(store.reminderDays).low }) { Text("核对补货") }
        Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(input, { input = it }, placeholder = { Text("输入问题…") }, modifier = Modifier.weight(1f)); TextButton(onClick = { send(input) }, enabled = !asking) { Text(if (asking) "查询中…" else "发送") } }
        Spacer(Modifier.height(16.dp))
    }
    if (confirming) {
        val low = store.items.filter { it.status(store.reminderDays).low && store.purchases.none { p -> p.itemId == it.id } }
        Confirm("确认补货建议", if (low.isEmpty()) "这些物品已在清单中，无需重复添加。" else low.joinToString("\n") { "${it.name}：${(it.minimum - it.quantity).display()} ${it.unit}" }, { confirming = false }) {
            scope.launch { runCatching { low.forEach { store.planSynced(it, it.minimum - it.quantity, java.util.UUID.randomUUID().toString()) } }
                .onSuccess { notify(if (low.isEmpty()) "采购任务已存在" else "已加入采购清单") }.onFailure { notify(it.message ?: "部分操作可能已保存，请刷新核对") }; confirming = false }
        }
    }
}

@Composable
internal fun Confirm(title: String, body: String, cancel: () -> Unit, confirm: () -> Unit) {
    AlertDialog(onDismissRequest = cancel, modifier = Modifier.appearanceFade(), title = { Text(title) }, text = { Text(body) }, dismissButton = { TextButton(onClick = cancel) { Text("取消") } }, confirmButton = { TextButton(onClick = confirm) { Text("确认") } })
}

@Composable
internal fun Photo(uri: String) {
    val context = LocalContext.current
    // File access and bitmap decoding must not block the sheet's entrance or a form transition.
    val bitmap by produceState<android.graphics.Bitmap?>(null, uri, context) {
        value = null
        if (uri.isNotBlank()) value = withContext(Dispatchers.IO) {
            runCatching { context.contentResolver.openInputStream(Uri.parse(uri))?.use { stream ->
                BitmapFactory.decodeStream(stream, null, BitmapFactory.Options().apply { inSampleSize = 4 })
            } }.getOrNull()
        }
    }
    if (uri.isNotBlank()) Box(Modifier.fillMaxWidth().height(160.dp), contentAlignment = Alignment.Center) {
        AnimatedVisibility(bitmap != null, enter = fadeIn(tween(AppMotion.Duration)), exit = fadeOut(tween(AppMotion.Quick))) {
            bitmap?.let { Image(it.asImageBitmap(), "物品照片", modifier = Modifier.fillMaxWidth().height(160.dp)) }
        }
    }
}
