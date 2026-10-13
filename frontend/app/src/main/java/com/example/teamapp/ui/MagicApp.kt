package com.example.teamapp.ui

import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.*
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.launch

internal val Red: Color
    @Composable get() = if (LocalLightDesign.current) Color(0xFFB44848) else MaterialTheme.colorScheme.error
internal fun emoji(item: StockItem) = when { item.name.contains("奶") -> "🥛"; item.name.contains("蛋") -> "🥚"; item.name.contains("苹果") -> "🍎"; item.name.contains("面包") -> "🍞"; item.category == "日用品" -> "🧴"; else -> "🥬" }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MagicApp(store: InventoryStore) {
    val lightDesign = LocalLightDesign.current
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var panel by rememberSaveable { mutableStateOf<String?>(null) }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var initialQuestion by rememberSaveable { mutableStateOf("") }
    val conversation = rememberSaveable(saver = listSaver<androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, String>(
        save = { messages -> messages.flatMap { listOf(it.first, if (it.second) "user" else "assistant") } },
        restore = { saved -> mutableStateListOf<Pair<String, Boolean>>().apply { saved.chunked(2).forEach { add(it[0] to (it[1] == "user")) } } }
    )) { mutableStateListOf<Pair<String, Boolean>>() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val notify: (String) -> Unit = { message -> scope.launch { snackbar.showSnackbar(store.storageError ?: message) } }
    val openItem: (StockItem) -> Unit = { selected = it.id; panel = "详情" }
    val item = store.items.firstOrNull { it.id == selected }
    BackHandler(panel != null) { panel = null }
    Scaffold(snackbarHost = { SnackbarHost(snackbar) }, bottomBar = {
        if (lightDesign) DesignNavigation(tab) { tab = it; panel = null } else {
            DarkNavigation(tab) { tab = it; panel = null }
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (lightDesign) DesignHeader(tab, store, { panel = "提醒" }, { tab = 3 }) else {
                DarkHeader(tab, store, { panel = "提醒" }, { tab = 3 })
            }
            if (store.storageError != null) {
                Text(store.storageError!!, color = Red, modifier = Modifier.padding(22.dp))
                Button(onClick = { panel = "隐私与安全" }, modifier = Modifier.padding(horizontal = 22.dp)) { Text("导出数据 / 数据管理") }
            } else when (tab) {
                0 -> Home(store, openItem, { tab = 1 }, { panel = it }, { initialQuestion = it; panel = "AI 智能管家" })
                1 -> Inventory(store, openItem, { panel = "手动添加" }, { panel = "语音添加" })
                2 -> Shopping(store, { id, p -> selected = id; panel = p }, notify)
                3 -> Profile(store) { panel = it }
            }
        }
    }
    if (panel != null) {
        ModalBottomSheet(onDismissRequest = { panel = null }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = if (lightDesign) BottomSheetDefaults.ContainerColor else MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface) {
            Column(Modifier.fillMaxWidth().fillMaxHeight(0.92f).imePadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(panel!!, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    TextButton(onClick = { panel = null }) { Text("关闭") }
                }
                if (!lightDesign) HorizontalDivider(color = DarkLine, modifier = Modifier.padding(top = 10.dp))
                when (panel) {
                    "AI 智能管家" -> Chat(store, conversation, initialQuestion, { initialQuestion = "" }, notify)
                    "拍照添加", "语音添加", "手动添加" -> AddFlow(store, panel!!, notify) { panel = null }
                    "编辑物品" -> item?.let { Editor(store, it, notify = notify, onSaved = { panel = "详情" }) }
                    "详情" -> item?.let { Detail(store, it, { panel = it }, notify) { panel = null } }
                    "加入采购清单", "调整采购数量", "购买入库", "增加库存", "消耗库存" -> item?.let { QuantityAction(store, it, panel!!, notify) { panel = null } }
                    "提醒" -> Attention(store, openItem)
                    else -> SettingsPanel(store, panel!!, notify) { panel = null }
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
private fun Inventory(store: InventoryStore, open: (StockItem) -> Unit, add: () -> Unit, voice: () -> Unit) {
    if (LocalLightDesign.current) DesignInventory(store, open, add, voice)
    else DarkInventory(store, open, add, voice)
}

@Composable
internal fun StockRow(item: StockItem, days: Int, action: () -> Unit) {
    if (LocalLightDesign.current) DesignStockRow(item, days, action)
    else DarkStockRow(item, days, action)
}

@Composable
private fun Shopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    if (LocalLightDesign.current) DesignShopping(store, action, notify)
    else DarkShopping(store, action, notify)
}

@Composable
private fun Profile(store: InventoryStore, open: (String) -> Unit) {
    if (LocalLightDesign.current) DesignProfile(store, open)
    else DarkProfile(store, open)
}

@Composable
internal fun Empty(title: String, subtitle: String) {
    if (LocalLightDesign.current) DesignEmpty(title, subtitle)
    else DarkEmpty(title, subtitle)
}

@Composable
private fun Attention(store: InventoryStore, open: (StockItem) -> Unit) {
    val rows = store.items.filter { val s = it.status(store.reminderDays); (s.low && store.notifications[0]) || (s.soon && store.notifications[1]) || (s.expired && store.notifications[2]) }.sortedBy { it.status(store.reminderDays).priority }
    LazyColumn(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text("App 内提醒 · 开关只影响提醒，库存状态保持真实", style = MaterialTheme.typography.bodySmall) }
        if (rows.isEmpty()) item { Empty("当前没有需要处理的提醒", "可在「我的 → 消息通知」管理提醒类别") }
        items(rows, key = { it.id }) { item -> Column { StockRow(item, store.reminderDays) { open(item) }; Text(reasons(item, store.reminderDays), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(8.dp)) } }
    }
}

internal fun reasons(item: StockItem, days: Int): String {
    val s = item.status(days)
    return buildList {
        if (s.low) add("剩余 ${item.quantity.display()} ${item.unit}，低于最低库存 ${item.minimum.display()} ${item.unit}")
        if (s.expired) add("有效期 ${item.expiry}，已过期 ${-s.days!!} 天，请核对处理")
        if (s.soon) add("有效期 ${item.expiry}，剩余 ${s.days} 天")
        if (!s.attention) add("当前库存状态正常")
        if (item.expiry.isBlank()) add("未设置有效期")
    }.joinToString("\n")
}

@Composable
private fun Detail(store: InventoryStore, item: StockItem, open: (String) -> Unit, notify: (String) -> Unit, close: () -> Unit) {
    var deleting by remember { mutableStateOf(false) }
    if (!LocalLightDesign.current) DarkDetail(store, item, open) { deleting = true } else {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Photo(item.image)
        Text("${emoji(item)} ${item.name}", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("${item.quantity.display()} ${item.unit}", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
        Text("${item.category} · ${item.location}\n最低库存：${item.minimum.display()} ${item.unit}\n有效期：${item.expiry.ifBlank { "未设置" }}")
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) { Text(reasons(item, store.reminderDays), modifier = Modifier.fillMaxWidth().padding(16.dp)) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { OutlinedButton(onClick = { open("编辑物品") }) { Text("编辑") }; OutlinedButton(onClick = { open("增加库存") }) { Text("入库") }; OutlinedButton(onClick = { open("消耗库存") }) { Text("消耗") } }
        Button(onClick = { open(if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }, modifier = Modifier.fillMaxWidth()) { Text("加入采购清单 / 调整计划") }
        Text("最近数量变化", fontWeight = FontWeight.Bold)
        item.history.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
        TextButton(onClick = { deleting = true }) { Text("删除物品", color = Red) }
    }
    }
    if (deleting) Confirm("删除${item.name}？", "库存记录、数量历史和对应采购任务将一起删除。", { deleting = false }) { store.deleteItem(item.id); notify("已删除${item.name}"); close() }
}

@Composable
private fun QuantityAction(store: InventoryStore, item: StockItem, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    var quantity by rememberSaveable(item.id, mode) { mutableStateOf(if (mode == "加入采购清单") maxOf(item.minimum - item.quantity, 1.0).display() else if (mode == "调整采购数量") store.purchases.firstOrNull { it.itemId == item.id }?.quantity?.display().orEmpty() else "") }
    var error by remember { mutableStateOf("") }
    Column(Modifier.padding(22.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(item.name, style = MaterialTheme.typography.titleLarge)
        Text("当前库存 ${item.quantity.display()} ${item.unit}")
        ModeNotice(if (mode == "购买入库") "已购买？请核对实际购入数量。计划数量不会自动入库。" else if (mode.contains("采购")) "核对计划购买数量，确认后保存至清单。" else "核对本次数量后确认，库存将同步更新。")
        OutlinedTextField(quantity, { quantity = it; error = "" }, label = { Text("${if (mode == "购买入库") "实际购入" else "本次"}数量（${item.unit}）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), isError = error.isNotBlank(), supportingText = { Text(error) }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            val amount = positiveNumber(quantity)
            if (amount == null) error = "请输入有效正数" else runCatching {
                when (mode) { "购买入库" -> store.receive(item.id, amount); "增加库存" -> store.changeQuantity(item.id, amount); "消耗库存" -> store.changeQuantity(item.id, -amount); else -> store.plan(item.id, amount) }
            }.onSuccess { notify(if (mode == "购买入库" || mode == "增加库存") "${item.name}已增加 ${amount.display()} ${item.unit}" else if (mode == "消耗库存") "已记录消耗 ${amount.display()} ${item.unit}" else "采购计划已保存"); close() }.onFailure { error = it.message ?: "保存失败" }
        }, modifier = Modifier.fillMaxWidth()) { Text(if (mode == "购买入库") "确认入库" else "确认保存") }
    }
}

@Composable
private fun Chat(store: InventoryStore, conversation: androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, initial: String, consumed: () -> Unit, notify: (String) -> Unit) {
    val lightDesign = LocalLightDesign.current
    var input by rememberSaveable { mutableStateOf("") }
    var confirming by remember { mutableStateOf(false) }
    fun send(text: String) { if (text.isNotBlank()) { conversation.add(text to true); conversation.add(answerInventory(text, store.items, store.reminderDays) to false); input = "" } }
    LaunchedEffect(Unit) { if (initial.isNotBlank()) send(initial); consumed() }
    Column(Modifier.padding(horizontal = 22.dp)) {
        if (LocalLightDesign.current) DesignChatIntro()
        if (LocalLightDesign.current) Text("本地库存问答 · 每次提问重新读取当前记录\n历史回答保留当时快照，请追问以获取最新数量。", style = MaterialTheme.typography.bodySmall)
        else DarkNotice("本地库存问答 · 每次提问重新读取当前记录\n历史回答保留当时快照，请追问以获取最新数量。")
        val scroll = androidx.compose.foundation.lazy.rememberLazyListState()
        LaunchedEffect(conversation.size) { if (conversation.isNotEmpty()) scroll.animateScrollToItem(conversation.lastIndex) }
        LazyColumn(Modifier.weight(1f).padding(vertical = 12.dp), state = scroll, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (conversation.isEmpty()) item { Empty("今天需要我帮你查看什么？", "试试「哪些快过期了」或「需要补什么」") }
            if (conversation.isEmpty() && !lightDesign) item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuggestionChip(onClick = { send("哪些快过期了？") }, label = { Text("哪些快过期了？", fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                    SuggestionChip(onClick = { send("需要补什么？") }, label = { Text("需要补什么？", fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                }
            }
            items(conversation.toList()) { (message, user) -> Card(colors = CardDefaults.cardColors(containerColor = if (user) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant), modifier = Modifier.fillMaxWidth().padding(start = if (user) 32.dp else 0.dp, end = if (user) 0.dp else 18.dp)) { Column(Modifier.padding(14.dp)) { Text(if (user) "你" else "✦ 库存助手", style = MaterialTheme.typography.labelSmall); Text(message) } } }
        }
        TextButton(onClick = { confirming = true }, enabled = store.items.any { it.status(store.reminderDays).low }) { Text("核对并加入补货清单") }
        Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(input, { input = it }, placeholder = { Text("继续问问…") }, modifier = Modifier.weight(1f)); TextButton(onClick = { send(input) }) { Text("发送") } }
        Spacer(Modifier.height(16.dp))
    }
    if (confirming) {
        val low = store.items.filter { it.status(store.reminderDays).low && store.purchases.none { p -> p.itemId == it.id } }
        Confirm("确认补货建议", if (low.isEmpty()) "这些物品已在清单中，无需重复添加。" else low.joinToString("\n") { "${it.name}：${(it.minimum - it.quantity).display()} ${it.unit}" }, { confirming = false }) { low.forEach { store.plan(it.id, it.minimum - it.quantity) }; confirming = false; notify(if (low.isEmpty()) "采购任务已存在" else "已加入采购清单") }
    }
}

@Composable
internal fun Confirm(title: String, body: String, cancel: () -> Unit, confirm: () -> Unit) {
    AlertDialog(onDismissRequest = cancel, title = { Text(title) }, text = { Text(body) }, dismissButton = { TextButton(onClick = cancel) { Text("取消") } }, confirmButton = { TextButton(onClick = confirm) { Text("确认") } })
}

@Composable
internal fun Photo(uri: String) {
    val context = LocalContext.current
    val bitmap = remember(uri) { if (uri.isBlank()) null else runCatching { context.contentResolver.openInputStream(Uri.parse(uri))?.use { stream -> BitmapFactory.decodeStream(stream, null, BitmapFactory.Options().apply { inSampleSize = 4 }) } }.getOrNull() }
    bitmap?.let { Image(it.asImageBitmap(), "物品照片", modifier = Modifier.fillMaxWidth().height(160.dp)) }
}
