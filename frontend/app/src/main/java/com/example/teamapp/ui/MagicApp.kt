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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Notifications
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
import kotlinx.coroutines.launch

internal val Green = Color(0xFF247D67)
internal val Red = Color(0xFFB44848)
private val Amber = Color(0xFFAA681C)
private val tabs = listOf("首页", "库存", "清单", "我的")
private val navigationIcons = listOf(Icons.Default.Home, Icons.AutoMirrored.Filled.List, Icons.Default.ShoppingCart, Icons.Default.Person)
internal fun emoji(item: StockItem) = when { item.name.contains("奶") -> "🥛"; item.name.contains("蛋") -> "🥚"; item.name.contains("苹果") -> "🍎"; item.name.contains("面包") -> "🍞"; item.category == "日用品" -> "🧴"; else -> "🥬" }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MagicApp(store: InventoryStore) {
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
        NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
            tabs.forEachIndexed { index, title -> NavigationBarItem(selected = index == tab, onClick = { tab = index; panel = null }, icon = { Icon(navigationIcons[index], contentDescription = null) }, label = { Text(title) }) }
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(listOf("你好，欢迎回家", "我的库存", "采购清单", "我的")[tab], style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(listOf(store.family + " · 让生活井井有条", "家里的每件物品，都心中有数", "补齐生活所需", "照顾你的家，也照顾你的偏好")[tab], style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                val count = store.items.count { val s = it.status(store.reminderDays); (s.low && store.notifications[0]) || (s.soon && store.notifications[1]) || (s.expired && store.notifications[2]) }
                IconButton(onClick = { panel = "提醒" }) { BadgedBox(badge = { if (count > 0) Badge { Text(count.toString()) } }) { Icon(Icons.Default.Notifications, contentDescription = "库存提醒") } }
                if (tab == 0) IconButton(onClick = { tab = 3 }) { Icon(Icons.Default.Person, contentDescription = "个人中心") }
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
        ModalBottomSheet(onDismissRequest = { panel = null }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
            Column(Modifier.fillMaxWidth().fillMaxHeight(0.92f).imePadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(panel!!, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    TextButton(onClick = { panel = null }) { Text("关闭") }
                }
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
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = RoundedCornerShape(26.dp)) {
            Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) { Text("MAGICVVU · HOME ASSISTANT", fontSize = 10.sp, letterSpacing = 1.sp); Text("AI 智能管家", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
                    Text("✦", fontSize = 44.sp)
                }
                val low = store.items.count { it.status(store.reminderDays).low }
                val soon = store.items.count { it.status(store.reminderDays).soon }
                val expired = store.items.count { it.status(store.reminderDays).expired }
                Text(if (store.items.isEmpty()) "从记录第一件物品开始，让家更有条理。" else "${store.items.size} 种物品已记录 · $low 种库存不足\n$soon 种即将过期 · $expired 种已过期")
                Text("本地库存助手 · 回答依据已确认记录", style = MaterialTheme.typography.labelSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuggestionChip(onClick = { ask("哪些快过期了？") }, label = { Text("哪些快过期了？", fontSize = 12.sp) })
                    SuggestionChip(onClick = { ask("需要补什么？") }, label = { Text("需要补什么？", fontSize = 12.sp) })
                }
                var question by rememberSaveable { mutableStateOf("") }
                OutlinedTextField(question, { question = it }, placeholder = { Text("问问家里的库存…") }, singleLine = true, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), trailingIcon = { TextButton(onClick = { if (question.isNotBlank()) { ask(question); question = "" } else panel("AI 智能管家") }) { Text("发送") } })
            }
        }
        Text("快捷添加", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            QuickCard("📷", "拍照添加", "拍一下，快速记录", Modifier.weight(1f)) { panel("拍照添加") }
            QuickCard("🎙", "语音添加", "说出来，轻松记录", Modifier.weight(1f)) { panel("语音添加") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) { Text("最近库存状态", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f)); TextButton(onClick = all) { Text("查看全部 ›") } }
        if (store.items.isEmpty()) Empty("还没有记录物品", "拍照、语音或手动添加第一件家庭物品")
        store.items.sortedBy { it.status(store.reminderDays).priority }.take(4).forEach { StockRow(it, store.reminderDays) { open(it) } }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun QuickCard(icon: String, title: String, subtitle: String, modifier: Modifier, action: () -> Unit) {
    Card(onClick = action, modifier = modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { Text(icon, color = MaterialTheme.colorScheme.primary, fontSize = 30.sp); Text(title, fontWeight = FontWeight.Bold); Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun Inventory(store: InventoryStore, open: (StockItem) -> Unit, add: () -> Unit, voice: () -> Unit) {
    var search by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableStateOf("全部") }
    Column(Modifier.padding(horizontal = 22.dp)) {
        OutlinedTextField(search, { search = it }, placeholder = { Text("搜索物品名称") }, singleLine = true, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth(), trailingIcon = { if (search.isNotEmpty()) TextButton(onClick = { search = "" }) { Text("清空") } })
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { listOf("全部", "需关注", "食品", "日用品").forEach { label -> FilterChip(selected = filter == label, onClick = { filter = label }, label = { Text(label) }) } }
        Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), horizontalArrangement = Arrangement.SpaceAround) { Stat(store.items.size, "物品种类"); Stat(store.items.count { it.status(store.reminderDays).low }, "库存不足"); Stat(store.items.count { it.status(store.reminderDays).soon }, "即将过期") }
        Row(verticalAlignment = Alignment.CenterVertically) { Text("家庭物品", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f)); TextButton(onClick = voice) { Text("语音") }; TextButton(onClick = add) { Text("＋ 添加") } }
        val result = store.items.filter { it.name.contains(search.trim(), true) && when (filter) { "需关注" -> it.status(store.reminderDays).attention; "食品", "日用品" -> it.category == filter; else -> true } }.sortedBy { it.status(store.reminderDays).priority }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(bottom = 20.dp)) { if (result.isEmpty()) item { Empty("没有匹配的物品", "试试其他关键词，或添加一件新物品") }; items(result, key = { it.id }) { item -> StockRow(item, store.reminderDays) { open(item) } } }
    }
}

@Composable
private fun Stat(number: Int, label: String) { Column(horizontalAlignment = Alignment.CenterHorizontally) { Text(number.toString(), fontSize = 28.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary); Text(label, style = MaterialTheme.typography.labelMedium) } }

@Composable
internal fun StockRow(item: StockItem, days: Int, action: () -> Unit) {
    Card(onClick = action, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(emoji(item), fontSize = 30.sp, modifier = Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(14.dp)).padding(10.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) { Text(item.name, fontWeight = FontWeight.Bold); Text("${item.quantity.display()} ${item.unit} · ${item.location}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            val status = item.status(days)
            Text(status.label, style = MaterialTheme.typography.labelSmall, color = when { status.expired -> Red; status.attention -> Amber; else -> MaterialTheme.colorScheme.primary })
        }
    }
}

@Composable
private fun Shopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    LazyColumn(Modifier.padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(bottom = 24.dp)) {
        item { Text("待采购 · ${store.purchases.size}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
        if (store.purchases.isEmpty()) item { Empty("采购清单还是空的", "看看下方的库存推荐，把补货计划记下来") }
        items(store.purchases, key = { "purchase-${it.itemId}" }) { task -> store.items.firstOrNull { it.id == task.itemId }?.let { item ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("${emoji(item)}  ${item.name}", fontWeight = FontWeight.Bold)
                    Text("待采购 ${task.quantity.display()} ${item.unit}")
                    Row { TextButton(onClick = { action(item.id, "调整采购数量") }) { Text("调整") }; TextButton(onClick = { store.removePlan(item.id); notify("已移出采购清单") }) { Text("移除") }; Button(onClick = { action(item.id, "购买入库") }) { Text("已购买") } }
                }
            }
        } }
        item { Text("根据库存推荐", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp)) }
        val low = store.items.filter { it.status(store.reminderDays).low }
        if (low.isEmpty()) item { Empty("库存充足", "目前没有低于最低库存的物品") }
        items(low, key = { "recommendation-${it.id}" }) { item ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(item.name, fontWeight = FontWeight.Bold)
                    Text("当前 ${item.quantity.display()} ${item.unit} · 最低 ${item.minimum.display()} ${item.unit}\n建议至少补充 ${(item.minimum - item.quantity).display()} ${item.unit}")
                    OutlinedButton(onClick = { action(item.id, if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }) { Text(if (store.purchases.any { it.itemId == item.id }) "已在清单 · 调整" else "加入清单") }
                }
            }
        }
    }
}

@Composable
private fun Profile(store: InventoryStore, open: (String) -> Unit) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Card(onClick = { open("账号设置") }, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.padding(24.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(18.dp)) { Text("☺", fontSize = 46.sp); Column(Modifier.weight(1f)) { Text(store.nickname, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text("本机个人资料 · 编辑资料 ›", style = MaterialTheme.typography.bodySmall) } }
        }
        MenuGroup("家庭与物品管理", listOf("我的家庭" to "家庭空间与存放位置", "库存检测规则" to "最低库存与有效期提醒"), open)
        MenuGroup("账号与个人设置", listOf("账号设置" to "昵称与本机个人资料", "通用设置" to "外观与使用偏好", "消息通知" to "管理 App 内库存提醒", "隐私与安全" to "权限说明与数据管理"), open)
        MenuGroup("支持与关于", listOf("帮助与反馈" to "使用指南与问题反馈", "关于 MagicVVu" to "让家庭物品管理更轻松"), open)
        Text("MAGICVVU  /  A LITTLE MORE HOME", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 20.dp))
    }
}

@Composable
private fun MenuGroup(title: String, rows: List<Pair<String, String>>, open: (String) -> Unit) {
    Text(title, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        rows.forEachIndexed { i, (name, description) ->
            Row(Modifier.fillMaxWidth().clickable { open(name) }.padding(18.dp), verticalAlignment = Alignment.CenterVertically) { Text(listOf("◇", "⚙", "♧", "⊙")[i % 4], fontSize = 22.sp, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(end = 14.dp)); Column(Modifier.weight(1f)) { Text(name, fontWeight = FontWeight.Medium); Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }; Text("›") }
            if (i != rows.lastIndex) HorizontalDivider(Modifier.padding(horizontal = 18.dp))
        }
    }
}

@Composable
internal fun Empty(title: String, subtitle: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 28.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("✧", fontSize = 34.sp, color = MaterialTheme.colorScheme.primary); Text(title, fontWeight = FontWeight.Medium); Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
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
    if (deleting) Confirm("删除${item.name}？", "库存记录、数量历史和对应采购任务将一起删除。", { deleting = false }) { store.deleteItem(item.id); notify("已删除${item.name}"); close() }
}

@Composable
private fun QuantityAction(store: InventoryStore, item: StockItem, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    var quantity by rememberSaveable(item.id, mode) { mutableStateOf(if (mode == "加入采购清单") maxOf(item.minimum - item.quantity, 1.0).display() else if (mode == "调整采购数量") store.purchases.firstOrNull { it.itemId == item.id }?.quantity?.display().orEmpty() else "") }
    var error by remember { mutableStateOf("") }
    Column(Modifier.padding(22.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(item.name, style = MaterialTheme.typography.titleLarge)
        Text("当前库存 ${item.quantity.display()} ${item.unit}")
        Text(if (mode == "购买入库") "已购买？请核对实际购入数量。计划数量不会自动入库。" else if (mode.contains("采购")) "核对计划购买数量，确认后保存至清单。" else "核对本次数量后确认，库存将同步更新。")
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
    var input by rememberSaveable { mutableStateOf("") }
    var confirming by remember { mutableStateOf(false) }
    fun send(text: String) { if (text.isNotBlank()) { conversation.add(text to true); conversation.add(answerInventory(text, store.items, store.reminderDays) to false); input = "" } }
    LaunchedEffect(Unit) { if (initial.isNotBlank()) send(initial); consumed() }
    Column(Modifier.padding(horizontal = 22.dp)) {
        Text("本地库存问答 · 每次提问重新读取当前记录\n历史回答保留当时快照，请追问以获取最新数量。", style = MaterialTheme.typography.bodySmall)
        val scroll = androidx.compose.foundation.lazy.rememberLazyListState()
        LaunchedEffect(conversation.size) { if (conversation.isNotEmpty()) scroll.animateScrollToItem(conversation.lastIndex) }
        LazyColumn(Modifier.weight(1f).padding(vertical = 12.dp), state = scroll, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (conversation.isEmpty()) item { Empty("今天需要我帮你查看什么？", "试试「哪些快过期了」或「需要补什么」") }
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
