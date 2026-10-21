package com.example.teamapp.ui

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
private val DesignRed = Color(0xFFB75649)

@Composable
internal fun DesignNavigation(selected: Int, select: (Int) -> Unit) {
    val indicatorPosition = animateFloatAsState(
        selected.toFloat(), tween(AppMotion.Duration, easing = AppMotion.easing), label = "light-nav-position"
    )
    Box(
        Modifier.fillMaxWidth().background(Color(0xFFF4F3E3)).border(BorderStroke(1.dp, DesignLine))
            .navigationBarsPadding().padding(horizontal = 12.dp, vertical = 9.dp)
    ) {
        Canvas(Modifier.matchParentSize()) {
            val tabWidth = size.width / 4
            drawRoundRect(DesignSoft, Offset(tabWidth * indicatorPosition.value, 0f), Size(tabWidth, size.height), CornerRadius(12.dp.toPx()))
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
                    if (selected == index) DesignOlive else DesignMuted,
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
                        if (index == 0) MewMascot(MewPose.Overview, Modifier.size(30.dp), description = null)
                        else DesignGlyph(listOf("leaf", "box", "cart", "person")[index], Modifier.size(27.dp), foreground)
                    }
                    Text(label, color = foreground, fontSize = 11.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
internal fun DesignHome(store: InventoryStore, open: (StockItem) -> Unit, all: () -> Unit, panel: (String) -> Unit, ask: (String) -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("家里的小物", fontSize = 11.sp, color = DesignMuted)
                Text("你好，欢迎回家", fontSize = 25.sp, fontWeight = FontWeight.Bold, color = DesignInk, modifier = Modifier.padding(top = 6.dp))
                Text(LocalDate.now().format(DateTimeFormatter.ofPattern("M月d日")) + "  ·  慢慢记好每一件小物", fontSize = 11.sp, color = DesignMuted, modifier = Modifier.padding(top = 6.dp))
            }
            MewMascot(MewPose.Welcome, Modifier.size(94.dp), "欢迎回家的 Mew")
        }
        DesignCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                MewMascot(MewPose.Overview, Modifier.size(64.dp), null)
                Column(Modifier.weight(1f).padding(start = 10.dp)) {
                    Text("Mew · AI 智能管家", fontWeight = FontWeight.Bold, fontSize = 19.sp)
                    Text("家里的物品，一起记清楚", fontSize = 11.sp, color = DesignMuted, modifier = Modifier.padding(top = 4.dp))
                }
            }
            HorizontalDivider(color = DesignLine, modifier = Modifier.padding(vertical = 13.dp))
            Text(
                if (store.items.isEmpty()) "从记录第一件物品开始，让家更有条理。"
                else "已记好 ${store.items.size} 种物品 · ${store.items.count { it.status(store.reminderDays).attention }} 种需要关注",
                fontSize = 13.sp, lineHeight = 21.sp
            )
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AssistChip(onClick = { ask("哪些快过期了？") }, label = { Text("哪些快过期了？", fontSize = 11.sp) })
                AssistChip(onClick = { ask("需要补什么？") }, label = { Text("需要补什么？", fontSize = 11.sp) })
            }
            var question by rememberSaveable { mutableStateOf("") }
            OutlinedTextField(
                question, { question = it }, singleLine = true,
                placeholder = { Text("问问 Mew，或记一件小物…", fontSize = 12.sp) },
                trailingIcon = { TextButton(onClick = {
                    if (question.isNotBlank()) { ask(question); question = "" } else panel("AI 智能管家")
                }) { Text("发送", fontSize = 12.sp) } },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(10.dp)
            )
            Text(if (store.cloud.signedIn) "回答依据当前家庭的云端库存记录" else "回答依据本机已确认的库存记录", fontSize = 10.sp, color = DesignMuted, modifier = Modifier.padding(top = 8.dp))
        }
        DesignSection("记一件家里的小物", "快捷添加")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DesignQuick("camera", "拍照添加", "拍一下，慢慢核对", Modifier.weight(1f)) { panel("拍照添加") }
            DesignQuick("mic", "语音添加", "说出来，轻松记录", Modifier.weight(1f)) { panel("语音添加") }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("最近库存状态", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(onClick = all) { Text("查看全部 ›", fontSize = 11.sp) }
        }
        if (store.items.isEmpty()) MewEmptyState("还没有记录物品", "拍照、语音或手动添加第一件家庭物品")
        store.items.sortedBy { it.status(store.reminderDays).priority }.take(4).forEach { item ->
            key(item.id) { DesignStockRow(item, store.reminderDays) { open(item) } }
        }
    }
}

@Composable
private fun DesignQuick(glyph: String, title: String, subtitle: String, modifier: Modifier, action: () -> Unit) {
    Card(modifier = modifier.clip(RoundedCornerShape(14.dp)).semantics { role = Role.Button }.motionClickable(onClick = action), border = BorderStroke(1.dp, DesignLine), colors = CardDefaults.cardColors(containerColor = DesignSoft), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(15.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            DesignGlyph(glyph, Modifier.size(29.dp))
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(subtitle, fontSize = 10.sp, color = DesignMuted)
        }
    }
}

@Composable
internal fun DesignInventory(store: InventoryStore, open: (StockItem) -> Unit, add: () -> Unit, voice: () -> Unit) {
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
            DesignCard(DesignSoft) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    DesignGlyph("box", Modifier.size(39.dp))
                    Column(Modifier.padding(start = 14.dp)) {
                        Text("家的小物，记得清楚", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Text("${store.items.size} 种物品 · 数量、日期与位置", fontSize = 11.sp, color = DesignMuted, modifier = Modifier.padding(top = 5.dp))
                    }
                }
            }
        }
        item(key = "inventory-actions") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(ring, { ring = true }, { Text("圆环", fontSize = 12.sp) })
                FilterChip(!ring, { ring = false }, { Text("列表", fontSize = 12.sp) })
                Spacer(Modifier.weight(1f))
                IconButton(onClick = voice, modifier = Modifier.semantics { contentDescription = "语音添加" }) { DesignGlyph("mic", Modifier.size(23.dp)) }
                IconButton(onClick = add, modifier = Modifier.background(DesignOlive, CircleShape).size(36.dp).semantics { contentDescription = "手动添加" }) { DesignGlyph("plus", Modifier.size(21.dp), Color.White) }
            }
        }
        item(key = "inventory-search") {
            OutlinedTextField(search, { search = it }, placeholder = { Text("名称或位置", fontSize = 13.sp) }, singleLine = true,
                trailingIcon = { if (search.isNotEmpty()) TextButton(onClick = { search = "" }) { Text("清空") } else DesignGlyph("search", Modifier.size(20.dp)) },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp))
        }
        item(key = "inventory-filters") {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(DesignSoft).horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("全部", "需关注", "食品", "日用品").forEach { label -> FilterChip(filter == label, { filter = label }, { Text(label, fontSize = 12.sp) }) }
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
            Box(Modifier.animateItem()) { MewEmptyState("没有匹配的物品", if (store.items.isEmpty()) "先记下一件小物，圆环会随真实库存展开" else "试试其他关键词或筛选条件") }
        }
        items(result, key = { it.id }) { item ->
            Box(Modifier.animateItem()) { DesignStockRow(item, store.reminderDays) { open(item) } }
        }
    }
}

/** A live inventory ring: no example inventory is added to the user's data. */
@Composable
private fun InventoryRing(items: List<StockItem>, days: Int, open: (StockItem) -> Unit) {
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
                    Text(current?.name ?: "家里的小物", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (current == null) Text("慢慢记好", fontSize = 11.sp, color = DesignMuted)
                    else TextButton(onClick = { open(current) }) { Text("查看详情 ›", fontSize = 11.sp) }
                }
            }
        }
        Text("${items.size} 种物品" + if (items.size > 12) " · 圆环展示前 12 种" else " · 按关注程度排列", fontSize = 10.sp, color = DesignMuted, modifier = Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
internal fun DesignStockRow(item: StockItem, days: Int, action: () -> Unit) {
    val status = item.status(days)
    Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).semantics { role = Role.Button }.motionClickable(onClick = action), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, DesignLine), colors = CardDefaults.cardColors(containerColor = Color(0xFFF7F5E8))) {
        Row(Modifier.fillMaxWidth().background(DesignSoft).padding(13.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(46.dp).background(Color(0xFFFBFAEE), RoundedCornerShape(11.dp)).border(1.dp, DesignLine, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) { StockIllustration(item, Modifier.size(34.dp)) }
            Column(Modifier.weight(1f)) {
                Text(item.name, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Text("${item.quantity.display()} ${item.unit} · ${item.location}", fontSize = 11.sp, color = DesignMuted, modifier = Modifier.padding(top = 4.dp))
            }
            Text("${item.quantity.display()} ${item.unit}", fontSize = 11.sp, color = DesignOlive, modifier = Modifier.border(1.dp, Color(0xFFA7BC80), RoundedCornerShape(7.dp)).padding(horizontal = 9.dp, vertical = 6.dp))
        }
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            DesignFact("保质日期", item.expiry.ifBlank { "未设置" })
            HorizontalDivider(color = DesignLine.copy(alpha = 0.65f))
            DesignFact("状态", status.label, if (status.attention) DesignRed else DesignInk)
        }
    }
}

@Composable
internal fun DesignShopping(store: InventoryStore, action: (String, String) -> Unit, notify: (String) -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
        item(key = "shopping-summary") {
            DesignCard(DesignSoft) {
                MewIntro(MewPose.Shopping, "把生活所需，慢慢补齐", "待采购 ${store.purchases.size} 项 · 买好后记得确认入库",
                    Modifier.padding(end = AssistantMascotWidth))
            }
        }
        item(key = "shopping-title") { DesignSection("待采购", "${store.purchases.size} 项") }
        if (store.purchases.isEmpty()) item(key = "shopping-empty") {
            Box(Modifier.animateItem()) { MewEmptyState("采购清单还是空的", "看看下方的库存推荐，把补货计划记下来") }
        }
        items(store.purchases, key = { "purchase-${it.itemId}" }) { task ->
            store.items.firstOrNull { it.id == task.itemId }?.let { item ->
                DesignCard(modifier = Modifier.animateItem()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StockIllustration(item, Modifier.size(40.dp))
                        Column(Modifier.weight(1f).padding(start = 12.dp)) {
                            Text(item.name, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Text("待采购 ${task.quantity.display()} ${item.unit}", fontSize = 12.sp, color = DesignMuted)
                        }
                        DesignGlyph("cart", Modifier.size(24.dp))
                    }
                    Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { action(item.id, "调整采购数量") }) { Text("调整") }
                        TextButton(onClick = { store.removePlan(item.id); notify("已移出采购清单") }) { Text("移除") }
                        Spacer(Modifier.weight(1f))
                        Button(onClick = { action(item.id, "购买入库") }) { Text("已购买") }
                    }
                }
            }
        }
        item(key = "recommendations-title") {
            Box(Modifier.animateItem()) { DesignSection("根据库存推荐", "记得核对实际数量") }
        }
        val low = store.items.filter { it.status(store.reminderDays).low }
        if (low.isEmpty()) item(key = "recommendations-empty") { Text("目前没有低于最低库存的物品。", fontSize = 12.sp, color = DesignMuted, modifier = Modifier.animateItem()) }
        items(low, key = { "recommendation-${it.id}" }) { item ->
            DesignCard(Color(0xFFF1E8CB), modifier = Modifier.animateItem()) {
                Text(item.name, fontWeight = FontWeight.Bold)
                Text("当前 ${item.quantity.display()} ${item.unit} · 最低 ${item.minimum.display()} ${item.unit}", fontSize = 12.sp, color = DesignMuted, modifier = Modifier.padding(vertical = 8.dp))
                OutlinedButton(onClick = { action(item.id, if (store.purchases.any { it.itemId == item.id }) "调整采购数量" else "加入采购清单") }) {
                    Text(if (store.purchases.any { it.itemId == item.id }) "已在清单 · 调整" else "加入清单")
                }
            }
        }
    }
}

@Composable
internal fun DesignProfile(store: InventoryStore, open: (String) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp), verticalArrangement = Arrangement.spacedBy(17.dp)) {
        Card(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).semantics { role = Role.Button }.motionClickable { open("账号设置") }, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, DesignLine), colors = CardDefaults.cardColors(containerColor = DesignSoft)) {
            Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                MewMascot(MewPose.Overview, Modifier.size(72.dp), "Mew 个人资料")
                Column(Modifier.weight(1f).padding(start = 14.dp)) {
                    Text(store.nickname, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(store.family, fontSize = 12.sp, color = DesignMuted, modifier = Modifier.padding(top = 5.dp))
                    Text(if (store.cloud.signedIn) "云端账号 · 编辑资料 ›" else "本机个人资料 · 编辑资料 ›", fontSize = 10.sp, color = DesignOlive, modifier = Modifier.padding(top = 8.dp))
                }
            }
        }
        DesignMenu("家庭与物品管理", listOf("我的家庭" to "家庭空间与存放位置", "库存检测规则" to "最低库存与有效期提醒"), open)
        DesignMenu("账号与个人设置", listOf("登录 / 注册" to if (store.cloud.signedIn) "切换账号或进入本机空间" else "手机号登录 · 家庭云端空间", "账号设置" to "昵称与账号资料", "通用设置" to "外观与使用偏好", "消息通知" to "管理 App 内库存提醒", "隐私与安全" to "权限说明与数据管理"), open)
        DesignMenu("支持与关于", listOf("帮助与反馈" to "使用指南与问题反馈", "关于 Mewstow" to "让家庭物品管理更轻松"), open)
        Text("家的小物，慢慢记好。", color = DesignMuted, fontSize = 11.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
    }
}

@Composable
private fun DesignMenu(title: String, rows: List<Pair<String, String>>, open: (String) -> Unit) {
    Text(title, color = DesignMuted, fontSize = 12.sp)
    Card(modifier = Modifier.fillMaxWidth(), border = BorderStroke(1.dp, DesignLine), colors = CardDefaults.cardColors(containerColor = Color(0xFFF7F5E8)), shape = RoundedCornerShape(14.dp)) {
        rows.forEachIndexed { index, (name, description) ->
            Row(Modifier.fillMaxWidth().motionClickable { open(name) }.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                DesignGlyph(if (name == "我的家庭") "leaf" else if (name == "消息通知") "bell" else if (name == "账号设置") "person" else "box", Modifier.size(23.dp))
                Column(Modifier.weight(1f).padding(horizontal = 13.dp)) {
                    Text(name, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Text(description, fontSize = 10.sp, color = DesignMuted, modifier = Modifier.padding(top = 3.dp))
                }
                Text("›", fontSize = 22.sp, color = DesignMuted)
            }
            if (index != rows.lastIndex) HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = DesignLine.copy(alpha = 0.65f))
        }
    }
}

@Composable
private fun DesignCard(color: Color = Color(0xFFF7F5E8), modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, DesignLine), colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(15.dp), content = content)
    }
}

@Composable
private fun DesignSection(title: String, subtitle: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text(subtitle, fontSize = 10.sp, color = DesignMuted)
    }
}

@Composable
private fun DesignFact(label: String, value: String, color: Color = DesignInk) {
    val foreground by animateColorAsState(color, tween(AppMotion.Duration), label = "stock-fact-color")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, fontSize = 12.sp, color = DesignMuted, modifier = Modifier.weight(1f))
        Text(value, fontSize = 12.sp, color = foreground)
    }
}

/** Small native illustrations remain crisp at different emulator and phone densities. */
@Composable
private fun StockIllustration(item: StockItem, modifier: Modifier) {
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
