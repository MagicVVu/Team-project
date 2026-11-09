package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
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

@Composable
internal fun ModeNotice(text: String) {
    val colors = MaterialTheme.colorScheme
    Surface(color = colors.surfaceVariant, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Text(text, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant,
            modifier = Modifier.padding(12.dp))
    }
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
