package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.theme.LocalLightDesign
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlin.math.cos
import kotlin.math.sin

// Colors are taken from the supplied mobile design, not from the dark-mode palette.
internal val DesignInk = Color(0xFF30412E)
private val DesignOlive = Color(0xFF476339)
internal val DesignHeaderColor = Color(0xFFAFC47D)
private val DesignPaper = Color(0xFFFAF7E8)
private val DesignSoft = Color(0xFFE4EACF)
private val DesignLine = Color(0xFFC5CFAD)
private val DesignMuted = Color(0xFF68745C)

@Composable
internal fun AppNavigation(selected: Int, select: (Int) -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val barColor = if (LocalLightDesign.current) Color(0xFFF4F3E3) else DarkHeaderColor
    val indicatorPosition = animateFloatAsState(
        selected.toFloat(), tween(AppMotion.Duration, easing = AppMotion.easing), label = "light-nav-position"
    )
    Box(
        Modifier.fillMaxWidth().background(barColor).border(BorderStroke(1.dp, colors.outlineVariant))
            .navigationBarsPadding().padding(horizontal = 12.dp, vertical = 9.dp)
    ) {
        Canvas(Modifier.matchParentSize()) {
            val tabWidth = size.width / 4
            drawRoundRect(colors.primaryContainer, Offset(tabWidth * indicatorPosition.value, 0f), Size(tabWidth, size.height), CornerRadius(12.dp.toPx()))
        }
        Row(Modifier.fillMaxWidth()) {
            listOf("首页", "库存", "清单", "我的").forEachIndexed { index, label ->
                val interaction = remember { MutableInteractionSource() }
                val pressed by interaction.collectIsPressedAsState()
                val scale = animateFloatAsState(
                    if (pressed) 0.92f else if (selected == index) 1.06f else 1f,
                    tween(AppMotion.Quick, easing = AppMotion.easing), label = "light-nav-scale"
                )
                val foreground by animateColorAsState(
                    if (selected == index) colors.onPrimaryContainer else colors.onSurfaceVariant,
                    tween(AppMotion.Quick), label = "light-nav-color"
                )
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(12.dp))
                        .selectable(selected == index, interactionSource = interaction, indication = ripple(), role = Role.Tab, onClick = { select(index) })
                        .padding(vertical = 5.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(3.dp)
                ) {
                    Box(Modifier.size(30.dp).graphicsLayer { scaleX = scale.value; scaleY = scale.value }, contentAlignment = Alignment.Center) {
                        DesignGlyph(listOf("home", "box", "cart", "person")[index], Modifier.size(27.dp), foreground)
                    }
                    Text(strings.label(label), color = foreground, fontSize = 11.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
internal fun DesignInventory(store: InventoryStore, open: (StockItem) -> Unit, add: () -> Unit, voice: () -> Unit) {
    val strings = rememberUiStrings()
    var search by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableStateOf("全部") }
    var ring by rememberSaveable { mutableStateOf(false) }
    val ringVisibility = remember { MutableTransitionState(ring) }.apply { targetState = ring }
    val result = store.items.filter { item ->
        (item.name.contains(search.trim(), true) || item.location.contains(search.trim(), true)) &&
            when (filter) { "需关注" -> item.status(store.reminderDays).attention; "食品", "日用品" -> item.category == filter; else -> true }
    }.sortedBy { it.status(store.reminderDays).priority }
    LazyColumn(Modifier.fillMaxSize().testTag("inventory-list"), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item(key = "inventory-summary") {
            SharedCard(DesignSoft) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    DesignGlyph("box", Modifier.size(39.dp))
                    Column(Modifier.padding(start = 14.dp)) {
                        Text(strings.get(R.string.ui_keep_track_of_home), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Text(strings.get(R.string.ui_items___quantities__dates_and_locations, store.items.size), fontSize = 11.sp, color = DesignMuted, modifier = Modifier.padding(top = 5.dp))
                    }
                }
            }
        }
        item(key = "inventory-actions") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(ring, { ring = true }, { Text(strings.get(R.string.ui_ring), fontSize = 12.sp) })
                FilterChip(!ring, { ring = false }, { Text(strings.get(R.string.ui_list), fontSize = 12.sp) })
                Spacer(Modifier.weight(1f))
                IconButton(onClick = voice, modifier = Modifier.semantics { contentDescription = "语音添加" }) { DesignGlyph("mic", Modifier.size(23.dp)) }
                IconButton(onClick = add, modifier = Modifier.background(DesignOlive, CircleShape).size(36.dp).semantics { contentDescription = "手动添加" }) { DesignGlyph("plus", Modifier.size(21.dp), Color.White) }
            }
        }
        item(key = "inventory-search") {
            OutlinedTextField(search, { search = it }, placeholder = { Text(strings.get(R.string.ui_name_or_location), fontSize = 13.sp) }, singleLine = true,
                trailingIcon = { if (search.isNotEmpty()) TextButton(onClick = { search = "" }) { Text(strings.get(R.string.ui_clear)) } else DesignGlyph("search", Modifier.size(20.dp)) },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp))
        }
        item(key = "inventory-filters") {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(DesignSoft).horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("全部", "需关注", "食品", "日用品").forEach { label -> FilterChip(filter == label, { filter = label }, { Text(strings.label(label), fontSize = 12.sp) }) }
            }
        }
        if (ringVisibility.currentState || ringVisibility.targetState || !ringVisibility.isIdle) item(key = "inventory-ring") {
            AnimatedVisibility(
                visibleState = ringVisibility,
                modifier = Modifier.motionInput(ring),
                enter = expandVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) + fadeIn(tween(AppMotion.Quick)),
                exit = shrinkVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) + fadeOut(tween(AppMotion.Quick))
            ) { InventoryRing(result, store.reminderDays, open) }
        }
        if (result.isEmpty()) item(key = "inventory-empty") {
            Box(Modifier.animateItem()) { MewEmptyState(strings.get(R.string.ui_no_matching_items), if (store.items.isEmpty()) strings.get(R.string.ui_add_an_item_to_start_your) else strings.get(R.string.ui_try_another_keyword_or_filter)) }
        }
        items(result, key = { it.id }) { item ->
            Box(Modifier.animateItem()) { StockRow(item, store.reminderDays) { open(item) } }
        }
    }
}

/** A live inventory ring: no example inventory is added to the user's data. */
@Composable
private fun InventoryRing(items: List<StockItem>, days: Int, open: (StockItem) -> Unit) {
    val strings = rememberUiStrings()
    val visible = items.take(12)
    var selected by rememberSaveable(visible.map { it.id }) { mutableStateOf<String?>(null) }
    val selectedItem = visible.firstOrNull { it.id == selected }
    BoxWithConstraints(Modifier.fillMaxWidth().height(360.dp).clip(RoundedCornerShape(20.dp)).background(DesignPaper)) {
        val diameter = minOf(maxWidth, 300.dp)
        val radius = diameter * 0.38f
        Canvas(Modifier.size(diameter).align(Alignment.Center)) {
            val thickness = size.minDimension * 0.27f
            val inset = thickness / 2f + 4.dp.toPx()
            val arcSize = Size(size.width - inset * 2, size.height - inset * 2)
            if (visible.isEmpty()) drawArc(DesignSoft, 0f, 360f, false, Offset(inset, inset), arcSize, style = Stroke(thickness))
            else visible.forEachIndexed { index, item ->
                val status = item.status(days)
                val color = when { status.expired -> Color(0xFFE48D81); status.soon -> Color(0xFFE6B073); status.low -> Color(0xFFE3CE70); else -> Color(0xFFCCD4B7) }
                drawArc(color, -90f + index * 360f / visible.size + 1.5f, 360f / visible.size - 3f, false, Offset(inset, inset), arcSize, style = Stroke(thickness))
            }
        }
        visible.forEachIndexed { index, item -> key(item.id) {
            val angle = (-90.0 + (index + 0.5) * 360.0 / visible.size) * Math.PI / 180.0
            val selectionColor by animateColorAsState(
                if (selected == item.id) DesignSoft else Color.Transparent,
                tween(AppMotion.Quick), label = "ring-selection"
            )
            Column(
                Modifier.align(Alignment.Center).offset(x = radius * cos(angle).toFloat(), y = radius * sin(angle).toFloat())
                    .size(width = 67.dp, height = 61.dp).clip(RoundedCornerShape(10.dp))
                    .background(selectionColor).motionClickable { selected = item.id }, horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                StockIllustration(item, Modifier.size(24.dp))
                Text(item.name, fontSize = 10.sp, lineHeight = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${item.quantity.display()} ${item.unit}", fontSize = 9.sp, lineHeight = 12.sp, color = DesignOlive)
            }
        } }
        Column(Modifier.align(Alignment.Center).width(116.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            MewMascot(MewPose.Overview, Modifier.size(76.dp), description = null)
            AppMotionContent(selectedItem, label = "ring-details") { current ->
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(current?.name ?: strings.get(R.string.ui_little_things_at_home), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (current == null) Text(strings.get(R.string.ui_remember_them_all), fontSize = 11.sp, color = DesignMuted)
                    else TextButton(onClick = { open(current) }) { Text(strings.get(R.string.ui_view_details), fontSize = 11.sp) }
                }
            }
        }
        Text(strings.get(R.string.ui_items, items.size) + if (items.size > 12) strings.get(R.string.ui___first_12_shown_on_the) else strings.get(R.string.ui___attention_first), fontSize = 10.sp, color = DesignMuted, modifier = Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
internal fun StockRow(item: StockItem, days: Int, action: () -> Unit) {
    val strings = rememberUiStrings()
    val status = item.status(days)
    val colors = MaterialTheme.colorScheme
    Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).semantics { role = Role.Button }.motionClickable(onClick = action), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, colors.outlineVariant), colors = CardDefaults.cardColors(containerColor = colors.surface)) {
        Row(Modifier.fillMaxWidth().background(colors.primaryContainer).padding(13.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(46.dp).background(colors.surface, RoundedCornerShape(11.dp)).border(1.dp, colors.outlineVariant, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) { StockIllustration(item, Modifier.size(34.dp)) }
            Column(Modifier.weight(1f)) {
                Text(item.name, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Bold)
                Text(item.location, fontSize = 11.sp, lineHeight = 16.sp, color = colors.onSurfaceVariant, modifier = Modifier.padding(top = 3.dp))
            }
            Text("${item.quantity.display()} ${item.unit}", fontSize = 11.sp, lineHeight = 16.sp, color = colors.primary, modifier = Modifier.border(1.dp, colors.outline, RoundedCornerShape(7.dp)).padding(horizontal = 9.dp, vertical = 6.dp))
        }
        Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            DesignFact(strings.get(R.string.ui_expiry_date), item.expiry.ifBlank { strings.get(R.string.ui_not_set) })
            HorizontalDivider(color = colors.outlineVariant.copy(alpha = 0.65f))
            DesignFact(strings.get(R.string.ui_status), strings.label(status.label), if (status.attention) colors.error else colors.onSurface)
        }
    }
}

@Composable
internal fun GuestShoppingPage(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val inventory = store.items
    val purchases = store.purchases
    val planned = remember(inventory, purchases) {
        val byId = inventory.associateBy { it.id }
        purchases.mapNotNull { task -> byId[task.itemId]?.let { task to it } }
    }
    ShoppingPaperList(paperItems = maxOf(1, planned.size) + 2) {
        item(key = "shopping-summary") {
            SharedCard(colors.primaryContainer, modifier = Modifier.padding(bottom = 18.dp)) {
                MewIntro(MewPose.Shopping, strings.get(R.string.ui_a_little_restock), strings.get(R.string.ui_record_what_you_bring_home),
                    Modifier.padding(end = AssistantMascotWidth))
            }
        }
        item(key = "shopping-title") { ShoppingPaperHeading(planned.size) }
        if (planned.isEmpty()) item(key = "shopping-empty") {
            ShoppingPaperRow {
                MewEmptyState(strings.get(R.string.ui_your_shopping_list_is_empty_2), strings.get(R.string.ui_use_the_stock_suggestions_below_to))
            }
        }
        items(planned, key = { "purchase-${it.first.itemId}" }) { (task, item) ->
            ShoppingPaperRow(Modifier.animateItem()) {
                CompactPurchaseRow(item, task.quantity,
                    illustration = { StockIllustration(item, Modifier.size(24.dp)) },
                    adjust = { action(item.id, "调整采购数量") },
                    remove = { store.removePlan(item.id); notify(strings.get(R.string.ui_removed_from_shopping_list)) },
                    purchase = { action(item.id, "购买入库") })
            }
        }
        item(key = "shopping-paper-foot") { ShoppingPaperEnd() }
        item(key = "recommendations-title") {
            Box(Modifier.animateItem().padding(top = 14.dp, bottom = 8.dp)) {
                DesignSection(strings.get(R.string.ui_stock_suggestions), strings.get(R.string.ui_check_the_actual_quantity))
            }
        }
        val low = inventory.filter { it.status(store.reminderDays).low }
        if (low.isEmpty()) item(key = "recommendations-empty") { Text(strings.get(R.string.ui_no_items_are_below_their_minimum_2), fontSize = 12.sp, color = colors.onSurfaceVariant, modifier = Modifier.animateItem()) }
        items(low, key = { "recommendation-${it.id}" }) { item ->
            SharedCard(colors.secondaryContainer, modifier = Modifier.animateItem().padding(bottom = 10.dp)) {
                Text(item.name, fontWeight = FontWeight.Bold)
                Text(strings.get(R.string.ui_current___minimum_suggested_restock__at,
                    item.quantity.display(), item.unit, item.minimum.display(), item.unit, (item.minimum - item.quantity).display(), item.unit), fontSize = 12.sp, color = colors.onSurfaceVariant, modifier = Modifier.padding(vertical = 8.dp))
                OutlinedButton(onClick = { action(item.id, if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }) {
                    Text(if (store.purchases.any { it.itemId == item.id }) strings.get(R.string.ui_on_list___adjust) else strings.get(R.string.ui_add_to_list))
                }
            }
        }
    }
}

@Composable
private fun CompactPurchaseRow(
    item: StockItem, quantity: Double,
    illustration: @Composable () -> Unit, adjust: () -> Unit, remove: () -> Unit, purchase: () -> Unit
) {
    val strings = rememberUiStrings()
    val light = LocalLightDesign.current
    val muted = if (light) DesignMuted else DarkMuted
    var menuOpen by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().padding(start = 3.dp, top = 2.dp, bottom = 2.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(34.dp).background(if (light) DesignSoft else DarkSoft, RoundedCornerShape(8.dp)),
                contentAlignment = Alignment.Center) { illustration() }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(item.name, fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("${quantity.display()} ${item.unit}", fontSize = 11.sp, lineHeight = 16.sp, color = muted)
            }
            Box(Modifier.height(48.dp), contentAlignment = Alignment.Center) {
                Button(onClick = purchase, modifier = Modifier.height(32.dp), shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (light) DesignSoft else Color(0xFF3A4334),
                        contentColor = if (light) DesignOlive else Color(0xFFD8E3CD)),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp)) {
                    Text(strings.get(R.string.ui_receive), fontSize = 11.sp, lineHeight = 16.sp)
                }
            }
            Box {
                IconButton(onClick = { menuOpen = true }, modifier = Modifier.size(48.dp)
                    .semantics { contentDescription = strings.get(R.string.ui_more_actions_for, item.name) }) {
                    DesignGlyph("more", Modifier.size(18.dp), muted)
                }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    DropdownMenuItem(text = { Text(strings.get(R.string.ui_adjust_quantity)) }, onClick = { menuOpen = false; adjust() })
                    DropdownMenuItem(text = { Text(strings.get(R.string.ui_remove)) }, onClick = { menuOpen = false; remove() })
                }
            }
        }
}

@Composable
internal fun ProfilePage(store: InventoryStore, open: (String) -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).semantics { role = Role.Button }.motionClickable { open("账号设置") }, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, colors.outlineVariant), colors = CardDefaults.cardColors(containerColor = colors.primaryContainer)) {
            Row(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                MewMascot(MewPose.Overview, Modifier.size(72.dp), strings.get(R.string.ui_mew_profile))
                Column(Modifier.weight(1f).padding(start = 14.dp)) {
                    Text(store.nickname, fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.Bold)
                    Text(store.family, fontSize = 12.sp, lineHeight = 18.sp, color = colors.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
                    Text(if (store.cloud.signedIn) strings.get(R.string.ui_edit_cloud_profile) else strings.get(R.string.ui_edit_local_profile), fontSize = 10.sp, lineHeight = 16.sp, color = colors.primary, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
        ProfileMenu("家庭与库存", listOf("我的家庭" to "home", "库存检测规则" to "checklist"), open)
        ProfileMenu("账号设置", listOf(
            "登录 / 注册" to "sign-in", "账号设置" to "account-card", "通用设置" to "settings",
            "消息通知" to "bell", "隐私与安全" to "privacy-shield"
        ), open)
        ProfileMenu("支持与关于", listOf("帮助与反馈" to "help-chat", "关于 Mewstow" to "info"), open)
        Text(strings.get(R.string.ui_every_little_thing__remembered), color = colors.onSurfaceVariant, fontSize = 11.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp))
    }
}

@Composable
private fun ProfileMenu(title: String, rows: List<Pair<String, String>>, open: (String) -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(strings.label(title), color = colors.onSurfaceVariant, fontSize = 12.sp, lineHeight = 18.sp)
        Card(modifier = Modifier.fillMaxWidth(), border = BorderStroke(1.dp, colors.outlineVariant),
            colors = CardDefaults.cardColors(containerColor = colors.surface), shape = RoundedCornerShape(14.dp)) {
            rows.forEachIndexed { index, (name, glyph) ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).motionClickable { open(name) }
                    .padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    DesignGlyph(glyph, Modifier.size(22.dp), colors.primary)
                    Text(if (name == "库存检测规则") strings.get(R.string.ui_stock_rules) else strings.label(name),
                        Modifier.weight(1f), fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium)
                    Text("›", fontSize = 22.sp, color = colors.onSurfaceVariant)
                }
                if (index != rows.lastIndex) HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = colors.outlineVariant.copy(alpha = 0.65f))
            }
        }
    }
}

@Composable
private fun SharedCard(color: Color = MaterialTheme.colorScheme.surface, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant), colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(12.dp), content = content)
    }
}

@Composable
private fun DesignSection(title: String, subtitle: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        if (subtitle.isNotEmpty()) Text(subtitle, fontSize = 10.sp, lineHeight = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun DesignFact(label: String, value: String, color: Color = MaterialTheme.colorScheme.onSurface) {
    val strings = rememberUiStrings()
    val foreground by animateColorAsState(color, tween(AppMotion.Duration), label = "stock-fact-color")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(strings.label(label), fontSize = 12.sp, lineHeight = 18.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
        Text(value, fontSize = 12.sp, lineHeight = 18.sp, color = foreground)
    }
}

/** Small native illustrations remain crisp at different emulator and phone densities. */
@Composable
private fun StockIllustration(item: StockItem, modifier: Modifier) {
    if (item.image.isNotBlank()) {
        StockItemImage(item, modifier) { StockIllustration(item.copy(image = ""), Modifier.fillMaxSize()) }
        return
    }
    val kind = when { item.name.contains("奶") -> "milk"; item.name.contains("面包") -> "bread"; item.name.contains("苹果") -> "apple"; else -> "box" }
    DesignGlyph(kind, modifier)
}

@Composable
internal fun DesignGlyph(kind: String, modifier: Modifier = Modifier.size(24.dp), color: Color = DesignOlive) {
    Canvas(modifier) {
        withTransform({ scale(size.width / 24f, size.height / 24f, pivot = Offset.Zero) }) {
            val stroke = Stroke(1.5f, cap = StrokeCap.Round)
            fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(color, Offset(x1, y1), Offset(x2, y2), 1.5f, StrokeCap.Round)
            when (kind) {
                "more" -> listOf(5f, 12f, 19f).forEach { drawCircle(color, 1.4f, Offset(it, 12f)) }
                "home" -> {
                    val path = Path().apply { moveTo(3f, 10f); lineTo(12f, 2f); lineTo(21f, 10f); lineTo(21f, 22f); lineTo(15f, 22f); lineTo(15f, 14f); lineTo(9f, 14f); lineTo(9f, 22f); lineTo(3f, 22f); close() }
                    drawPath(path, color, style = stroke)
                }
                "leaf" -> {
                    val path = Path().apply { moveTo(4f, 20f); cubicTo(3f, 7f, 10f, 2f, 21f, 3f); cubicTo(20f, 15f, 12f, 21f, 4f, 20f); close() }
                    drawPath(path, color, style = stroke); line(3f, 22f, 16f, 8f)
                }
                "cart" -> {
                    line(2f, 3f, 5f, 3f); line(5f, 3f, 8f, 16f); line(8f, 16f, 19f, 16f); line(7f, 7f, 22f, 7f); line(22f, 7f, 19f, 13f); line(19f, 13f, 8f, 13f)
                    drawCircle(color, 1.4f, Offset(9f, 21f), style = stroke); drawCircle(color, 1.4f, Offset(18f, 21f), style = stroke)
                }
                "person" -> {
                    drawCircle(color, 3.5f, Offset(12f, 7f), style = stroke)
                    val path = Path().apply { moveTo(4f, 21f); cubicTo(4f, 12f, 20f, 12f, 20f, 21f) }
                    drawPath(path, color, style = stroke); line(4f, 21f, 20f, 21f)
                }
                "bell" -> {
                    val path = Path().apply { moveTo(5f, 17f); lineTo(7f, 14f); lineTo(7f, 8f); cubicTo(7f, 2f, 17f, 2f, 17f, 8f); lineTo(17f, 14f); lineTo(19f, 17f); close() }
                    drawPath(path, color, style = stroke); drawArc(color, 0f, 180f, false, Offset(10f, 18f), Size(4f, 3f), style = stroke)
                }
                "checklist" -> {
                    drawRoundRect(color, Offset(4f, 3f), Size(16f, 18f), CornerRadius(2.5f), style = stroke)
                    for (y in listOf(8f, 15f)) {
                        line(7f, y, 8.5f, y + 1.5f)
                        line(8.5f, y + 1.5f, 11f, y - 1f)
                        line(13.5f, y, 17f, y)
                    }
                }
                "sign-in" -> {
                    val door = Path().apply {
                        moveTo(10f, 3f); lineTo(19f, 3f); lineTo(19f, 21f); lineTo(10f, 21f)
                    }
                    drawPath(door, color, style = stroke)
                    line(3f, 12f, 15f, 12f)
                    line(11f, 8f, 15f, 12f)
                    line(15f, 12f, 11f, 16f)
                }
                "account-card" -> {
                    drawRoundRect(color, Offset(2.5f, 5f), Size(19f, 14f), CornerRadius(2.5f), style = stroke)
                    drawCircle(color, 2f, Offset(8f, 10.5f), style = stroke)
                    val shoulders = Path().apply { moveTo(5f, 16f); quadraticTo(8f, 12f, 11f, 16f) }
                    drawPath(shoulders, color, style = stroke)
                    line(14f, 10f, 18.5f, 10f)
                    line(14f, 14f, 18.5f, 14f)
                }
                "settings" -> {
                    val gear = Path().apply {
                        repeat(32) { point ->
                            val angle = point * (Math.PI / 16.0) - Math.PI / 2.0
                            val radius = if (point % 4 in 1..2) 9.5f else 7.5f
                            val x = 12f + radius * cos(angle).toFloat()
                            val y = 12f + radius * sin(angle).toFloat()
                            if (point == 0) moveTo(x, y) else lineTo(x, y)
                        }
                        close()
                    }
                    drawPath(gear, color, style = stroke)
                    drawCircle(color, 3f, Offset(12f, 12f), style = stroke)
                }
                "privacy-shield" -> {
                    val shield = Path().apply {
                        moveTo(12f, 2.5f); lineTo(20f, 6f); lineTo(20f, 12f)
                        cubicTo(20f, 17f, 16f, 20f, 12f, 22f)
                        cubicTo(8f, 20f, 4f, 17f, 4f, 12f)
                        lineTo(4f, 6f); close()
                    }
                    drawPath(shield, color, style = stroke)
                    drawCircle(color, 1.5f, Offset(12f, 11f), style = stroke)
                    line(12f, 13f, 12f, 16f)
                }
                "help-chat" -> {
                    val bubble = Path().apply {
                        moveTo(12f, 3.5f); cubicTo(6f, 3.5f, 3f, 6.5f, 3f, 11.5f)
                        cubicTo(3f, 14f, 4f, 15.5f, 5.5f, 17f); lineTo(4.5f, 21f); lineTo(9f, 19f)
                        cubicTo(17f, 20f, 21f, 16f, 21f, 11.5f)
                        cubicTo(21f, 6.5f, 18f, 3.5f, 12f, 3.5f); close()
                    }
                    val question = Path().apply {
                        moveTo(10f, 9f); cubicTo(10f, 6f, 15f, 6f, 15f, 9f)
                        cubicTo(15f, 11f, 12.5f, 11f, 12.5f, 13f)
                    }
                    drawPath(bubble, color, style = stroke)
                    drawPath(question, color, style = stroke)
                    drawCircle(color, .8f, Offset(12.5f, 15.5f))
                }
                "info" -> {
                    drawCircle(color, 9f, Offset(12f, 12f), style = stroke)
                    drawCircle(color, 1f, Offset(12f, 7.5f))
                    line(12f, 11f, 12f, 16.5f)
                }
                "camera" -> {
                    drawRoundRect(color, Offset(2f, 6f), Size(20f, 15f), CornerRadius(2f), style = stroke)
                    drawCircle(color, 4f, Offset(12f, 13f), style = stroke); line(8f, 6f, 9f, 3f); line(9f, 3f, 15f, 3f); line(15f, 3f, 16f, 6f)
                }
                "mic" -> {
                    drawRoundRect(color, Offset(9f, 2f), Size(6f, 13f), CornerRadius(3f), style = stroke)
                    drawArc(color, 0f, 180f, false, Offset(6f, 8f), Size(12f, 11f), style = stroke); line(6f, 8f, 6f, 13f); line(18f, 8f, 18f, 13f); line(12f, 19f, 12f, 23f); line(8f, 23f, 16f, 23f)
                }
                "plus" -> { line(12f, 4f, 12f, 20f); line(4f, 12f, 20f, 12f) }
                "search" -> { drawCircle(color, 7f, Offset(10f, 10f), style = stroke); line(15f, 15f, 22f, 22f) }
                "milk" -> {
                    val path = Path().apply { moveTo(6f, 3f); lineTo(15f, 3f); lineTo(19f, 8f); lineTo(19f, 22f); lineTo(5f, 22f); lineTo(5f, 8f); close() }
                    drawPath(path, Color(0xFFFFFEED)); drawPath(path, color, style = stroke)
                    drawRect(Color(0xFFAFCFD0), Offset(6f, 11f), Size(12f, 7f)); line(5f, 8f, 19f, 8f); line(15f, 3f, 15f, 8f)
                    val drop = Path().apply { moveTo(12f, 12f); cubicTo(7f, 17f, 17f, 18f, 12f, 12f); close() }
                    drawPath(drop, color, style = Stroke(1f))
                }
                "bread" -> {
                    val path = Path().apply { moveTo(5f, 10f); cubicTo(0f, 4f, 7f, 1f, 9f, 4f); cubicTo(12f, 0f, 18f, 2f, 19f, 5f); cubicTo(24f, 6f, 23f, 10f, 19f, 11f); lineTo(18f, 22f); lineTo(6f, 22f); close() }
                    drawPath(path, Color(0xFFE5C889)); drawPath(path, color, style = stroke); line(10f, 10f, 11f, 19f); line(15f, 10f, 14f, 19f)
                }
                "apple" -> {
                    val path = Path().apply { moveTo(12f, 7f); cubicTo(3f, 0f, 0f, 16f, 8f, 22f); cubicTo(11f, 24f, 13f, 20f, 16f, 22f); cubicTo(24f, 16f, 22f, 0f, 12f, 7f); close() }
                    drawPath(path, Color(0xFFD99A88)); drawPath(path, color, style = stroke); line(12f, 7f, 13f, 2f)
                }
                else -> {
                    val path = Path().apply { moveTo(3f, 7f); lineTo(12f, 3f); lineTo(21f, 7f); lineTo(21f, 18f); lineTo(12f, 22f); lineTo(3f, 18f); close() }
                    drawPath(path, Color(0xFFE3D6A9)); drawPath(path, color, style = stroke); line(3f, 7f, 12f, 12f); line(12f, 12f, 21f, 7f); line(12f, 12f, 12f, 22f)
                }
            }
        }
    }
}
