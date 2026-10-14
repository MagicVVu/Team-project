package com.example.teamapp.ui.ring

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.*
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlin.math.*

/** Data and actions belong to the caller: this browser never writes to InventoryStore. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun StockRingBrowser(
    items: List<StockItem>, reminderDays: Int,
    onOpenItem: (StockItem) -> Unit, onAdd: () -> Unit,
    modifier: Modifier = Modifier,
    onSelectedItem: (StockItem?) -> Unit = {}
) {
    val light = LocalLightDesign.current
    val scheme = MaterialTheme.colorScheme
    val focus = LocalFocusManager.current
    var query by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf("全部") }
    var attention by rememberSaveable { mutableStateOf(false) }
    var order by rememberSaveable { mutableStateOf(RingOrder.STATUS) }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    val scopeKey = listOf(query, category, attention.toString(), order.name)
    val incoming = remember(items, reminderDays, scopeKey) { ringResults(items, reminderDays, query, category, attention, order) }
    var displayed by remember { mutableStateOf(incoming) }
    var previousIds by remember { mutableStateOf<List<String>>(emptyList()) }
    var previousScope by remember { mutableStateOf(scopeKey) }
    var interacting by remember { mutableStateOf(false) }
    val position = remember { Animatable(0f) }
    var dragPosition by remember { mutableStateOf<Float?>(null) }
    var seeking by remember { mutableStateOf(false) }
    var motion by remember { mutableStateOf<Job?>(null) }
    val coroutineScope = rememberCoroutineScope()
    val selected = displayed.firstOrNull { it.id == selectedId }
    val displayPosition = dragPosition ?: position.value
    val currentIndex = RingMath.index(displayPosition, displayed.size)
    val infoItem = if (interacting) displayed.getOrNull(currentIndex) else selected
    val selectedCallback by rememberUpdatedState(onSelectedItem)

    // Freeze ordering during a gesture/animation. Reconcile by ID when the motion finishes.
    LaunchedEffect(incoming, scopeKey, interacting) {
        if (!interacting) {
            val ids = incoming.map { it.id }
            selectedId = RingMath.selection(previousIds, ids, selectedId, previousScope != scopeKey)
            displayed = incoming
            previousIds = ids
            previousScope = scopeKey
            position.snapTo(ids.indexOf(selectedId).coerceAtLeast(0).toFloat())
            selectedCallback(incoming.firstOrNull { it.id == selectedId })
        }
    }

    fun settle(value: Float, immediate: Boolean = false) {
        motion?.cancel()
        if (displayed.isEmpty()) { interacting = false; dragPosition = null; seeking = false; return }
        val target = RingMath.index(value, displayed.size)
        interacting = true
        motion = coroutineScope.launch {
            position.snapTo(if (immediate) target.toFloat() else value)
            dragPosition = null
            seeking = false
            if (!immediate) position.animateTo(target.toFloat(), spring(dampingRatio = .86f, stiffness = 420f))
            selectedId = displayed[target].id
            selectedCallback(displayed[target])
            interacting = false
        }
    }

    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.padding(horizontal = 12.dp).fillMaxWidth().height(30.dp)
            .background(scheme.surface, RoundedCornerShape(9.dp)).border(1.dp, scheme.outlineVariant, RoundedCornerShape(9.dp)).padding(horizontal = 9.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            DesignGlyph("search", Modifier.size(15.dp), scheme.onSurfaceVariant)
            BasicTextField(query, { query = it }, singleLine = true, textStyle = TextStyle(color = scheme.onSurface, fontSize = 12.sp),
                modifier = Modifier.weight(1f).testTag("ring-search").semantics { contentDescription = "搜索物品名称" },
                decorationBox = { field -> Box { if (query.isEmpty()) Text("搜索物品名称", fontSize = 12.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant); field() } })
            if (query.isNotEmpty()) Text("清空", fontSize = 11.sp, color = scheme.primary,
                modifier = Modifier.clickable { query = ""; focus.clearFocus() }.padding(3.dp))
        }

        BoxWithConstraints(Modifier.fillMaxWidth().testTag("ring-viewport")) {
            val viewportWidth = maxWidth
            val viewportHeight = maxWidth * 1.32f
            val widthPx = constraints.maxWidth.toFloat()
            val heightPx = widthPx * 1.32f
            val center = Offset(widthPx * .98f, heightPx / 2f)
            val radius = widthPx * .68f
            val thickness = widthPx * .235f
            val inner = radius - thickness / 2f
            val outer = radius + thickness / 2f
            val visibleIndices = RingMath.visible(displayPosition, displayed.size)
            val fills = remember(light) { if (light) listOf(Color(0xFFDF9790), Color(0xFFE9BD8E), Color(0xFFBFCBA0), Color(0xFFD1DABD))
                else listOf(Color(0xFF59464A), Color(0xFF5A5345), Color(0xFF495243), Color(0xFF3C4440)) }
            val track = if (light) Color(0xFFE9EDD9) else Color(0xFF292E2C)
            val activeInk = if (light) Color(0xFF30412E) else Color(0xFFE6E7E1)

            Box(Modifier.fillMaxWidth().height(viewportHeight).clip(RoundedCornerShape(12.dp))
                .pointerInput(displayed.map { it.id }, widthPx, heightPx) {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        if (displayed.isEmpty()) return@awaitEachGesture
                        val distance = (down.position - center).getDistance()
                        if (distance !in (inner - 12f)..(outer + 12f)) return@awaitEachGesture
                        var lastAngle = atan2(down.position.y - center.y, down.position.x - center.x) * 180f / PI.toFloat()
                        var started = false
                        var released = false
                        try {
                            do {
                                val event = awaitPointerEvent()
                                val change = event.changes.firstOrNull { it.id == down.id } ?: break
                                if (!change.pressed) { released = true; break }
                                if (!started && (change.position - down.position).getDistance() > viewConfiguration.touchSlop) {
                                    started = true
                                    focus.clearFocus()
                                    motion?.cancel()
                                    interacting = true
                                    dragPosition = position.value
                                }
                                if (started) {
                                    val angle = atan2(change.position.y - center.y, change.position.x - center.x) * 180f / PI.toFloat()
                                    dragPosition = RingMath.drag(dragPosition ?: position.value, RingMath.deltaDegrees(lastAngle, angle), displayed.size)
                                    change.consume()
                                    lastAngle = angle
                                }
                            } while (true)
                        } finally {
                            if (started) settle(dragPosition ?: position.value)
                        }
                        // Card labels handle taps. The background also accepts taps on the arc.
                        if (!started && released) {
                            val angle = atan2(down.position.y - center.y, down.position.x - center.x) * 180f / PI.toFloat()
                            val relative = RingMath.deltaDegrees(180f, angle)
                            val target = (position.value + relative / RingMath.STEP).roundToInt()
                            if (abs(relative) <= 80f && target in displayed.indices) settle(target.toFloat())
                        }
                    }
                }) {
                Canvas(Modifier.fillMaxSize()) {
                    drawPath(sector(center, inner, outer, 96f, 168f), track)
                    visibleIndices.forEach { index ->
                        val delta = (index - displayPosition) * RingMath.STEP
                        if (abs(delta) <= 84f) {
                            val status = displayed[index].status(reminderDays)
                            val color = fills[status.priority]
                            val chosen = index == currentIndex
                            val path = sector(center, inner - if (chosen) 2.dp.toPx() else 0f,
                                outer + if (chosen) 3.dp.toPx() else 0f, RingMath.angle(index, displayPosition) - RingMath.SWEEP / 2f, RingMath.SWEEP)
                            drawPath(path, color)
                            if (chosen) drawPath(path, scheme.primary, style = Stroke(2.dp.toPx()))
                        }
                    }
                }
                visibleIndices.forEach { index ->
                    val delta = (index - displayPosition) * RingMath.STEP
                    if (abs(delta) <= 79f) {
                        val item = displayed[index]
                        val angle = RingMath.angle(index, displayPosition) * PI.toFloat() / 180f
                        val boxWidth = viewportWidth * .205f
                        val boxHeight = viewportWidth * .29f
                        Column(Modifier.offset { IntOffset((center.x + radius * cos(angle) - widthPx * .205f / 2f).roundToInt(), (center.y + radius * sin(angle) - widthPx * .29f / 2f).roundToInt()) }
                            .size(boxWidth, boxHeight).testTag("ring-card-${item.id}")
                            .semantics { contentDescription = "圆环物品：${item.name}"; this.selected = index == currentIndex }
                            .clickable { focus.clearFocus(); settle(index.toFloat()) },
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            DesignGlyph(if (item.name.contains("奶")) "milk" else if (item.name.contains("面包")) "bread" else if (item.name.contains("苹果")) "apple" else "box", Modifier.size(21.dp), activeInk)
                            Text(item.name, fontSize = 10.sp, lineHeight = 12.sp, color = activeInk, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(top = 2.dp))
                            Text("${item.quantity.display()} ${item.unit}", fontSize = 9.sp, lineHeight = 12.sp, color = activeInk, maxLines = 1)
                            Text(item.status(reminderDays).label, fontSize = 8.sp, lineHeight = 11.sp, color = activeInk, maxLines = 1)
                        }
                    }
                }
                CategoryPanel(items, reminderDays, query, category, { category = it; focus.clearFocus() }, attention, { attention = it }, order, { order = it },
                    Modifier.align(Alignment.CenterEnd).padding(end = 8.dp).width(106.dp), onAdd)
            }
        }

        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            TextButton(onClick = { settle((currentIndex - 1).toFloat()) }, enabled = currentIndex > 0, modifier = Modifier.testTag("ring-previous"), contentPadding = PaddingValues(5.dp)) { Text("‹") }
            Text("${if (currentIndex < 0) 0 else currentIndex + 1} / ${displayed.size}", fontSize = 13.sp, lineHeight = 18.sp,
                modifier = Modifier.testTag("ring-position").semantics { contentDescription = "当前位置 ${if (currentIndex < 0) 0 else currentIndex + 1}，结果总数 ${displayed.size}" })
            TextButton(onClick = { settle((currentIndex + 1).toFloat()) }, enabled = currentIndex >= 0 && currentIndex < displayed.lastIndex, modifier = Modifier.testTag("ring-next"), contentPadding = PaddingValues(5.dp)) { Text("›") }
        }
        if (displayed.size > 1) {
            Text(if (seeking) "定位至：${displayed[currentIndex].name}" else "拖动进度条快速定位 · 沿圆弧滑动浏览", fontSize = 10.sp, lineHeight = 14.sp,
                color = scheme.onSurfaceVariant, modifier = Modifier.align(Alignment.CenterHorizontally).testTag("ring-seek-label"))
            Slider(value = displayPosition.coerceIn(0f, displayed.lastIndex.toFloat()), onValueChange = {
                motion?.cancel(); interacting = true; seeking = true; dragPosition = it; focus.clearFocus()
            }, onValueChangeFinished = { settle(dragPosition ?: position.value, immediate = true) }, valueRange = 0f..displayed.lastIndex.toFloat(),
                thumb = { Box(Modifier.size(14.dp).background(scheme.primary, androidx.compose.foundation.shape.CircleShape)) },
                track = { state -> SliderDefaults.Track(state, modifier = Modifier.height(3.dp)) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(27.dp).testTag("ring-seek"))
        }
        if (infoItem != null) {
            Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp).testTag("ring-selected-info").semantics { contentDescription = "已选中物品：${infoItem.name}" }, border = BorderStroke(1.dp, scheme.outlineVariant), colors = CardDefaults.cardColors(containerColor = scheme.surface)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row {
                        Text(infoItem.name, fontSize = 16.sp, lineHeight = 21.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 2)
                        Text("${infoItem.quantity.display()} ${infoItem.unit}", fontSize = 12.sp, color = scheme.primary)
                    }
                    Text("${infoItem.category} · ${infoItem.location} · ${infoItem.status(reminderDays).label}", fontSize = 11.sp, lineHeight = 16.sp)
                    Text("有效期 ${infoItem.expiry.ifBlank { "未设置" }} · 最低库存 ${infoItem.minimum.display()} ${infoItem.unit}", fontSize = 10.sp, lineHeight = 15.sp, color = scheme.onSurfaceVariant)
                    TextButton(onClick = { onOpenItem(infoItem) }, enabled = !interacting, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(28.dp).testTag("ring-detail")) { Text("查看详情 →", fontSize = 12.sp) }
                }
            }
        } else {
            Column(Modifier.fillMaxWidth().padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(if (items.isEmpty()) "库存为空，添加第一件物品" else "搜索或筛选没有结果", fontSize = 14.sp)
                TextButton(onClick = { if (items.isEmpty()) onAdd() else { query = ""; category = "全部"; attention = false; focus.clearFocus() } }, modifier = Modifier.testTag("ring-empty-action")) {
                    Text(if (items.isEmpty()) "添加物品" else "清空搜索和筛选")
                }
            }
        }
    }
}

private fun sector(center: Offset, inner: Float, outer: Float, start: Float, sweep: Float): Path {
    val radians = start * PI.toFloat() / 180f
    return Path().apply {
        moveTo(center.x + outer * cos(radians), center.y + outer * sin(radians))
        arcTo(androidx.compose.ui.geometry.Rect(center - Offset(outer, outer), Size(outer * 2, outer * 2)), start, sweep, false)
        val end = (start + sweep) * PI.toFloat() / 180f
        lineTo(center.x + inner * cos(end), center.y + inner * sin(end))
        arcTo(androidx.compose.ui.geometry.Rect(center - Offset(inner, inner), Size(inner * 2, inner * 2)), start + sweep, -sweep, false)
        close()
    }
}

@Composable
private fun CategoryPanel(items: List<StockItem>, days: Int, query: String, category: String, select: (String) -> Unit,
    attention: Boolean, toggle: (Boolean) -> Unit, order: RingOrder, sort: (RingOrder) -> Unit, modifier: Modifier, add: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    var expanded by remember { mutableStateOf(false) }
    val searched = remember(items, query) { items.filter { it.name.contains(query.trim(), true) } }
    Column(modifier.background(colors.surface, RoundedCornerShape(14.dp)).border(1.dp, colors.outlineVariant, RoundedCornerShape(14.dp)).padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("分类", fontSize = 12.sp, lineHeight = 17.sp)
        listOf("全部", "食品", "日用品", "其他").forEach { label ->
            val count = searched.count { (label == "全部" || it.category == label) && (!attention || it.status(days).attention) }
            Row(Modifier.fillMaxWidth().height(24.dp).clip(RoundedCornerShape(7.dp))
                .background(if (category == label) colors.primary else colors.surface)
                .border(1.dp, if (category == label) colors.primary else colors.outlineVariant, RoundedCornerShape(7.dp))
                .testTag("ring-category-$label").semantics { selected = category == label; contentDescription = "$label，$count 件" }
                .clickable { select(label) }.padding(horizontal = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(label, fontSize = 10.sp, lineHeight = 14.sp, color = if (category == label) colors.onPrimary else colors.onSurface, modifier = Modifier.weight(1f))
                Text(count.toString(), fontSize = 10.sp, lineHeight = 14.sp, color = if (category == label) colors.onPrimary else colors.onSurfaceVariant)
            }
        }
        HorizontalDivider(color = colors.outlineVariant, modifier = Modifier.padding(vertical = 2.dp))
        Row(Modifier.fillMaxWidth().height(27.dp).testTag("ring-attention").semantics { toggleableState = if (attention) androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off }
            .clickable { toggle(!attention) }, verticalAlignment = Alignment.CenterVertically) {
            Text(if (attention) "☑" else "□", fontSize = 13.sp, color = colors.primary)
            Text("需关注", fontSize = 10.sp, lineHeight = 14.sp, modifier = Modifier.weight(1f).padding(start = 3.dp))
            Text(searched.count { (category == "全部" || it.category == category) && it.status(days).attention }.toString(), fontSize = 10.sp, color = colors.onSurfaceVariant)
        }
        Box {
            Text("${order.title} ⌄", fontSize = 10.sp, lineHeight = 14.sp,
                modifier = Modifier.fillMaxWidth().height(26.dp).testTag("ring-order").clickable { expanded = true }.padding(top = 5.dp))
            DropdownMenu(expanded, { expanded = false }) { RingOrder.entries.forEach { option -> DropdownMenuItem(text = { Text(option.title) }, onClick = { sort(option); expanded = false }) } }
        }
        if (items.isEmpty()) Text("＋ 添加物品", fontSize = 10.sp, lineHeight = 17.sp, color = colors.primary,
            modifier = Modifier.fillMaxWidth().height(28.dp).testTag("ring-add-inside").clickable(onClick = add).padding(top = 5.dp))
    }
}
