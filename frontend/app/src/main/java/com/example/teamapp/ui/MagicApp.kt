package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.example.teamapp.data.*
import com.example.teamapp.R
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.theme.appearanceFade
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.ring.RingInventoryPage
import com.example.teamapp.ui.ring.InventoryDetailContent
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal val Red: Color
    @Composable get() = if (LocalLightDesign.current) Color(0xFFB44848) else MaterialTheme.colorScheme.error
internal fun emoji(item: StockItem) = when { item.name.contains("奶") -> "🥛"; item.name.contains("蛋") -> "🥚"; item.name.contains("苹果") -> "🍎"; item.name.contains("面包") -> "🍞"; item.category == "日用品" -> "🧴"; else -> "🥬" }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MagicApp(store: InventoryStore, onOpenAuth: () -> Unit = {}) {
    AppLanguageProvider(store.language) { MagicAppContent(store, onOpenAuth) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MagicAppContent(store: InventoryStore, onOpenAuth: () -> Unit) {
    val strings = rememberUiStrings()
    val lightDesign = LocalLightDesign.current
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var panel by rememberSaveable { mutableStateOf<String?>(null) }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var inventoryDetailVisible by remember { mutableStateOf(false) }
    var initialQuestion by rememberSaveable { mutableStateOf("") }
    val conversation = rememberSaveable(store.cloud.scopeKey, saver = listSaver<androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, String>(
        save = { messages -> messages.flatMap { listOf(it.first, if (it.second) "user" else "assistant") } },
        restore = { saved -> mutableStateListOf<Pair<String, Boolean>>().apply { saved.chunked(2).forEach { add(it[0] to (it[1] == "user")) } } }
    )) { mutableStateListOf<Pair<String, Boolean>>() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val pageStates = rememberSaveableStateHolder()
    LaunchedEffect(store.cloud.scopeKey) {
        panel = null; selected = null
        store.cloud.assistant.bind(); store.cloud.planningFacts.bind()
    }
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
    val notify: (String) -> Unit = { message -> scope.launch { snackbar.showSnackbar(strings.label(if (store.cloud.signedIn) message else store.storageError ?: message)) } }
    val openItem: (StockItem) -> Unit = { selected = it.id; panel = "详情" }
    val item = store.items.firstOrNull { it.id == selected }
    // A deleted item's sheet keeps its last frame while sliding off screen.
    var retainedItem by remember(selected) { mutableStateOf(item) }
    SideEffect { if (item != null) retainedItem = item }
    val sheetItem = item ?: retainedItem
    val pageTravel = with(LocalDensity.current) { 28.dp.roundToPx() }
    BackHandler(panel != null) { closePanel() }
    AssistantPullLayer(tab, panel == null && !inventoryDetailVisible, store, conversation, snackbar, notify) { headerModifier ->
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
                    Button(onClick = { panel = "隐私与安全" }, modifier = Modifier.padding(horizontal = 22.dp)) { Text(strings.get(R.string.ui_export___manage_data)) }
                } else HouseholdPullRefresh(
                    enabled = store.cloud.signedIn && !store.cloud.expired && panel == null && !inventoryDetailVisible,
                    busy = store.cloud.busy,
                    onRefresh = { store.cloud.refresh() },
                    modifier = Modifier.weight(1f).fillMaxWidth()
                ) {
                    AnimatedContent(tab, Modifier.fillMaxSize(), transitionSpec = {
                        val direction = if (targetState > initialState) 1 else -1
                        (fadeIn(tween(AppMotion.Duration)) + slideInHorizontally(tween(AppMotion.Page, easing = AppMotion.easing)) { direction * pageTravel })
                            .togetherWith(fadeOut(tween(AppMotion.Quick)) + slideOutHorizontally(tween(AppMotion.Duration, easing = AppMotion.easing)) { -direction * pageTravel / 2 })
                            .using(null)
                    }, label = "main-page") { page ->
                        pageStates.SaveableStateProvider(page) {
                            Box(Modifier.fillMaxSize().motionInput(page == tab)) {
                                when (page) {
                                    0 -> Home(store, openItem, { selectTab(1) }, { panel = it }, { initialQuestion = it; panel = "AI 智能管家" })
                                    1 -> RingInventoryPage(store, { stockItem, route -> selected = stockItem.id; panel = route },
                                        { panel = "手动添加" }, notify, active = page == tab,
                                        onDetailVisibilityChanged = { inventoryDetailVisible = it })
                                    2 -> Shopping(store, { id, p -> selected = id; panel = p }, notify)
                                    3 -> Profile(store) { if (it == "登录 / 注册") onOpenAuth() else panel = it }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (panel == "拍照添加") {
        Dialog(onDismissRequest = { panel = null }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                Box(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
                    PhotoScanFlow(store, notify, close = { panel = null })
                }
            }
        }
    }
    if (panel != null && panel != "拍照添加") {
        ModalBottomSheet(onDismissRequest = { panel = null }, sheetState = sheetState, modifier = Modifier.appearanceFade(),
            containerColor = if (lightDesign) BottomSheetDefaults.ContainerColor else MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface) {
            Column(Modifier.fillMaxWidth().fillMaxHeight(0.92f).imePadding().motionInput(!closingPanel)) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    AppMotionContent(panel.orEmpty(), Modifier.weight(1f), label = "panel-title") { title ->
                        Text(when (title) {
                            "AI 智能管家" -> strings.get(R.string.brand_assistant_title)
                            "库存检测规则" -> strings.get(R.string.ui_stock_rules)
                            else -> strings.label(title)
                        },
                            style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    }
                    TextButton(onClick = { closePanel() }) { Text(strings.get(R.string.ui_close_2)) }
                }
                if (!lightDesign) HorizontalDivider(color = DarkLine, modifier = Modifier.padding(top = 10.dp))
                AppMotionContent(panel.orEmpty(), Modifier.weight(1f).fillMaxWidth(), label = "panel-content") { route ->
                    when (route) {
                        "AI 智能管家" -> Chat(store, conversation, initialQuestion, { initialQuestion = "" }, notify)
                        "拍照添加", "语音添加", "手动添加" -> AddFlow(store, route, notify) { closePanel() }
                        "编辑物品" -> sheetItem?.let { Editor(store, it, notify = notify, onSaved = { focus.clearFocus(); panel = "详情" }) }
                        "详情" -> sheetItem?.let { Detail(store, it, { panel = it }, notify, close = { closePanel() }) }
                        "资料与盘点" -> sheetItem?.let { PlanningFactsPanel(store.cloud, it, adjust = { panel = "盘点修正" }) }
                        "消费流水" -> ConsumptionEventsPanel(store.cloud, sheetItem?.id.orEmpty())
                        "批次操作" -> sheetItem?.let { BatchOperationsPanel(store.cloud, it, "ASK") }
                        "关注概览" -> CloudAssistant(store.cloud, "今天需要关注什么，分别展示风险和规划资料", showIntro = false)
                        "盘点修正" -> sheetItem?.let { QuantityAction(store, it, route, notify) { closePanel() } }
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
    val strings = rememberUiStrings()
    Column(Modifier.fillMaxSize()) {
        if (store.cloud.signedIn) Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(strings.tr("登记日期与阈值提醒", "Recorded dates & stock thresholds"), modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelMedium)
            TextButton(onClick = { panel("关注概览") }) { Text(strings.tr("AI 关注概览", "AI overview")) }
        }
        Box(Modifier.weight(1f)) {
            if (LocalLightDesign.current) DesignHome(store, open, all, panel, ask)
            else DarkHome(store, open, all, panel, ask)
        }
    }
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
    val strings = rememberUiStrings()
    val rows = store.items.filter { val s = it.status(store.reminderDays); (s.low && store.notifications[0]) || (s.soon && store.notifications[1]) || (s.expired && store.notifications[2]) }.sortedBy { it.status(store.reminderDays).priority }
    LazyColumn(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text(strings.get(R.string.ui_in_app_alerts___these_switches_do), style = MaterialTheme.typography.bodySmall) }
        if (rows.isEmpty()) item { Empty(strings.get(R.string.ui_no_alerts_need_attention), strings.get(R.string.ui_manage_alert_types_in_me)) }
        items(rows, key = { it.id }) { item -> Column(Modifier.animateItem()) { StockRow(item, store.reminderDays) { open(item) }; Text(reasons(item, store.reminderDays, strings = strings), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(8.dp)) } }
    }
}

internal fun reasons(item: StockItem, days: Int, concise: Boolean = false, strings: com.example.teamapp.ui.i18n.UiStrings): String {
    val s = item.status(days)
    val duration = s.days?.let { if (strings.english) strings.days(kotlin.math.abs(it)) else kotlin.math.abs(it) }
    return buildList {
        if (s.low) add(if (concise) strings.get(R.string.ui_short_by, (item.minimum - item.quantity).display(), item.unit) else strings.get(R.string.ui_left__below_the_minimum_of, item.quantity.display(), item.unit, item.minimum.display(), item.unit))
        if (s.expired) add(if (concise) strings.get(R.string.ui_expired_day_s__ago__please_check, duration) else strings.get(R.string.ui_expired_on___day_s__ago__please, item.expiry, duration))
        if (s.soon) add(if (concise) strings.get(R.string.ui_expires_in_day_s, duration) else strings.get(R.string.ui_expires_on___in_day_s, item.expiry, duration))
        if (!s.attention) add(strings.get(R.string.ui_stock_status_is_normal))
        if (item.expiry.isBlank()) add(strings.get(R.string.ui_no_expiry_date_set))
    }.joinToString(if (concise) if (strings.english) "; " else "；" else "\n")
}

@Composable
internal fun Detail(store: InventoryStore, item: StockItem, open: (String) -> Unit, notify: (String) -> Unit, close: () -> Unit,
    reveal: (Int) -> Modifier = { Modifier }) {
    val strings = rememberUiStrings()
    var deleting by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val operationId = rememberSaveable(item.id) { java.util.UUID.randomUUID().toString() }
    InventoryDetailContent(store, item, open, { deleting = true }, reveal)
    if (deleting) Confirm(strings.get(R.string.ui_delete, item.name), if (store.cloud.signedIn) strings.get(R.string.ui_remove_this_batch_from_inventory__the) else strings.get(R.string.ui_the_stock_record__quantity_history_and), { deleting = false }) {
        scope.launch { runCatching { store.deleteItemSynced(item, operationId) }.onSuccess { notify(strings.get(R.string.ui_deleted, item.name)); close() }.onFailure { notify(it.message ?: strings.get(R.string.ui_could_not_delete)) }; deleting = false }
    }
}

@Composable
private fun QuantityAction(store: InventoryStore, item: StockItem, mode: String, notify: (String) -> Unit, close: () -> Unit) {
    val strings = rememberUiStrings()
    if (store.cloud.signedIn && mode == "消耗库存") {
        BatchOperationsPanel(store.cloud, item, "CONSUME")
        return
    }
    val scope = rememberCoroutineScope()
    val operationId = rememberSaveable(item.id, mode) { java.util.UUID.randomUUID().toString() }
    var submitting by remember { mutableStateOf(false) }
    var quantity by rememberSaveable(item.id, mode) { mutableStateOf(if (mode == "加入采购清单") maxOf(item.minimum - item.quantity, 1.0).display() else if (mode == "调整采购数量") store.purchases.firstOrNull { it.itemId == item.id }?.quantity?.display().orEmpty() else if (item.individualRecord && mode == "消耗库存") "1" else "") }
    var error by remember { mutableStateOf("") }
    Column(Modifier.padding(22.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(item.name, style = MaterialTheme.typography.titleLarge)
        Text(strings.get(R.string.ui_current_stock, item.quantity.display(), item.unit))
        ModeNotice(if (mode == "购买入库") strings.get(R.string.ui_bought_this_item__check_the_quantity) else if (mode.contains("采购")) strings.get(R.string.ui_check_the_planned_quantity_before_saving) else strings.get(R.string.ui_check_this_quantity_before_confirming_the))
        if (item.individualRecord && mode == "消耗库存") Text(strings.tr("本次只消耗所选的这一件物品。", "Use the selected item."))
        else OutlinedTextField(quantity, { quantity = it; error = "" }, label = { Text(strings.get(R.string.ui_quantity_3, if (mode == "购买入库") strings.get(R.string.ui_actual_purchase) else strings.get(R.string.ui_this_change), item.unit)) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), isError = error.isNotBlank(), supportingText = { MotionErrorText(error) }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            val amount = if (mode == "盘点修正") nonNegativeNumber(quantity) else positiveNumber(quantity)
            if (amount == null) error = "请输入有效正数" else if (!submitting) scope.launch {
                submitting = true
                try {
                    when (mode) {
                        "购买入库" -> store.receive(item.id, amount)
                        "增加库存" -> store.changeQuantitySynced(item, amount, operationId)
                        "消耗库存" -> store.changeQuantitySynced(item, -amount, operationId)
                        "盘点修正" -> store.changeQuantitySynced(item, java.math.BigDecimal.valueOf(amount).subtract(item.quantityText.toBigDecimal()).toDouble(), operationId)
                        else -> store.planSynced(item, amount, operationId)
                    }
                    notify(if (mode == "盘点修正") strings.tr("盘点修正已保存，未计为消费", "Stock correction saved; not counted as consumption") else if (mode == "购买入库" || mode == "增加库存") strings.get(R.string.ui_added_to, item.name, amount.display(), item.unit) else if (mode == "消耗库存") strings.get(R.string.ui_recorded_use_of, amount.display(), item.unit) else strings.get(R.string.ui_shopping_plan_saved)); close()
                } catch (failure: Exception) { error = failure.message ?: "保存失败" }
                finally { submitting = false }
            }
        }, enabled = !submitting && !store.cloud.busy && !store.cloud.expired, modifier = Modifier.fillMaxWidth()) { Text(if (submitting) strings.get(R.string.ui_saving) else if (mode == "购买入库") strings.get(R.string.ui_confirm_receipt) else strings.get(R.string.ui_save)) }
    }
}

@Composable
internal fun Chat(store: InventoryStore, conversation: androidx.compose.runtime.snapshots.SnapshotStateList<Pair<String, Boolean>>, initial: String, consumed: () -> Unit, notify: (String) -> Unit, showIntro: Boolean = true) {
    val strings = rememberUiStrings()
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
        if (strings.english) Text(strings.get(R.string.ui_ai_language_note), style = MaterialTheme.typography.bodySmall)
        if (store.cloud.signedIn) Text(strings.get(R.string.ui_household_inventory_q_a___review_and), style = MaterialTheme.typography.bodySmall)
        else if (!showIntro) Text(strings.get(R.string.ui_based_on_local_stock___restocking), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        else if (LocalLightDesign.current) Text(strings.get(R.string.ui_local_stock_q_a___each_question), style = MaterialTheme.typography.bodySmall)
        else DarkNotice(strings.get(R.string.ui_local_stock_q_a___each_question))
        val scroll = androidx.compose.foundation.lazy.rememberLazyListState()
        LaunchedEffect(conversation.size) { if (conversation.isNotEmpty()) scroll.animateScrollToItem(conversation.lastIndex) }
        LazyColumn(Modifier.weight(1f).padding(vertical = 8.dp), state = scroll, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (conversation.isEmpty()) item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().padding(12.dp)) {
                        Text(strings.get(R.string.ui_what_would_you_like_to_check), fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 24.sp)
                    }
                }
            }
            if (showIntro && conversation.isEmpty() && !lightDesign) item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuggestionChip(onClick = { send("哪些快过期了？") }, label = { Text(strings.get(R.string.ui_expiring_soon), fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                    SuggestionChip(onClick = { send("需要补什么？") }, label = { Text(strings.get(R.string.ui_restock), fontSize = 12.sp) }, shape = androidx.compose.foundation.shape.CircleShape)
                }
            }
            itemsIndexed(conversation.toList(), key = { index, _ -> "message-$index" }) { _, (message, user) -> Card(colors = CardDefaults.cardColors(containerColor = if (user) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant), modifier = Modifier.animateItem().fillMaxWidth().padding(start = if (user) 32.dp else 0.dp, end = if (user) 0.dp else 18.dp)) { Column(Modifier.padding(14.dp)) { Text(if (user) strings.get(R.string.ui_you) else "✦ Mew", style = MaterialTheme.typography.labelSmall); Text(message) } } }
        }
        TextButton(onClick = { confirming = true }, enabled = store.items.any { it.status(store.reminderDays).low }) { Text(strings.get(R.string.ui_review_restock)) }
        Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(input, { input = it }, placeholder = { Text(strings.get(R.string.ui_enter_a_question)) }, modifier = Modifier.weight(1f)); TextButton(onClick = { send(input) }, enabled = !asking) { Text(if (asking) strings.get(R.string.ui_checking) else strings.get(R.string.ui_send)) } }
        Spacer(Modifier.height(16.dp))
    }
    if (confirming) {
        val low = store.items.filter { it.status(store.reminderDays).low && store.purchases.none { p -> p.itemId == it.id } }
        Confirm(strings.get(R.string.ui_confirm_restock_suggestions), if (low.isEmpty()) strings.get(R.string.ui_these_items_are_already_on_the) else low.joinToString("\n") { "${it.name}：${(it.minimum - it.quantity).display()} ${it.unit}" }, { confirming = false }) {
            scope.launch { runCatching { low.forEach { store.planSynced(it, it.minimum - it.quantity, java.util.UUID.randomUUID().toString()) } }
                .onSuccess { notify(if (low.isEmpty()) strings.get(R.string.ui_shopping_entries_already_exist) else strings.get(R.string.ui_added_to_shopping_list)) }.onFailure { notify(it.message ?: strings.get(R.string.ui_some_actions_may_have_been_saved)) }; confirming = false }
        }
    }
}

@Composable
internal fun Confirm(title: String, body: String, cancel: () -> Unit, confirm: () -> Unit) {
    val strings = rememberUiStrings()
    AlertDialog(onDismissRequest = cancel, modifier = Modifier.appearanceFade(), title = { Text(title) }, text = { Text(body) }, dismissButton = { TextButton(onClick = cancel) { Text(strings.get(R.string.ui_cancel)) } }, confirmButton = { TextButton(onClick = confirm) { Text(strings.get(R.string.ui_confirm_2)) } })
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
