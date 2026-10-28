package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.i18n.LanguageSettings

// Exact colors from the supplied dark_ui images; the light design uses its own palette.
internal val DarkPaper = Color(0xFF18191B)
internal val DarkHeaderColor = Color(0xFF202124)
internal val DarkCardColor = Color(0xFF242528)
internal val DarkHero = Color(0xFF292A2D)
internal val DarkSoft = Color(0xFF303135)
internal val DarkLine = Color(0xFF3D3F42)
internal val DarkInk = Color(0xFFE6E7E1)
internal val DarkMuted = Color(0xFFB8B9B3)
internal val DarkGreen = Color(0xFF9BA78B)

@Composable
internal fun DarkNavigation(selected: Int, select: (Int) -> Unit) {
    val strings = rememberUiStrings()
    val indicatorPosition = animateFloatAsState(
        selected.toFloat(), tween(AppMotion.Duration, easing = AppMotion.easing), label = "dark-nav-position"
    )
    Column(Modifier.fillMaxWidth().background(DarkHeaderColor)) {
        HorizontalDivider(color = DarkLine)
        Box(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 12.dp, vertical = 8.dp)) {
            Canvas(Modifier.matchParentSize()) {
                val tabWidth = size.width / 4
                val indicatorWidth = 47.dp.toPx()
                drawRoundRect(Color(0xFF373E32), Offset(tabWidth * indicatorPosition.value + (tabWidth - indicatorWidth) / 2, 2.dp.toPx()), Size(indicatorWidth, 31.dp.toPx()), CornerRadius(16.dp.toPx()))
            }
            Row(Modifier.fillMaxWidth()) {
                listOf("首页", "库存", "清单", "我的").forEachIndexed { index, label ->
                    val interaction = remember { MutableInteractionSource() }
                    val pressed by interaction.collectIsPressedAsState()
                    val scale = animateFloatAsState(
                        if (pressed) 0.92f else if (selected == index) 1.06f else 1f,
                        tween(AppMotion.Quick, easing = AppMotion.easing), label = "dark-nav-scale"
                    )
                    val foreground by animateColorAsState(
                        if (selected == index) Color(0xFFC6CEBA) else DarkMuted,
                        tween(AppMotion.Quick), label = "dark-nav-color"
                    )
                    Column(
                        Modifier.weight(1f).clip(RoundedCornerShape(12.dp))
                            .selectable(selected == index, interactionSource = interaction, indication = ripple(), role = Role.Tab, onClick = { select(index) }).padding(vertical = 2.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)
                    ) {
                        Box(Modifier.size(47.dp, 31.dp).graphicsLayer { scaleX = scale.value; scaleY = scale.value }, contentAlignment = Alignment.Center) {
                            DarkGlyph(listOf("home", "box", "cart", "person")[index], Modifier.size(24.dp), foreground)
                        }
                        Text(strings.label(label), color = foreground, fontSize = 11.sp, lineHeight = 16.sp)
                    }
                }
            }
        }
    }
}

@Composable
internal fun DarkHome(store: InventoryStore, open: (StockItem) -> Unit, all: () -> Unit, panel: (String) -> Unit, ask: (String) -> Unit) {
    val strings = rememberUiStrings()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        DarkCard(DarkHero) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(strings.get(R.string.ui_mew_assistant), fontSize = 20.sp, lineHeight = 27.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (store.items.isEmpty()) strings.get(R.string.ui_add_your_first_item) else strings.get(R.string.ui_items___low_expiring___expired, strings.stockCount(store.items.size), store.items.count { it.status(store.reminderDays).low }, store.items.count { it.status(store.reminderDays).soon }, store.items.count { it.status(store.reminderDays).expired }), fontSize = 12.sp, lineHeight = 20.sp)
                }
                MewMascot(MewPose.Overview, Modifier.size(52.dp), strings.get(R.string.ui_mew__your_stock_companion))
            }
            Text(if (store.cloud.signedIn) strings.get(R.string.ui_based_on_household_cloud_inventory) else strings.get(R.string.ui_based_on_local_inventory), fontSize = 10.sp, lineHeight = 15.sp, color = DarkMuted, modifier = Modifier.padding(top = 6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SuggestionChip(onClick = { ask("哪些快过期了？") }, label = { Text(strings.get(R.string.ui_expiring_soon), fontSize = 11.sp, lineHeight = 16.sp) }, shape = CircleShape)
                SuggestionChip(onClick = { ask("需要补什么？") }, label = { Text(strings.get(R.string.ui_restock), fontSize = 11.sp, lineHeight = 16.sp) }, shape = CircleShape)
            }
            var question by rememberSaveable { mutableStateOf("") }
            OutlinedTextField(question, { question = it }, singleLine = true, placeholder = { Text(strings.get(R.string.ui_ask_about_stock__add_items), fontSize = 13.sp) },
                shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(unfocusedContainerColor = DarkHeaderColor, focusedContainerColor = DarkHeaderColor, unfocusedBorderColor = DarkLine),
                trailingIcon = { IconButton(onClick = { if (question.isNotBlank()) { ask(question); question = "" } else panel("AI 智能管家") }, modifier = Modifier.semantics { contentDescription = "发送" }) {
                    Box(Modifier.size(27.dp).background(DarkGreen, CircleShape), contentAlignment = Alignment.Center) { DarkGlyph("arrow", Modifier.size(18.dp), Color(0xFF20251C)) }
                } })
        }
        Text(strings.get(R.string.ui_add_items), fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DarkQuick("camera", strings.get(R.string.ui_photo), Modifier.weight(1f)) { panel("拍照添加") }
            DarkQuick("mic", strings.get(R.string.ui_voice), Modifier.weight(1f)) { panel("语音添加") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(strings.get(R.string.ui_recent_stock), fontSize = 14.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            TextButton(onClick = all) { Text(strings.get(R.string.ui_view_all), fontSize = 11.sp) }
        }
        if (store.items.isEmpty()) MewEmptyState(strings.get(R.string.ui_no_items_yet), strings.get(R.string.ui_add_your_first_item_by_photo))
        store.items.sortedBy { it.status(store.reminderDays).priority }.take(4).forEach { item ->
            key(item.id) { DarkStockRow(item, store.reminderDays) { open(item) } }
        }
    }
}

@Composable
private fun DarkQuick(glyph: String, title: String, modifier: Modifier, action: () -> Unit) {
    Card(modifier = modifier.clip(RoundedCornerShape(18.dp)).semantics { role = Role.Button }.motionClickable(onClick = action), shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, DarkLine), colors = CardDefaults.cardColors(containerColor = DarkCardColor)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DarkGlyph(glyph, Modifier.size(24.dp))
            Text(title, fontSize = 14.sp, lineHeight = 19.sp)
        }
    }
}

@Composable
internal fun DarkInventory(store: InventoryStore, open: (StockItem) -> Unit, add: () -> Unit, voice: () -> Unit) {
    val strings = rememberUiStrings()
    var search by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableStateOf("全部") }
    val result = store.items.filter { item ->
        (item.name.contains(search.trim(), true) || item.location.contains(search.trim(), true)) &&
            when (filter) { "需关注" -> item.status(store.reminderDays).attention; "食品", "日用品" -> item.category == filter; else -> true }
    }.sortedBy { it.status(store.reminderDays).priority }
    LazyColumn(Modifier.fillMaxSize().testTag("dark-inventory-list"), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item(key = "inventory-search") {
            OutlinedTextField(search, { search = it }, placeholder = { Text(strings.get(R.string.ui_search_item_names), fontSize = 14.sp) }, singleLine = true,
                leadingIcon = { DarkGlyph("search", Modifier.size(23.dp)) },
                trailingIcon = { if (search.isNotEmpty()) TextButton(onClick = { search = "" }) { Text(strings.get(R.string.ui_clear)) } },
                shape = RoundedCornerShape(15.dp), modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(unfocusedContainerColor = DarkHeaderColor, focusedContainerColor = DarkHeaderColor, unfocusedBorderColor = DarkLine))
        }
        item(key = "inventory-filters") {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                listOf("全部", "需关注", "食品", "日用品").forEach { label ->
                    FilterChip(filter == label, { filter = label }, { Text(strings.label(label), fontSize = 12.sp, lineHeight = 17.sp) }, shape = CircleShape,
                        colors = FilterChipDefaults.filterChipColors(containerColor = DarkCardColor, labelColor = DarkMuted, selectedContainerColor = DarkGreen, selectedLabelColor = Color(0xFF20251C)))
                }
            }
        }
        item(key = "inventory-summary") {
            DarkCard(DarkHero) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
                    DarkStat(store.items.size, "物品种类")
                    DarkStat(store.items.count { it.status(store.reminderDays).low }, "库存不足")
                    DarkStat(store.items.count { it.status(store.reminderDays).soon }, "即将过期")
                }
            }
        }
        item(key = "inventory-actions") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(strings.get(R.string.ui_household_items), fontSize = 14.sp, modifier = Modifier.weight(1f))
                TextButton(onClick = voice) { Text(strings.get(R.string.ui_voice_2), fontSize = 12.sp) }
                TextButton(onClick = add) { Text(strings.get(R.string.ui___add), fontSize = 12.sp) }
            }
        }
        if (result.isEmpty()) item(key = "inventory-empty") {
            Box(Modifier.animateItem()) { MewEmptyState(if (store.items.isEmpty()) strings.get(R.string.ui_no_items_yet) else strings.get(R.string.ui_no_matching_items), if (store.items.isEmpty()) strings.get(R.string.ui_add_your_first_item_by_photo) else strings.get(R.string.ui_try_another_keyword_or_add_an)) }
        }
        items(result, key = { it.id }) { item ->
            Box(Modifier.animateItem()) { DarkStockRow(item, store.reminderDays) { open(item) } }
        }
    }
}

@Composable
private fun DarkStat(number: Int, label: String) {
    val strings = rememberUiStrings()
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        AppMotionContent(number, label = "inventory-stat") { value ->
            Text(value.toString(), fontSize = 28.sp, lineHeight = 36.sp)
        }
        Text(strings.label(label), fontSize = 11.sp, lineHeight = 17.sp, color = DarkMuted)
    }
}

@Composable
internal fun DarkStockRow(item: StockItem, days: Int, action: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).semantics { role = Role.Button }.motionClickable(onClick = action), shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, DarkLine), colors = CardDefaults.cardColors(containerColor = DarkCardColor)) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(42.dp).background(DarkSoft, RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) { DarkStockIcon(item, Modifier.size(30.dp)) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(item.name, fontSize = 15.sp, lineHeight = 21.sp)
                Text("${item.quantity.display()} ${item.unit} · ${item.location}", fontSize = 11.sp, lineHeight = 16.sp, color = DarkMuted)
            }
            DarkStatus(item.status(days))
        }
    }
}

@Composable
private fun DarkStatus(status: StockStatus) {
    val strings = rememberUiStrings()
    val background by animateColorAsState(
        when { status.expired -> Color(0xFF413436); status.attention -> Color(0xFF3C3932); else -> Color(0xFF373E32) },
        tween(AppMotion.Duration), label = "stock-status-background"
    )
    val foreground by animateColorAsState(
        when { status.expired -> Color(0xFFDAAEA6); status.attention -> Color(0xFFE2C38B); else -> Color(0xFFC6CEBA) },
        tween(AppMotion.Duration), label = "stock-status-foreground"
    )
    Text(strings.label(status.label), fontSize = 10.sp, lineHeight = 15.sp, color = foreground, modifier = Modifier.background(background, CircleShape).padding(horizontal = 8.dp, vertical = 5.dp))
}

@Composable
internal fun DarkShopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    val strings = rememberUiStrings()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item(key = "shopping-summary") {
            DarkCard {
                MewIntro(MewPose.Shopping, strings.get(R.string.ui_a_little_restock), strings.get(R.string.ui_record_what_you_bring_home),
                    Modifier.padding(end = AssistantMascotWidth))
            }
        }
        item(key = "shopping-title") { Text(strings.get(R.string.ui_to_buy_2, store.purchases.size), fontSize = 14.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp)) }
        if (store.purchases.isEmpty()) item(key = "shopping-empty") {
            Box(Modifier.animateItem()) { MewEmptyState(strings.get(R.string.ui_your_shopping_list_is_empty_2), strings.get(R.string.ui_use_the_stock_suggestions_below_to)) }
        }
        items(store.purchases, key = { "purchase-${it.itemId}" }) { task -> store.items.firstOrNull { it.id == task.itemId }?.let { item ->
            CompactPurchaseCard(item, task.quantity, Modifier.animateItem(),
                illustration = { DarkStockIcon(item, Modifier.size(24.dp)) },
                adjust = { action(item.id, "调整采购数量") },
                remove = { store.removePlan(item.id); notify(strings.get(R.string.ui_removed_from_shopping_list)) },
                purchase = { action(item.id, "购买入库") })
        } }
        item(key = "recommendations-title") { Text(strings.get(R.string.ui_stock_suggestions), fontSize = 14.sp, fontWeight = FontWeight.Medium, modifier = Modifier.animateItem().padding(top = 8.dp)) }
        val low = store.items.filter { it.status(store.reminderDays).low }
        if (low.isEmpty()) item(key = "recommendations-empty") {
            Box(Modifier.animateItem()) { MewEmptyState(strings.get(R.string.ui_stock_looks_good), strings.get(R.string.ui_no_items_are_below_their_minimum)) }
        }
        items(low, key = { "recommendation-${it.id}" }) { item ->
            DarkCard(DarkHero, modifier = Modifier.animateItem()) {
                Text(item.name, fontSize = 16.sp, lineHeight = 22.sp)
                Text(strings.get(R.string.ui_current___minimum_suggested_restock__at, item.quantity.display(), item.unit, item.minimum.display(), item.unit, (item.minimum - item.quantity).display(), item.unit), fontSize = 12.sp, lineHeight = 20.sp, modifier = Modifier.padding(vertical = 8.dp))
                OutlinedButton(onClick = { action(item.id, if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (store.purchases.any { it.itemId == item.id }) strings.get(R.string.ui_on_list___adjust) else strings.get(R.string.ui_add_to_list))
                }
            }
        }
    }
}

@Composable
internal fun DarkProfile(store: InventoryStore, open: (String) -> Unit) {
    val strings = rememberUiStrings()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).semantics { role = Role.Button }.motionClickable { open("账号设置") }, shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, DarkLine), colors = CardDefaults.cardColors(containerColor = DarkHero)) {
            Row(Modifier.padding(15.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(13.dp)) {
                MewMascot(MewPose.Overview, Modifier.size(72.dp), strings.get(R.string.ui_mew_profile))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(store.nickname, fontSize = 18.sp, lineHeight = 24.sp)
                    Text(if (store.cloud.signedIn) strings.get(R.string.ui_cloud_account, store.family) else strings.get(R.string.ui_local_profile), fontSize = 11.sp, lineHeight = 17.sp, color = DarkMuted)
                    Text(strings.get(R.string.ui_edit_profile), fontSize = 10.sp, lineHeight = 16.sp, color = DarkMuted)
                }
            }
        }
        DarkMenu("家庭与库存", listOf("我的家庭" to "家庭与位置", "库存检测规则" to "最低库存、到期提醒"), open)
        DarkMenu("账号设置", listOf("登录 / 注册" to if (store.cloud.signedIn) "切换账号或进入本机空间" else "登录家庭云端", "账号设置" to "昵称与账号资料", "通用设置" to "外观与使用偏好", "消息通知" to "管理 App 内库存提醒", "隐私与安全" to "权限说明与数据管理"), open)
        DarkMenu("支持与关于", listOf("帮助与反馈" to "使用指南与问题反馈", "关于 Mewstow" to "让家庭物品管理更轻松"), open)
        Text("Mewstow / Every little thing, remembered.", fontSize = 10.sp, lineHeight = 16.sp, color = DarkMuted, modifier = Modifier.align(Alignment.CenterHorizontally).padding(vertical = 8.dp))
    }
}

@Composable
private fun DarkMenu(title: String, rows: List<Pair<String, String>>, open: (String) -> Unit) {
    val strings = rememberUiStrings()
    Text(strings.label(title), fontSize = 14.sp, lineHeight = 20.sp)
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, DarkLine), colors = CardDefaults.cardColors(containerColor = DarkCardColor)) {
        rows.forEachIndexed { index, (name, description) ->
            Row(Modifier.fillMaxWidth().motionClickable { open(name) }.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                val glyph = when (name) { "我的家庭" -> "home"; "库存检测规则" -> "box"; "账号设置" -> "person"; "消息通知" -> "bell"; "隐私与安全" -> "shield"; "关于 Mewstow" -> "leaf"; else -> "sun" }
                Box(Modifier.size(32.dp).background(DarkSoft, RoundedCornerShape(10.dp)), contentAlignment = Alignment.Center) { DarkGlyph(glyph, Modifier.size(22.dp)) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(if (name == "库存检测规则") strings.get(R.string.ui_stock_rules) else strings.label(name), fontSize = 14.sp, lineHeight = 20.sp)
                    Text(strings.label(description), fontSize = 10.sp, lineHeight = 15.sp, color = DarkMuted)
                }
                Text("›", fontSize = 22.sp, color = DarkMuted)
            }
            if (index != rows.lastIndex) HorizontalDivider(color = DarkLine)
        }
    }
}

@Composable
internal fun DarkDetail(store: InventoryStore, item: StockItem, open: (String) -> Unit, delete: () -> Unit) {
    val strings = rememberUiStrings()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Photo(item.image)
        DarkCard {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Box(Modifier.size(80.dp).background(DarkSoft, RoundedCornerShape(18.dp)), contentAlignment = Alignment.Center) { DarkStockIcon(item, Modifier.size(62.dp)) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(item.name, fontSize = 22.sp, lineHeight = 29.sp, fontWeight = FontWeight.SemiBold)
                    Text("${item.quantity.display()} ${item.unit}", fontSize = 32.sp, lineHeight = 40.sp)
                    DarkStatus(item.status(store.reminderDays))
                }
            }
            Row(Modifier.padding(top = 16.dp)) {
                DarkFact(strings.get(R.string.ui_category), strings.label(item.category), Modifier.weight(1f))
                DarkFact(strings.get(R.string.ui_location_3), item.location, Modifier.weight(1f))
            }
            Row(Modifier.padding(top = 14.dp)) {
                DarkFact(strings.get(R.string.ui_minimum_stock), "${item.minimum.display()} ${item.unit}", Modifier.weight(1f))
                DarkFact(strings.get(R.string.ui_expiry_date), item.expiry.ifBlank { strings.get(R.string.ui_not_set) }, Modifier.weight(1f))
            }
        }
        DarkNotice(reasons(item, store.reminderDays, concise = true, strings = strings), if (item.status(store.reminderDays).attention) Color(0xFF38342B) else DarkSoft)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { open("编辑物品") }, modifier = Modifier.weight(1f)) { Text(strings.get(R.string.ui_edit)) }
            OutlinedButton(onClick = { open("增加库存") }, modifier = Modifier.weight(1f)) { Text(strings.get(R.string.ui_add_stock)) }
            OutlinedButton(onClick = { open("消耗库存") }, modifier = Modifier.weight(1f)) { Text(strings.get(R.string.ui_use_stock)) }
        }
        Button(onClick = { open(if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }, modifier = Modifier.fillMaxWidth()) { Text(strings.get(R.string.ui_add_to_list___adjust)) }
        Text(strings.get(R.string.ui_quantity_history), fontSize = 16.sp, lineHeight = 22.sp)
        item.history.forEach { DarkNotice(it) }
        TextButton(onClick = delete) { Text(strings.get(R.string.ui_delete_item), color = MaterialTheme.colorScheme.error) }
    }
}

@Composable
private fun DarkFact(label: String, value: String, modifier: Modifier) {
    val strings = rememberUiStrings()
    Column(modifier, verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(strings.label(label), fontSize = 12.sp, lineHeight = 18.sp, color = DarkMuted)
        Text(value, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

@Composable
internal fun DarkCard(color: Color = DarkCardColor, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, DarkLine), colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(12.dp), content = content)
    }
}

@Composable
internal fun DarkNotice(text: String, color: Color = DarkSoft) {
    Surface(color = color, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Text(text, fontSize = 12.sp, lineHeight = 20.sp, color = DarkMuted, modifier = Modifier.padding(12.dp))
    }
}

/** Shared flow text preserves the existing light rendering. */
@Composable
internal fun ModeNotice(text: String) {
    if (LocalLightDesign.current) Text(text) else DarkNotice(text)
}

@Composable
internal fun DarkGeneralSettings(store: InventoryStore, notify: (String) -> Unit) {
    val strings = rememberUiStrings()
    DarkCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DarkGlyph("sun", Modifier.size(26.dp))
            LanguageSettings(store)
        }
        HorizontalDivider(color = DarkLine, modifier = Modifier.padding(vertical = 14.dp))
        Text(strings.get(R.string.ui_appearance), fontSize = 16.sp)
        Text(strings.label(store.appearance), style = MaterialTheme.typography.bodySmall, color = DarkMuted, modifier = Modifier.padding(top = 5.dp))
    }
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("跟随系统", "浅色", "深色").forEach { mode ->
            FilterChip(store.appearance == mode, { store.updateAppearance(mode); notify(strings.get(R.string.ui_appearance_saved)) }, { Text(strings.label(mode)) }, shape = CircleShape,
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = DarkGreen, selectedLabelColor = Color(0xFF20251C)))
        }
    }
    DarkNotice(strings.get(R.string.ui_units_are_set_per_item_and))
}

/** Native item illustrations avoid missing emoji glyphs on MuMu's Android font. */
@Composable
private fun DarkStockIcon(item: StockItem, modifier: Modifier) {
    if (item.image.isNotBlank()) {
        StockItemImage(item, modifier) { DarkStockIcon(item.copy(image = ""), Modifier.fillMaxSize()) }
        return
    }
    val kind = when {
        item.name.contains("奶") || item.name.contains("饮") -> "milk"
        item.name.contains("面包") -> "bread"
        item.category == "日用品" -> "soap"
        item.name.contains("蛋") -> "egg"
        item.name.contains("苹果") -> "apple"
        else -> "box"
    }
    Canvas(modifier) {
        withTransform({ scale(size.width / 24f, size.height / 24f, pivot = Offset.Zero) }) {
            when (kind) {
                "milk" -> {
                    val glass = Path().apply { moveTo(3f, 2f); lineTo(21f, 2f); lineTo(18f, 23f); lineTo(6f, 23f); close() }
                    drawPath(glass, Color(0xFFAFE3F6))
                    val milk = Path().apply { moveTo(5f, 7f); lineTo(19f, 7f); lineTo(17f, 21f); lineTo(7f, 21f); close() }
                    drawPath(milk, Color(0xFFDCD8EE))
                    drawLine(Color.White.copy(alpha = .85f), Offset(18f, 4f), Offset(16f, 17f), 1.7f, StrokeCap.Round)
                }
                "bread" -> {
                    drawRoundRect(Color(0xFFC8894D), Offset(3f, 5f), Size(18f, 17f), CornerRadius(3f))
                    drawOval(Color(0xFFF7C578), Offset(2f, 1f), Size(20f, 12f))
                    drawRoundRect(Color(0xFFE4AD68), Offset(3f, 9f), Size(13f, 13f), CornerRadius(2f))
                    listOf(Offset(6f, 13f), Offset(11f, 16f), Offset(7f, 19f)).forEach { drawCircle(Color(0xFFC58B52), .6f, it) }
                }
                "soap" -> {
                    drawRoundRect(Color(0xFFF1ADCA), Offset(6f, 7f), Size(13f, 16f), CornerRadius(4f))
                    drawRect(Color(0xFFC87797), Offset(11f, 3f), Size(3f, 5f))
                    drawRoundRect(Color(0xFFF1ADCA), Offset(8f, 1f), Size(10f, 3f), CornerRadius(1.4f))
                    val drop = Path().apply { moveTo(12f, 10f); cubicTo(2f, 20f, 22f, 22f, 12f, 10f); close() }
                    drawPath(drop, Color(0xFFFFE6F0))
                }
                "egg" -> {
                    val egg = Path().apply { moveTo(12f, 1f); cubicTo(3f, 1f, 0f, 23f, 12f, 23f); cubicTo(24f, 23f, 21f, 1f, 12f, 1f); close() }
                    drawPath(egg, Color(0xFFEAD6B7))
                }
                "apple" -> {
                    drawOval(Color(0xFFD8897A), Offset(2f, 6f), Size(12f, 17f))
                    drawOval(Color(0xFFD8897A), Offset(10f, 6f), Size(12f, 17f))
                    drawLine(Color(0xFFAA9A76), Offset(12f, 9f), Offset(12f, 2f), 1.7f)
                    drawOval(Color(0xFF9BA78B), Offset(12f, 1f), Size(7f, 4f))
                }
                else -> {
                    drawRoundRect(Color(0xFFD2B58A), Offset(3f, 4f), Size(18f, 18f), CornerRadius(2f))
                    drawRect(Color(0xFFF0D5AA), Offset(10f, 4f), Size(4f, 9f))
                    drawLine(Color(0xFF9B7F5A), Offset(3f, 9f), Offset(21f, 9f), 1f)
                }
            }
        }
    }
}

@Composable
internal fun DarkGlyph(kind: String, modifier: Modifier = Modifier.size(24.dp), color: Color = DarkMuted) {
    if (kind !in listOf("home", "box", "sun", "shield", "arrow")) { DesignGlyph(kind, modifier, color); return }
    Canvas(modifier) {
        withTransform({ scale(size.width / 24f, size.height / 24f, pivot = Offset.Zero) }) {
            val stroke = Stroke(1.6f, cap = StrokeCap.Round)
            fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(color, Offset(x1, y1), Offset(x2, y2), 1.6f, StrokeCap.Round)
            when (kind) {
                "home" -> {
                    val path = Path().apply { moveTo(3f, 10f); lineTo(12f, 2f); lineTo(21f, 10f); lineTo(21f, 22f); lineTo(15f, 22f); lineTo(15f, 14f); lineTo(9f, 14f); lineTo(9f, 22f); lineTo(3f, 22f); close() }
                    drawPath(path, color, style = stroke)
                }
                "box" -> {
                    val path = Path().apply { moveTo(3f, 7f); lineTo(12f, 3f); lineTo(21f, 7f); lineTo(21f, 18f); lineTo(12f, 22f); lineTo(3f, 18f); close() }
                    drawPath(path, color, style = stroke); line(3f, 7f, 12f, 12f); line(12f, 12f, 21f, 7f); line(12f, 12f, 12f, 22f)
                }
                "sun" -> {
                    drawCircle(color, 4f, Offset(12f, 12f), style = stroke)
                    line(12f, 1f, 12f, 4f); line(12f, 20f, 12f, 23f); line(1f, 12f, 4f, 12f); line(20f, 12f, 23f, 12f)
                    line(4f, 4f, 6f, 6f); line(18f, 18f, 20f, 20f); line(4f, 20f, 6f, 18f); line(18f, 6f, 20f, 4f)
                }
                "shield" -> {
                    val path = Path().apply { moveTo(12f, 2f); lineTo(21f, 6f); lineTo(21f, 13f); quadraticBezierTo(18f, 20f, 12f, 23f); quadraticBezierTo(6f, 20f, 3f, 13f); lineTo(3f, 6f); close() }
                    drawPath(path, color, style = stroke); line(7f, 12f, 10f, 15f); line(10f, 15f, 17f, 8f)
                }
                "arrow" -> { line(4f, 12f, 20f, 12f); line(14f, 6f, 20f, 12f); line(20f, 12f, 14f, 18f) }
            }
        }
    }
}
