package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.util.UUID

@Composable
internal fun CloudStatus(store: InventoryStore, onLogin: () -> Unit) {
    val cloud = store.cloud
    val scope = rememberCoroutineScope()
    if (cloud.signedIn) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp)) {
            // The existing assistant cord occupies the trailing edge below the app bar.
            Row(Modifier.fillMaxWidth().padding(end = 84.dp)) {
                Text("家庭云端 · ${if (cloud.lastSync.isBlank()) "尚未同步" else "同步于 ${cloud.lastSync}"}",
                    modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall)
                TextButton(onClick = { scope.launch { runCatching { cloud.refresh() } } }, enabled = !cloud.busy && !cloud.expired) { Text("刷新") }
            }
            if (cloud.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            cloud.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            if (cloud.expired) TextButton(onClick = onLogin) { Text("重新登录") }
        }
    }
}

@Composable
internal fun CloudFamilySetup(store: InventoryStore, onLogin: () -> Unit) {
    val scope = rememberCoroutineScope()
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("欢迎，${store.nickname}", style = MaterialTheme.typography.headlineSmall)
            Text("创建一个家庭，或通过邀请码加入已有家庭。游客的本机记录仍独立保留。")
            CloudStatus(store, onLogin)
            CloudFamilyPanel(store) {}
            TextButton(onClick = { scope.launch { store.cloud.logout(); onLogin() } }) { Text("退出账号") }
        }
    }
}

@Composable
internal fun CloudFamilyPanel(store: InventoryStore, notify: (String) -> Unit) {
    val cloud = store.cloud
    val scope = rememberCoroutineScope()
    var newName by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var rename by rememberSaveable(cloud.account?.householdId, cloud.household?.name) { mutableStateOf(cloud.household?.name.orEmpty()) }
    var invitation by remember { mutableStateOf("") }
    var members by remember { mutableStateOf<List<String>>(emptyList()) }
    var error by remember { mutableStateOf("") }
    fun execute(message: String = "已保存", block: suspend () -> Unit) {
        scope.launch { runCatching { block() }.onSuccess { error = ""; notify(message) }.onFailure { error = it.message ?: "操作失败" } }
    }
    LaunchedEffect(cloud.scopeKey) { runCatching { cloud.members() }.onSuccess { members = it } }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("我的家庭", fontWeight = FontWeight.Bold)
        cloud.households.forEach { home ->
            OutlinedButton(enabled = !cloud.busy && !cloud.expired, onClick = { execute("已切换家庭") { cloud.selectHousehold(home.id) } }, modifier = Modifier.fillMaxWidth()) {
                Text("${if (home.id == cloud.account?.householdId) "✓ " else ""}${home.name} · ${home.role}")
            }
        }
        if (cloud.household != null) {
            Field("当前家庭名称", rename, { rename = it })
            Button(enabled = !cloud.busy && rename.isNotBlank() && cloud.household?.role in listOf("owner", "admin"),
                onClick = { execute("家庭名称已更新") { cloud.profile(store.nickname, rename) } }) { Text("保存家庭名称") }
            Text("家庭成员", fontWeight = FontWeight.Bold)
            members.forEach { Text(it) }
            OutlinedButton(enabled = !cloud.busy && cloud.household?.role in listOf("owner", "admin"),
                onClick = { execute("邀请码已生成，30 分钟内有效，仅能使用一次") { invitation = cloud.invitation() } }) { Text("生成成员邀请码") }
            if (invitation.isNotBlank()) androidx.compose.foundation.text.selection.SelectionContainer {
                Text("邀请码（30 分钟内有效，仅能使用一次，请私下分享）：\n$invitation")
            }
        }
        HorizontalDivider()
        Field("新家庭名称", newName, { newName = it })
        Button(enabled = !cloud.busy && !cloud.expired && newName.isNotBlank(),
            onClick = { execute("家庭已创建") { cloud.createHousehold(newName); newName = "" } }) { Text("创建家庭") }
        Field("家庭邀请码", code, { code = it })
        OutlinedButton(enabled = !cloud.busy && !cloud.expired && code.isNotBlank(),
            onClick = { execute("已加入家庭") { cloud.joinHousehold(code); code = "" } }) { Text("加入家庭") }
        MotionErrorText(error)
        Text("切换家庭后仅展示该家庭的库存与清单；其他成员的修改可通过刷新获取。", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
internal fun CloudShopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    val cloud = store.cloud
    val scope = rememberCoroutineScope()
    var history by rememberSaveable { mutableStateOf(false) }
    var editing by remember { mutableStateOf<CloudShoppingItem?>(null) }
    var adding by remember { mutableStateOf(false) }
    var purchasing by remember { mutableStateOf<CloudShoppingItem?>(null) }
    var removing by remember { mutableStateOf<CloudShoppingItem?>(null) }
    val entries = cloud.shopping.filter { it.purchased == history }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(!history, { history = false }, label = { Text("待购买") })
                FilterChip(history, { history = true }, label = { Text("已购历史") })
                TextButton(onClick = { adding = true }, enabled = !cloud.busy && !cloud.expired) { Text("添加采购") }
            }
            Text("家庭共享清单 · ${entries.size} 项", fontWeight = FontWeight.Bold)
            Text("购买后生成独立库存批次，已购记录保留。", style = MaterialTheme.typography.bodySmall)
        }
        if (entries.isEmpty()) item { Empty(if (history) "暂无购买历史" else "清单里还没有待购物品", "可以直接添加采购，或从库存详情加入清单") }
        items(entries, key = { it.id }) { entry ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(entry.name, style = MaterialTheme.typography.titleMedium)
                    Text("${entry.quantity.display()} ${entry.unit}")
                    Text(if (entry.purchased) "${if (entry.purchasedBy == cloud.account?.userId) "我" else "家庭成员"}已购买入库" else "${if (entry.addedBy == cloud.account?.userId) "我" else "家庭成员"}添加", style = MaterialTheme.typography.bodySmall)
                    if (!entry.purchased) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Button(enabled = !cloud.busy && !cloud.expired, onClick = { purchasing = entry }) { Text("已购买") }
                        TextButton(enabled = !cloud.busy, onClick = { editing = entry }) { Text("调整") }
                        TextButton(enabled = !cloud.busy, onClick = { removing = entry }) { Text("移除") }
                    }
                }
            }
        }
        if (!history) {
            item { Text("补货建议", fontWeight = FontWeight.Bold) }
            items(store.items.filter { it.status(store.reminderDays).low }, key = { "recommend-${it.id}" }) { item ->
                OutlinedButton(onClick = { action(item.id, "加入采购清单") }, enabled = !cloud.busy) {
                    Text("${item.name} · 建议补 ${(item.minimum - item.quantity).display()} ${item.unit}")
                }
            }
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
    if (adding || editing != null) {
        CloudShoppingEditor(store, editing, notify) { adding = false; editing = null }
    }
    purchasing?.let { entry -> CloudPurchaseDialog(store, entry, notify) { purchasing = null } }
    removing?.let { entry -> Confirm("移除${entry.name}？", "仅移除这条待购记录，已有库存保持原样。", { removing = null }) {
        scope.launch { runCatching { cloud.removeShopping(entry.id) }.onSuccess { removing = null; notify("已移除") }.onFailure { notify(it.message ?: "移除失败") } }
    } }
}

@Composable
private fun CloudShoppingEditor(store: InventoryStore, item: CloudShoppingItem?, notify: (String) -> Unit, close: () -> Unit) {
    val id = rememberSaveable { item?.id ?: UUID.randomUUID().toString() }
    var name by rememberSaveable { mutableStateOf(item?.name.orEmpty()) }
    var quantity by rememberSaveable { mutableStateOf(item?.quantity?.display() ?: "1") }
    var unit by rememberSaveable { mutableStateOf(item?.unit ?: "件") }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    AlertDialog(onDismissRequest = { if (!store.cloud.busy) close() }, title = { Text(if (item == null) "添加采购" else "调整采购") },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Field("物品名称", name, { name = it }); Field("计划数量", quantity, { quantity = it }, numeric = true); Field("单位", unit, { unit = it }); MotionErrorText(error)
        } }, dismissButton = { TextButton(onClick = close, enabled = !store.cloud.busy) { Text("取消") } },
        confirmButton = { TextButton(enabled = !store.cloud.busy, onClick = {
            val amount = positiveNumber(quantity)
            if (name.isBlank() || unit.isBlank() || amount == null) error = "请填写名称、正数数量和单位"
            else scope.launch { runCatching { store.cloud.saveShopping(id, name, amount, unit, item == null) }
                .onSuccess { notify("采购清单已保存"); close() }.onFailure { error = it.message ?: "保存失败" } }
        }) { Text("确认保存") } })
}

@Composable
private fun CloudPurchaseDialog(store: InventoryStore, item: CloudShoppingItem, notify: (String) -> Unit, close: () -> Unit) {
    var quantity by rememberSaveable { mutableStateOf(item.quantity.display()) }
    var location by rememberSaveable { mutableStateOf(store.items.firstOrNull { it.id == item.sourceId }?.location.orEmpty()) }
    var expiry by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    AlertDialog(onDismissRequest = { if (!store.cloud.busy) close() }, title = { Text("购买${item.name}并入库") },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("核对实际购买数量，确认后创建独立批次。")
            Field("实际数量（${item.unit}）", quantity, { quantity = it }, numeric = true)
            Field("存放位置（选填）", location, { location = it }); Field("有效期 YYYY-MM-DD（选填）", expiry, { expiry = it }); MotionErrorText(error)
        } }, dismissButton = { TextButton(onClick = close, enabled = !store.cloud.busy) { Text("取消") } },
        confirmButton = { TextButton(enabled = !store.cloud.busy, onClick = {
            val amount = positiveNumber(quantity)
            if (amount == null) error = "请输入有效正数"
            else if (expiry.isNotBlank() && runCatching { LocalDate.parse(expiry.trim()) }.isFailure) error = "请输入有效日期"
            else scope.launch { runCatching { store.cloud.purchase(item.id, amount, location, expiry) }
                .onSuccess { notify("购买已记录，库存已同步"); close() }.onFailure { error = it.message ?: "入库失败" } }
        }) { Text("确认购买并入库") } })
}
