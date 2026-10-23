package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.R
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.util.UUID

@Composable
internal fun CloudStatus(store: InventoryStore, onLogin: () -> Unit) {
    val strings = rememberUiStrings()
    val cloud = store.cloud
    val scope = rememberCoroutineScope()
    if (cloud.signedIn) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp)) {
            // The existing assistant cord occupies the trailing edge below the app bar.
            Row(Modifier.fillMaxWidth().padding(end = 84.dp)) {
                Text(strings.get(R.string.ui_household_cloud, if (cloud.lastSync.isBlank()) strings.get(R.string.ui_not_synced) else strings.get(R.string.ui_synced_at, cloud.lastSync)),
                    modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall)
                TextButton(onClick = { scope.launch { runCatching { cloud.refresh() } } }, enabled = !cloud.busy && !cloud.expired) { Text(strings.get(R.string.ui_refresh)) }
            }
            if (cloud.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            cloud.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            if (cloud.expired) TextButton(onClick = onLogin) { Text(strings.get(R.string.ui_log_in_again)) }
        }
    }
}

@Composable
internal fun CloudFamilySetup(store: InventoryStore, onLogin: () -> Unit) {
    val strings = rememberUiStrings()
    val scope = rememberCoroutineScope()
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(strings.get(R.string.ui_welcome, store.nickname), style = MaterialTheme.typography.headlineSmall)
            Text(strings.get(R.string.ui_create_a_household_or_join_one))
            CloudStatus(store, onLogin)
            CloudFamilyPanel(store) {}
            TextButton(onClick = { scope.launch { store.cloud.logout(); onLogin() } }) { Text(strings.get(R.string.ui_log_out)) }
        }
    }
}

@Composable
internal fun CloudFamilyPanel(store: InventoryStore, notify: (String) -> Unit) {
    val strings = rememberUiStrings()
    val cloud = store.cloud
    val scope = rememberCoroutineScope()
    var newName by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var rename by rememberSaveable(cloud.account?.householdId, cloud.household?.name) { mutableStateOf(cloud.household?.name.orEmpty()) }
    var invitation by remember { mutableStateOf("") }
    var members by remember { mutableStateOf<List<String>>(emptyList()) }
    var error by remember { mutableStateOf("") }
    fun execute(message: String = "已保存", block: suspend () -> Unit) {
        scope.launch { runCatching { block() }.onSuccess { error = ""; notify(strings.label(message)) }.onFailure { error = it.message ?: "操作失败" } }
    }
    LaunchedEffect(cloud.scopeKey) { runCatching { cloud.members() }.onSuccess { members = it } }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(strings.get(R.string.ui_my_household), fontWeight = FontWeight.Bold)
        cloud.households.forEach { home ->
            OutlinedButton(enabled = !cloud.busy && !cloud.expired, onClick = { execute("已切换家庭") { cloud.selectHousehold(home.id) } }, modifier = Modifier.fillMaxWidth().testTag("family-${home.id}")) {
                Text("${if (home.id == cloud.account?.householdId) "✓ " else ""}${home.name} · ${home.role}")
            }
        }
        if (cloud.household != null) {
            Field(strings.get(R.string.ui_current_household_name), rename, { rename = it })
            Button(enabled = !cloud.busy && rename.isNotBlank() && cloud.household?.role in listOf("owner", "admin"),
                onClick = { execute("家庭名称已更新") { cloud.profile(store.nickname, rename) } }) { Text(strings.get(R.string.ui_save_household_name)) }
            Text(strings.get(R.string.ui_household_members), fontWeight = FontWeight.Bold)
            members.forEach { Text(it) }
            OutlinedButton(enabled = !cloud.busy && cloud.household?.role in listOf("owner", "admin"),
                onClick = { execute("邀请码已生成，30 分钟内有效，仅能使用一次") { invitation = cloud.invitation() } }) { Text(strings.get(R.string.ui_create_member_invite)) }
            if (invitation.isNotBlank()) androidx.compose.foundation.text.selection.SelectionContainer {
                Text(strings.get(R.string.ui_invite_code__valid_for_30_minutes, invitation))
            }
        }
        HorizontalDivider()
        Field(strings.get(R.string.ui_new_household_name), newName, { newName = it })
        Button(enabled = !cloud.busy && !cloud.expired && newName.isNotBlank(),
            onClick = { execute("家庭已创建") { cloud.createHousehold(newName); newName = "" } }) { Text(strings.get(R.string.ui_create_household)) }
        Field(strings.get(R.string.ui_household_invite_code), code, { code = it })
        OutlinedButton(enabled = !cloud.busy && !cloud.expired && code.isNotBlank(),
            onClick = { execute("已加入家庭") { cloud.joinHousehold(code); code = "" } }) { Text(strings.get(R.string.ui_join_household)) }
        MotionErrorText(error)
        Text(strings.get(R.string.ui_switching_households_shows_only_that_household_s), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
internal fun CloudShopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    val strings = rememberUiStrings()
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
                FilterChip(!history, { history = false }, label = { Text(strings.get(R.string.ui_to_buy)) })
                FilterChip(history, { history = true }, label = { Text(strings.get(R.string.ui_purchase_history)) })
                TextButton(onClick = { adding = true }, enabled = !cloud.busy && !cloud.expired) { Text(strings.get(R.string.ui_add_purchase)) }
            }
            Text(strings.get(R.string.ui_shared_shopping_list___item_s, entries.size), fontWeight = FontWeight.Bold)
            Text(strings.get(R.string.ui_each_purchase_creates_a_separate_inventory), style = MaterialTheme.typography.bodySmall)
        }
        if (entries.isEmpty()) item { Empty(if (history) strings.get(R.string.ui_no_purchase_history_yet) else strings.get(R.string.ui_your_shopping_list_is_empty), strings.get(R.string.ui_add_a_purchase_here_or_from)) }
        items(entries, key = { it.id }) { entry ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(entry.name, style = MaterialTheme.typography.titleMedium)
                    Text("${entry.quantity.display()} ${entry.unit}")
                    Text(if (entry.purchased) strings.get(R.string.ui_recorded_the_purchase, if (entry.purchasedBy == cloud.account?.userId) strings.get(R.string.ui_me_actor) else strings.get(R.string.ui_household_member)) else strings.get(R.string.ui_added_by, if (entry.addedBy == cloud.account?.userId) strings.get(R.string.ui_me_actor) else strings.get(R.string.ui_household_member)), style = MaterialTheme.typography.bodySmall)
                    if (!entry.purchased) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Button(enabled = !cloud.busy && !cloud.expired, onClick = { purchasing = entry }) { Text(strings.get(R.string.ui_receive)) }
                        TextButton(enabled = !cloud.busy, onClick = { editing = entry }) { Text(strings.get(R.string.ui_adjust)) }
                        TextButton(enabled = !cloud.busy, onClick = { removing = entry }) { Text(strings.get(R.string.ui_remove)) }
                    }
                }
            }
        }
        if (!history) {
            item { Text(strings.get(R.string.ui_restock), fontWeight = FontWeight.Bold) }
            items(store.items.filter { it.status(store.reminderDays).low }, key = { "recommend-${it.id}" }) { item ->
                OutlinedButton(onClick = { action(item.id, "加入采购清单") }, enabled = !cloud.busy) {
                    Text(strings.get(R.string.ui___suggested_restock, item.name, (item.minimum - item.quantity).display(), item.unit))
                }
            }
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
    if (adding || editing != null) {
        CloudShoppingEditor(store, editing, notify) { adding = false; editing = null }
    }
    purchasing?.let { entry -> CloudPurchaseDialog(store, entry, notify) { purchasing = null } }
    removing?.let { entry -> Confirm(strings.get(R.string.ui_remove_2, entry.name), strings.get(R.string.ui_only_this_shopping_entry_will_be), { removing = null }) {
        scope.launch { runCatching { cloud.removeShopping(entry.id) }.onSuccess { removing = null; notify(strings.get(R.string.ui_removed)) }.onFailure { notify(it.message ?: strings.get(R.string.ui_could_not_remove)) } }
    } }
}

@Composable
private fun CloudShoppingEditor(store: InventoryStore, item: CloudShoppingItem?, notify: (String) -> Unit, close: () -> Unit) {
    val strings = rememberUiStrings()
    val id = rememberSaveable { item?.id ?: UUID.randomUUID().toString() }
    var name by rememberSaveable { mutableStateOf(item?.name.orEmpty()) }
    var quantity by rememberSaveable { mutableStateOf(item?.quantity?.display() ?: "1") }
    var unit by rememberSaveable { mutableStateOf(item?.unit ?: "件") }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    AlertDialog(onDismissRequest = { if (!store.cloud.busy) close() }, title = { Text(if (item == null) strings.get(R.string.ui_add_purchase) else strings.get(R.string.ui_edit_purchase)) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Field(strings.get(R.string.ui_item_name_2), name, { name = it }); Field(strings.get(R.string.ui_planned_quantity), quantity, { quantity = it }, numeric = true); Field(strings.get(R.string.ui_unit), unit, { unit = it }); MotionErrorText(error)
        } }, dismissButton = { TextButton(onClick = close, enabled = !store.cloud.busy) { Text(strings.get(R.string.ui_cancel)) } },
        confirmButton = { TextButton(enabled = !store.cloud.busy, onClick = {
            val amount = positiveNumber(quantity)
            if (name.isBlank() || unit.isBlank() || amount == null) error = "请填写名称、正数数量和单位"
            else scope.launch { runCatching { store.cloud.saveShopping(id, name, amount, unit, item == null) }
                .onSuccess { notify(strings.get(R.string.ui_shopping_list_saved)); close() }.onFailure { error = it.message ?: "保存失败" } }
        }) { Text(strings.get(R.string.ui_save)) } })
}

@Composable
private fun CloudPurchaseDialog(store: InventoryStore, item: CloudShoppingItem, notify: (String) -> Unit, close: () -> Unit) {
    val strings = rememberUiStrings()
    var quantity by rememberSaveable { mutableStateOf(item.quantity.display()) }
    var location by rememberSaveable { mutableStateOf(store.items.firstOrNull { it.id == item.sourceId }?.location.orEmpty()) }
    var expiry by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    AlertDialog(onDismissRequest = { if (!store.cloud.busy) close() }, title = { Text(strings.get(R.string.ui_record_purchase_of, item.name)) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(strings.get(R.string.ui_check_the_amount_actually_bought__confirmation))
            Field(strings.get(R.string.ui_actual_quantity, item.unit), quantity, { quantity = it }, numeric = true)
            Field(strings.get(R.string.ui_location__optional), location, { location = it }); Field(strings.get(R.string.ui_expiry_yyyy_mm_dd__optional), expiry, { expiry = it }); MotionErrorText(error)
        } }, dismissButton = { TextButton(onClick = close, enabled = !store.cloud.busy) { Text(strings.get(R.string.ui_cancel)) } },
        confirmButton = { TextButton(enabled = !store.cloud.busy, onClick = {
            val amount = positiveNumber(quantity)
            if (amount == null) error = "请输入有效正数"
            else if (expiry.isNotBlank() && runCatching { LocalDate.parse(expiry.trim()) }.isFailure) error = "请输入有效日期"
            else scope.launch { runCatching { store.cloud.purchase(item.id, amount, location, expiry) }
                .onSuccess { notify(strings.get(R.string.ui_purchase_recorded_and_inventory_synced)); close() }.onFailure { error = it.message ?: "入库失败" } }
        }) { Text(strings.get(R.string.ui_confirm_purchase_and_receive)) } })
}
