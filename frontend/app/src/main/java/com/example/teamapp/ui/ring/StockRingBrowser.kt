package com.example.teamapp.ui.ring

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.asAndroidPath
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.layout.onSizeChanged
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

    val screenHeight = LocalConfiguration.current.screenHeightDp.dp
    val palette = remember(light) { RingPalette(light) }
    var infoHeightPx by remember { mutableIntStateOf(0) }
    var seekHeightPx by remember { mutableIntStateOf(0) }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.padding(horizontal = 18.dp).fillMaxWidth().height(28.dp)
            .background(palette.panel, RoundedCornerShape(18.dp)).border(1.dp, palette.line, RoundedCornerShape(18.dp)).padding(horizontal = 10.dp),
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
            val viewportHeight = (screenHeight - 205.dp).coerceIn(maxWidth * 1.08f, maxWidth * 1.5f)
            val widthPx = constraints.maxWidth.toFloat()
            val heightPx = with(androidx.compose.ui.platform.LocalDensity.current) { viewportHeight.toPx() }
            val center = Offset(widthPx * 1.07f, heightPx * .46f)
            val radius = widthPx * .75f
            val thickness = widthPx * .28f
            val inner = radius - thickness / 2f
            val outer = radius + thickness / 2f
            val visibleIndices = RingMath.visible(displayPosition, displayed.size)
            // Each card owns its animation. Its path, badge, icon and text share this transform.
            val elevations = visibleIndices.associateWith { index ->
                key(index) { animateFloatAsState(if (index == currentIndex) 1f else 0f, tween(180), label = "ring-pop-$index").value }
            }
            val density = androidx.compose.ui.platform.LocalDensity.current
            val popPx = with(density) { 12.dp.toPx() }
            val orderedIndices = visibleIndices.sortedBy { elevations.getValue(it) }

            Box(Modifier.fillMaxWidth().height(viewportHeight).clip(RoundedCornerShape(0.dp))
                .pointerInput(displayed.map { it.id }, widthPx, heightPx) {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        if (displayed.isEmpty()) return@awaitEachGesture
                        // Overlay controls own their gestures where the ring passes behind them.
                        val inset = with(density) { 16.dp.toPx() }
                        val overInfo = down.position.x <= inset + widthPx * .55f && down.position.y >= heightPx - infoHeightPx - inset
                        val overSeek = down.position.x >= widthPx - inset - widthPx * .34f && down.position.y >= heightPx - seekHeightPx - inset
                        if (overInfo || overSeek) return@awaitEachGesture
                        val distance = (down.position - center).getDistance()
                        if (distance !in (inner - popPx * 2)..(outer + popPx * 2)) return@awaitEachGesture
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
                            val relative = RingMath.deltaDegrees(RingMath.SELECTION_ANGLE, angle)
                            val target = (position.value + relative / RingMath.STEP).roundToInt()
                            if (abs(relative) <= 80f && target in displayed.indices) settle(target.toFloat())
                        }
                    }
                }) {
                Canvas(Modifier.fillMaxSize()) {
                    drawPath(sector(center, inner, outer, RingMath.SELECTION_ANGLE - 86f, 172f), palette.track)
                    val guideRadius = inner - 13.dp.toPx()
                    val guideBounds = Offset(center.x - guideRadius, center.y - guideRadius)
                    val guideSize = Size(guideRadius * 2, guideRadius * 2)
                    // A quiet continuous rail with rounded ends follows the inner contour.
                    drawArc(palette.line, RingMath.SELECTION_ANGLE - 83f, 166f, false,
                        guideBounds, guideSize, style = Stroke(1.2.dp.toPx(), cap = StrokeCap.Round))
                    if (displayed.isNotEmpty()) {
                        drawArc(palette.accent.copy(alpha = .10f), RingMath.SELECTION_ANGLE - 7f, 14f, false,
                            guideBounds, guideSize, style = Stroke(6.dp.toPx(), cap = StrokeCap.Round))
                        drawArc(palette.accent, RingMath.SELECTION_ANGLE - 7f, 14f, false,
                            guideBounds, guideSize, style = Stroke(2.4.dp.toPx(), cap = StrokeCap.Round))
                    }
                    orderedIndices.forEach { index ->
                        val delta = (index - displayPosition) * RingMath.STEP
                        if (abs(delta) <= 84f) {
                            val status = displayed[index].status(reminderDays)
                            val amount = elevations.getValue(index)
                            val radians = RingMath.angle(index, displayPosition) * PI.toFloat() / 180f
                            val pivot = center + Offset(radius * cos(radians), radius * sin(radians))
                            val path = sector(center, inner, outer, RingMath.angle(index, displayPosition) - RingMath.SWEEP / 2f,
                                RingMath.SWEEP, .45.dp.toPx(), 2.4.dp.toPx())
                            withTransform({
                                translate(cos(radians) * popPx * amount, sin(radians) * popPx * amount)
                                scale(1f + .12f * amount, 1f + .12f * amount, pivot)
                            }) {
                                if (amount > .01f) drawIntoCanvas { canvas ->
                                    val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                                        color = android.graphics.Color.TRANSPARENT
                                        setShadowLayer(7.dp.toPx() * amount, 0f, 4.dp.toPx() * amount,
                                            android.graphics.Color.argb(((if (light) 45 else 95) * amount).toInt(), 0, 0, 0))
                                    }
                                    canvas.nativeCanvas.drawPath(path.asAndroidPath(), paint)
                                }
                                drawPath(path, palette.fills[status.priority])
                                drawPath(path, androidx.compose.ui.graphics.lerp(palette.seam, palette.edge, amount), style = Stroke((.5f + 3.1f * amount).dp.toPx()))
                            }
                        }
                    }
                }
                orderedIndices.forEach { index ->
                    val delta = (index - displayPosition) * RingMath.STEP
                    if (abs(delta) <= 79f) {
                        val item = displayed[index]
                        val angle = RingMath.angle(index, displayPosition) * PI.toFloat() / 180f
                        val amount = elevations.getValue(index)
                        val boxWidth = viewportWidth * .21f
                        val boxHeight = viewportWidth * .255f
                        val contentRadius = radius - widthPx * .025f
                        val pivot = center + Offset(radius * cos(angle), radius * sin(angle))
                        val contentCenter = center + Offset(contentRadius * cos(angle), contentRadius * sin(angle))
                        val labelCenter = pivot + (contentCenter - pivot) * (1f + .12f * amount) + Offset(cos(angle), sin(angle)) * popPx * amount
                        Column(Modifier.offset { IntOffset((labelCenter.x - widthPx * .21f / 2f).roundToInt(), (labelCenter.y - widthPx * .255f / 2f).roundToInt()) }
                            .size(boxWidth, boxHeight).testTag("ring-card-${item.id}")
                            .semantics { contentDescription = "圆环物品：${item.name}"; this.selected = index == currentIndex }
                            .graphicsLayer { rotationZ = RingMath.SELECTION_ANGLE - 180f + delta; scaleX = 1f + .12f * amount; scaleY = 1f + .12f * amount }
                            .clickable { focus.clearFocus(); settle(index.toFloat()) },
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            RingItemIllustration(item, Modifier.size(27.dp))
                            Text(item.name, fontSize = 11.sp, lineHeight = 14.sp, color = palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(top = 5.dp))
                            Text("${item.quantity.display()} ${item.unit}", fontSize = 11.sp, lineHeight = 14.sp, color = palette.ink, maxLines = 1)
                        }
                        val badgeRadius = radius + thickness * .34f
                        val badgeCenter = pivot + Offset((badgeRadius - radius) * cos(angle), (badgeRadius - radius) * sin(angle)) * (1f + .12f * amount) + Offset(cos(angle), sin(angle)) * popPx * amount
                        Box(Modifier.offset { IntOffset((badgeCenter.x - with(density) { 16.dp.toPx() } / 2f).roundToInt(), (badgeCenter.y - with(density) { 48.dp.toPx() } / 2f).roundToInt()) }
                            .size(16.dp, 48.dp).graphicsLayer { rotationZ = RingMath.SELECTION_ANGLE - 180f + delta; scaleX = 1f + .12f * amount; scaleY = 1f + .12f * amount }
                            .background(palette.badge, RoundedCornerShape(2.dp)).padding(vertical = 3.dp), contentAlignment = Alignment.Center) {
                            val status = item.status(reminderDays)
                            val badgeText = when {
                                status.expired -> "已\n过\n期"
                                status.days == 0L -> "今\n天"
                                status.days != null && status.days < 100 -> "${status.days}\n天"
                                status.low -> "需\n补"
                                else -> "正\n常"
                            }
                            Text(badgeText, fontSize = 8.sp, lineHeight = 11.sp, color = palette.badgeInk, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                        }
                    }
                }
                CategoryPanel(items, reminderDays, query, category, { category = it; focus.clearFocus() }, attention, { attention = it }, order, { order = it },
                    Modifier.align(Alignment.CenterEnd).padding(end = 12.dp, bottom = viewportHeight * .08f).width(maxOf(92.dp, viewportWidth * .25f)), onAdd, palette)

                // The card and navigation sit in the lower empty area, as in the design reference.
                if (infoItem != null) {
                    RingInfoCard(infoItem, reminderDays, !interacting, { onOpenItem(infoItem) }, palette,
                        Modifier.align(Alignment.BottomStart).padding(start = 16.dp, bottom = 13.dp).width(viewportWidth * .55f).onSizeChanged { infoHeightPx = it.height })
                } else {
                    Column(Modifier.align(Alignment.BottomStart).padding(start = 16.dp, bottom = 13.dp).width(viewportWidth * .46f)
                        .onSizeChanged { infoHeightPx = it.height }
                        .background(palette.panel, RoundedCornerShape(14.dp)).border(1.dp, palette.line, RoundedCornerShape(14.dp)).padding(12.dp)) {
                        Text(if (items.isEmpty()) "家里的小物，慢慢记好" else "没有找到匹配的物品", fontSize = 13.sp, lineHeight = 19.sp, color = palette.ink)
                        Text(if (items.isEmpty()) "添加第一件物品，开始整理库存。" else "试试清空搜索或分类筛选。", fontSize = 10.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant, modifier = Modifier.padding(top = 5.dp))
                        TextButton(onClick = { if (items.isEmpty()) onAdd() else { query = ""; category = "全部"; attention = false; focus.clearFocus() } },
                            contentPadding = PaddingValues(0.dp), modifier = Modifier.testTag("ring-empty-action")) { Text(if (items.isEmpty()) "＋ 添加物品" else "清空搜索和筛选", fontSize = 11.sp) }
                    }
                }
                Column(Modifier.align(Alignment.BottomEnd).padding(end = 16.dp, bottom = 10.dp).width(viewportWidth * .34f).onSizeChanged { seekHeightPx = it.height }, horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        RingStepButton("‹", currentIndex > 0, "ring-previous", palette) { settle((currentIndex - 1).toFloat()) }
                        Text("${if (currentIndex < 0) 0 else currentIndex + 1} / ${displayed.size}", fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant,
                            modifier = Modifier.testTag("ring-position").semantics { contentDescription = "当前位置 ${if (currentIndex < 0) 0 else currentIndex + 1}，结果总数 ${displayed.size}" })
                        RingStepButton("›", currentIndex >= 0 && currentIndex < displayed.lastIndex, "ring-next", palette) { settle((currentIndex + 1).toFloat()) }
                    }
                    if (displayed.size > 1) {
                        Slider(value = displayPosition.coerceIn(0f, displayed.lastIndex.toFloat()), onValueChange = {
                            motion?.cancel(); interacting = true; seeking = true; dragPosition = it; focus.clearFocus()
                        }, onValueChangeFinished = { settle(dragPosition ?: position.value, immediate = true) }, valueRange = 0f..displayed.lastIndex.toFloat(),
                            colors = SliderDefaults.colors(thumbColor = palette.accent, activeTrackColor = palette.accent, inactiveTrackColor = palette.track),
                            thumb = { Box(Modifier.size(12.dp).background(palette.accent, androidx.compose.foundation.shape.CircleShape).border(1.5.dp, palette.panel, androidx.compose.foundation.shape.CircleShape)) },
                            track = { state -> SliderDefaults.Track(state, modifier = Modifier.height(3.dp)) },
                            modifier = Modifier.fillMaxWidth().height(28.dp).testTag("ring-seek"))
                        Text(if (seeking) "定位至：${displayed[currentIndex].name}" else "滑动圆环 · 拖动定位", fontSize = 9.sp, lineHeight = 13.sp, maxLines = 2,
                            overflow = TextOverflow.Ellipsis, color = scheme.onSurfaceVariant, modifier = Modifier.testTag("ring-seek-label"))
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(bottom = 3.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            listOf("已过期", "临期", "库存不足", "正常").forEachIndexed { index, label ->
                Box(Modifier.padding(start = if (index == 0) 0.dp else 10.dp, end = 4.dp).size(5.dp).background(palette.fills[index], androidx.compose.foundation.shape.CircleShape))
                Text(label, fontSize = 9.sp, lineHeight = 13.sp, color = scheme.onSurfaceVariant)
            }
        }
    }
}

private class RingPalette(light: Boolean) {
    val fills = if (light) listOf(Color(0xFFD98F85), Color(0xFFE7B580), Color(0xFFC4CEAC), Color(0xFFD7DCC8))
        else listOf(Color(0xFF58494D), Color(0xFF575346), Color(0xFF444A3F), Color(0xFF353D37))
    val panel = if (light) Color(0xFFF4F2DE) else Color(0xFF242528)
    val line = if (light) Color(0xFFD8DFC1) else Color(0xFF3D3F42)
    val track = if (light) Color(0xFFE8ECD9) else Color(0xFF2B2D2B)
    val edge = if (light) Color(0xFFFFFFF3) else Color(0xFFD2D8C6)
    val seam = if (light) Color(0xFFFFFFF3) else Color(0xFF686C60)
    val ink = if (light) Color(0xFF38452E) else Color(0xFFEBEBDF)
    val accent = if (light) Color(0xFF657F46) else Color(0xFFA1AD91)
    val badge = if (light) Color(0xFF838466) else Color(0xFFA4AD95)
    val badgeInk = if (light) Color(0xFFFFFFF1) else Color(0xFF30392B)
}

@Composable
private fun RingStepButton(label: String, enabled: Boolean, tag: String, palette: RingPalette, action: () -> Unit) {
    TextButton(onClick = action, enabled = enabled, contentPadding = PaddingValues(0.dp),
        modifier = Modifier.size(30.dp).testTag(tag),
        colors = ButtonDefaults.textButtonColors(containerColor = palette.panel, contentColor = palette.accent, disabledContainerColor = palette.panel.copy(alpha = .65f)),
        shape = androidx.compose.foundation.shape.CircleShape) { Text(label, fontSize = 21.sp, lineHeight = 24.sp) }
}

@Composable
private fun RingInfoCard(item: StockItem, days: Int, enabled: Boolean, open: () -> Unit, palette: RingPalette, modifier: Modifier) {
    val scheme = MaterialTheme.colorScheme
    val status = item.status(days)
    val statusText = buildString {
        append(status.label)
        when { status.expired -> append(" ${-(status.days ?: 0)} 天"); status.soon -> append(" · 剩 ${status.days} 天") }
        if (status.low) append(" · 缺 ${(item.minimum - item.quantity).display()} ${item.unit}")
    }
    val statusInk = when {
        status.expired -> scheme.error
        status.soon -> if (LocalLightDesign.current) Color(0xFFAB743F) else Color(0xFFD5BC85)
        else -> palette.accent
    }
    Card(onClick = open, enabled = enabled,
        modifier = modifier.testTag("ring-selected-info").semantics { contentDescription = "已选中物品：${item.name}" }, shape = RoundedCornerShape(18.dp),
        border = BorderStroke(1.dp, palette.line), colors = CardDefaults.cardColors(containerColor = palette.panel)) {
        Column(Modifier.heightIn(min = 210.dp).padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text("${item.category} · ${item.location}", fontSize = 12.sp, lineHeight = 18.sp, color = scheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(item.name, fontSize = 20.sp, lineHeight = 26.sp, color = palette.ink, fontWeight = FontWeight.SemiBold,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text("${item.quantity.display()} ${item.unit}", fontSize = 17.sp, lineHeight = 23.sp, color = palette.accent, fontWeight = FontWeight.Medium)
            Text(statusText, fontSize = 13.sp, lineHeight = 19.sp, color = statusInk, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.weight(1f))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text("有效期 ${item.expiry.ifBlank { "未设置" }}", fontSize = 12.sp, lineHeight = 18.sp, color = scheme.onSurfaceVariant)
                    if (item.minimum > 0) Text("最低库存 ${item.minimum.display()} ${item.unit}", fontSize = 12.sp, lineHeight = 18.sp, color = scheme.onSurfaceVariant)
                }
                RingItemIllustration(item, Modifier.size(52.dp).testTag("ring-info-icon"))
            }
        }
    }
}

private fun sector(center: Offset, inner: Float, outer: Float, start: Float, sweep: Float, tooth: Float = 0f, pitch: Float = 1f): Path {
    val radians = start * PI.toFloat() / 180f
    return Path().apply {
        fun edge(from: Float, to: Float, angle: Float) {
            val direction = Offset(cos(angle), sin(angle))
            val normal = Offset(-sin(angle), cos(angle))
            val steps = (abs(to - from) / pitch).roundToInt().coerceAtLeast(2)
            for (step in 1..steps) {
                val distance = from + (to - from) * step / steps
                val notch = if (step == steps) 0f else if (step % 2 == 0) tooth else -tooth
                val point = center + direction * distance + normal * notch
                lineTo(point.x, point.y)
            }
        }
        moveTo(center.x + outer * cos(radians), center.y + outer * sin(radians))
        arcTo(androidx.compose.ui.geometry.Rect(center - Offset(outer, outer), Size(outer * 2, outer * 2)), start, sweep, false)
        val end = (start + sweep) * PI.toFloat() / 180f
        if (tooth > 0f) edge(outer, inner, end) else lineTo(center.x + inner * cos(end), center.y + inner * sin(end))
        arcTo(androidx.compose.ui.geometry.Rect(center - Offset(inner, inner), Size(inner * 2, inner * 2)), start + sweep, -sweep, false)
        if (tooth > 0f) edge(inner, outer, radians)
        close()
    }
}

@Composable
private fun CategoryPanel(items: List<StockItem>, days: Int, query: String, category: String, select: (String) -> Unit,
    attention: Boolean, toggle: (Boolean) -> Unit, order: RingOrder, sort: (RingOrder) -> Unit, modifier: Modifier, add: () -> Unit, palette: RingPalette) {
    val colors = MaterialTheme.colorScheme
    var expanded by remember { mutableStateOf(false) }
    val searched = remember(items, query) { items.filter { it.name.contains(query.trim(), true) } }
    Column(modifier.background(palette.panel, RoundedCornerShape(15.dp)).border(1.dp, palette.line, RoundedCornerShape(15.dp)).padding(9.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("分类", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, lineHeight = 18.sp, modifier = Modifier.padding(bottom = 3.dp))
        listOf("全部", "食品", "日用品", "其他").forEach { label ->
            val count = searched.count { (label == "全部" || it.category == label) && (!attention || it.status(days).attention) }
            Row(Modifier.fillMaxWidth().height(24.dp).clip(RoundedCornerShape(7.dp))
                .background(if (category == label) palette.accent else palette.panel)
                .border(1.dp, if (category == label) palette.accent else palette.line, RoundedCornerShape(7.dp))
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
