package com.example.teamapp.ui.ring

import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.R
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.spring
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
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
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.*
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.AppMotionContent
import com.example.teamapp.ui.motionClickable
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
    onSelectedItem: (StockItem?) -> Unit = {},
    showAddAction: Boolean = false,
    toolbarEndPadding: Dp = 18.dp
) {
    val strings = rememberUiStrings()
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
    val resultAlpha = remember { Animatable(1f) }
    var dragPosition by remember { mutableStateOf<Float?>(null) }
    var seeking by remember { mutableStateOf(false) }
    var motion by remember { mutableStateOf<Job?>(null) }
    var motionTarget by remember { mutableStateOf<Int?>(null) }
    val coroutineScope = rememberCoroutineScope()
    val selected = displayed.firstOrNull { it.id == selectedId }
    // Position is read by drawing/placement, so each animation frame does not recompose the browser.
    val displayPosition = remember { { dragPosition ?: position.value } }
    val currentIndex by remember { derivedStateOf { RingMath.index(displayPosition(), displayed.size) } }
    val visibleIndices by remember { derivedStateOf { RingMath.visible(displayPosition(), displayed.size) } }
    val statuses = remember(displayed, reminderDays) { displayed.map { it.status(reminderDays) } }
    val infoItem = if (interacting) displayed.getOrNull(currentIndex) else selected
    val selectedCallback by rememberUpdatedState(onSelectedItem)
    val navigationIndex = motionTarget ?: currentIndex

    // Freeze ordering during a gesture/animation. Reconcile by ID when the motion finishes.
    LaunchedEffect(incoming, scopeKey, interacting) {
        if (interacting) {
            resultAlpha.animateTo(1f, tween(AppMotion.Quick, easing = AppMotion.easing))
        } else {
            val ids = incoming.map { it.id }
            val reordered = displayed.map { it.id } != ids
            if (reordered && displayed.isNotEmpty()) {
                resultAlpha.animateTo(0f, tween(80, easing = AppMotion.easing))
            }
            selectedId = RingMath.selection(previousIds, ids, selectedId, previousScope != scopeKey)
            displayed = incoming
            previousIds = ids
            previousScope = scopeKey
            motionTarget = null
            position.snapTo(ids.indexOf(selectedId).coerceAtLeast(0).toFloat())
            selectedCallback(incoming.firstOrNull { it.id == selectedId })
            resultAlpha.animateTo(1f, tween(AppMotion.Quick, easing = AppMotion.easing))
        }
    }

    fun settle(value: Float) {
        val start = displayPosition()
        motion?.cancel()
        if (displayed.isEmpty()) { interacting = false; dragPosition = null; seeking = false; motionTarget = null; return }
        val target = RingMath.index(value, displayed.size)
        interacting = true
        motionTarget = target
        motion = coroutineScope.launch {
            // A tap supplies the destination, not the starting frame. Preserve interrupted motion.
            position.snapTo(start)
            dragPosition = null
            seeking = false
            position.animateTo(target.toFloat(), spring(dampingRatio = .92f, stiffness = 420f))
            selectedId = displayed[target].id
            selectedCallback(displayed[target])
            motionTarget = null
            interacting = false
        }
    }

    val view = androidx.compose.ui.platform.LocalView.current
    var windowHeight by remember(view) { mutableIntStateOf(view.rootView.height) }
    DisposableEffect(view) {
        val listener = android.view.ViewTreeObserver.OnGlobalLayoutListener { windowHeight = view.rootView.height }
        view.viewTreeObserver.addOnGlobalLayoutListener(listener)
        onDispose { view.viewTreeObserver.removeOnGlobalLayoutListener(listener) }
    }
    val screenHeight = with(androidx.compose.ui.platform.LocalDensity.current) { windowHeight.coerceAtLeast(1).toDp() }
    val palette = remember(light) { RingPalette(if (light) 1f else 0f) }
    var infoHeightPx by remember { mutableIntStateOf(0) }
    var seekHeightPx by remember { mutableIntStateOf(0) }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = toolbarEndPadding)
            .height(if (showAddAction) 48.dp else 28.dp).testTag("ring-toolbar"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.weight(1f).height(28.dp)
                .background(palette.panel, RoundedCornerShape(18.dp)).border(1.dp, palette.line, RoundedCornerShape(18.dp)).padding(horizontal = 10.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                DesignGlyph("search", Modifier.size(15.dp), scheme.onSurfaceVariant)
                BasicTextField(query, { query = it }, singleLine = true, textStyle = TextStyle(color = scheme.onSurface, fontSize = 12.sp),
                    modifier = Modifier.weight(1f).testTag("ring-search").semantics { contentDescription = strings.get(R.string.ui_search_item_names) },
                    decorationBox = { field -> Box { if (query.isEmpty()) Text(strings.get(R.string.ui_search_items), fontSize = 12.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant); field() } })
                if (query.isNotEmpty()) Text(strings.get(R.string.ui_clear), fontSize = 11.sp, color = scheme.primary,
                    modifier = Modifier.motionClickable { query = ""; focus.clearFocus() }.padding(3.dp))
            }
            if (showAddAction) IconButton(onClick = { focus.clearFocus(); onAdd() },
                modifier = Modifier.size(48.dp).testTag("ring-add").semantics { contentDescription = strings.get(R.string.ui_add_items) }) {
                Box(Modifier.size(30.dp).background(scheme.primaryContainer, CircleShape), contentAlignment = Alignment.Center) {
                    DesignGlyph("plus", Modifier.size(17.dp), scheme.onPrimaryContainer)
                }
            }
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
            // Each card owns its animation. Its path, badge, icon and text share this transform.
            val elevations = visibleIndices.associateWith { index ->
                key(displayed[index].id) { animateFloatAsState(if (index == currentIndex) 1f else 0f,
                    tween(AppMotion.Quick, easing = AppMotion.easing), label = "ring-pop-$index") }
            }
            val density = androidx.compose.ui.platform.LocalDensity.current
            val popPx = with(density) { 12.dp.toPx() }
            val orderedIndices = visibleIndices.sortedBy { it == currentIndex }
            val trackPath = remember(center, inner, outer) {
                sector(center, inner, outer, RingMath.SELECTION_ANGLE - 86f, 172f)
            }
            // Every card has identical geometry. Rotate a cached path instead of rebuilding its teeth.
            val cardPath = remember(center, inner, outer, density) {
                with(density) { sector(center, inner, outer, RingMath.SELECTION_ANGLE - RingMath.SWEEP / 2f,
                    RingMath.SWEEP, .45.dp.toPx(), 2.4.dp.toPx()) }
            }
            val shadowPaint = remember { android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                color = android.graphics.Color.TRANSPARENT
            } }

            Box(Modifier.fillMaxWidth().height(viewportHeight).clip(RoundedCornerShape(0.dp))
                .ringAccents(palette)
                .pointerInput(displayed.map { it.id }, widthPx, heightPx) {
                    awaitEachGesture {
                        // Inspect Initial before child clickables consume their down event, while
                        // respecting the parent motionInput blocker on an outgoing page.
                        val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                        if (down.isConsumed) return@awaitEachGesture
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
                        var tapConsumed = false
                        var blocked = false
                        try {
                            do {
                                val event = awaitPointerEvent(PointerEventPass.Initial)
                                val change = event.changes.firstOrNull { it.id == down.id } ?: break
                                if (change.isConsumed) { blocked = true; break }
                                if (!change.pressed) {
                                    released = true
                                    if (!started) {
                                        // Let a card own its tap; the uncovered arc also accepts taps.
                                        val main = awaitPointerEvent(PointerEventPass.Main)
                                        tapConsumed = main.changes.firstOrNull { it.id == down.id }?.isConsumed == true
                                    }
                                    break
                                }
                                if (!started && (change.position - down.position).getDistance() > viewConfiguration.touchSlop) {
                                    started = true
                                    focus.clearFocus()
                                    motion?.cancel()
                                    motionTarget = null
                                    interacting = true
                                    dragPosition = displayPosition()
                                }
                                if (started) {
                                    val angle = atan2(change.position.y - center.y, change.position.x - center.x) * 180f / PI.toFloat()
                                    dragPosition = RingMath.drag(dragPosition ?: position.value, RingMath.deltaDegrees(lastAngle, angle), displayed.size)
                                    change.consume()
                                    lastAngle = angle
                                }
                            } while (true)
                        } finally {
                            if (started) {
                                if (blocked) { dragPosition = null; seeking = false; interacting = false }
                                else settle(dragPosition ?: position.value)
                            }
                        }
                        // Card labels handle taps. The background also accepts taps on the arc.
                        if (!started && released && !tapConsumed) {
                            val angle = atan2(down.position.y - center.y, down.position.x - center.x) * 180f / PI.toFloat()
                            val relative = RingMath.deltaDegrees(RingMath.SELECTION_ANGLE, angle)
                            val target = (displayPosition() + relative / RingMath.STEP).roundToInt()
                            if (abs(relative) <= 80f && target in displayed.indices) settle(target.toFloat())
                        }
                    }
                }) {
                Canvas(Modifier.fillMaxSize().graphicsLayer { alpha = resultAlpha.value }) {
                    val framePosition = displayPosition()
                    drawPath(trackPath, palette.track)
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
                        val delta = (index - framePosition) * RingMath.STEP
                        if (delta in RingMath.MIN_VISIBLE_DELTA..RingMath.MAX_VISIBLE_DELTA) {
                            val status = statuses[index]
                            val amount = elevations.getValue(index).value
                            val radians = RingMath.angle(index, framePosition) * PI.toFloat() / 180f
                            val pivot = center + Offset(radius * cos(radians), radius * sin(radians))
                            withTransform({
                                translate(cos(radians) * popPx * amount, sin(radians) * popPx * amount)
                                scale(1f + .12f * amount, 1f + .12f * amount, pivot)
                                rotate(delta, center)
                            }) {
                                if (amount > .01f) drawIntoCanvas { canvas ->
                                    shadowPaint.setShadowLayer(7.dp.toPx() * amount, 0f, 4.dp.toPx() * amount,
                                        android.graphics.Color.argb(((if (light) 45 else 95) * amount).toInt(), 0, 0, 0))
                                    canvas.nativeCanvas.drawPath(cardPath.asAndroidPath(), shadowPaint)
                                }
                                drawPath(cardPath, palette.fills[status.priority])
                                drawPath(cardPath, androidx.compose.ui.graphics.lerp(palette.seam, palette.edge, amount), style = Stroke((.5f + 3.1f * amount).dp.toPx()))
                            }
                        }
                    }
                }
                orderedIndices.forEach { index ->
                    key(displayed[index].id) {
                        val item = displayed[index]
                        val elevation = elevations.getValue(index)
                        val boxWidth = viewportWidth * .235f
                        val boxHeight = viewportWidth * .30f
                        val contentRadius = radius - widthPx * .025f
                        Column(Modifier.offset {
                            val angle = RingMath.angle(index, displayPosition()) * PI.toFloat() / 180f
                            val amount = elevation.value
                            val contentDistance = radius + (contentRadius - radius) * (1f + .12f * amount) + popPx * amount
                            val labelCenter = center + Offset(cos(angle), sin(angle)) * contentDistance
                            IntOffset((labelCenter.x - widthPx * .235f / 2f).roundToInt(), (labelCenter.y - widthPx * .30f / 2f).roundToInt())
                        }
                            .size(boxWidth, boxHeight).testTag("ring-card-${item.id}")
                            .semantics { contentDescription = strings.get(R.string.ui_ring_item, item.name); this.selected = index == currentIndex }
                            .graphicsLayer {
                                rotationZ = RingMath.angle(index, displayPosition()) - 180f
                                scaleX = 1f + .12f * elevation.value; scaleY = scaleX; alpha = resultAlpha.value
                            }
                            .clickable { focus.clearFocus(); settle(index.toFloat()) },
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            RingItemIllustration(item, Modifier.size(32.dp))
                            Text(item.name, fontSize = 12.sp, lineHeight = 16.sp, color = palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(top = 5.dp))
                            Text("${item.quantity.display()} ${item.unit}", fontSize = 12.sp, lineHeight = 16.sp, color = palette.ink, maxLines = 1)
                        }
                        val badgeRadius = radius + thickness * .34f
                        Box(Modifier.offset {
                            val angle = RingMath.angle(index, displayPosition()) * PI.toFloat() / 180f
                            val amount = elevation.value
                            val badgeDistance = radius + (badgeRadius - radius) * (1f + .12f * amount) + popPx * amount
                            val badgeCenter = center + Offset(cos(angle), sin(angle)) * badgeDistance
                            IntOffset((badgeCenter.x - with(density) { 16.dp.toPx() } / 2f).roundToInt(), (badgeCenter.y - with(density) { 48.dp.toPx() } / 2f).roundToInt())
                        }
                            .size(16.dp, 48.dp).graphicsLayer {
                                rotationZ = RingMath.angle(index, displayPosition()) - 180f
                                scaleX = 1f + .12f * elevation.value; scaleY = scaleX; alpha = resultAlpha.value
                            }
                            .background(palette.badge, RoundedCornerShape(2.dp)).padding(vertical = 3.dp), contentAlignment = Alignment.Center) {
                            val status = statuses[index]
                            val badgeText = when {
                                status.expired -> if (strings.english) "E\nX\nP" else "已\n过\n期"
                                status.days == 0L -> if (strings.english) "T\nO\nD" else "今\n天"
                                status.days != null && status.days < 100 -> if (strings.english) "${status.days}\nd" else "${status.days}\n天"
                                status.low -> if (strings.english) "L\nO\nW" else "需\n补"
                                else -> if (strings.english) "O\nK" else "正\n常"
                            }
                            Text(badgeText, fontSize = 8.sp, lineHeight = 11.sp, color = palette.badgeInk, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                        }
                    }
                }
                CategoryPanel(items, reminderDays, query, category, { category = it; focus.clearFocus() }, attention, { attention = it }, order, { order = it },
                    Modifier.align(Alignment.CenterEnd).padding(end = 12.dp, bottom = viewportHeight * .08f).width(maxOf(92.dp, viewportWidth * .25f)), onAdd, palette)

                // The card and navigation sit in the lower empty area, as in the design reference.
                AppMotionContent(infoItem, label = "ring-selection",
                    // A fast seek updates one preview instead of composing an exit for every item.
                    contentKey = { if (interacting) "ring-preview" else it?.id },
                    modifier = Modifier.align(Alignment.BottomStart).padding(start = 16.dp, bottom = 13.dp)
                        .width(viewportWidth * .55f).onSizeChanged { infoHeightPx = it.height }) { cardItem ->
                    if (cardItem != null) {
                        RingInfoCard(cardItem, reminderDays, !interacting, { onOpenItem(cardItem) }, palette, Modifier.fillMaxWidth())
                    } else {
                        Column(Modifier.fillMaxWidth()
                            .background(palette.detailPanel, RoundedCornerShape(14.dp)).border(1.dp, palette.detailLine, RoundedCornerShape(14.dp)).padding(12.dp)) {
                            Text(if (items.isEmpty()) strings.get(R.string.ui_every_little_thing__remembered_2) else strings.get(R.string.ui_no_matching_items_2), fontSize = 13.sp, lineHeight = 19.sp, color = palette.ink)
                            Text(if (items.isEmpty()) strings.get(R.string.ui_add_your_first_item_to_start) else strings.get(R.string.ui_try_clearing_the_search_or_category), fontSize = 10.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant, modifier = Modifier.padding(top = 5.dp))
                            TextButton(onClick = { if (items.isEmpty()) onAdd() else { query = ""; category = "全部"; attention = false; focus.clearFocus() } },
                                contentPadding = PaddingValues(0.dp), modifier = Modifier.testTag("ring-empty-action")) { Text(if (items.isEmpty()) strings.get(R.string.ui___add_item) else strings.get(R.string.ui_clear_search_and_filters), fontSize = 11.sp) }
                        }
                    }
                }
                Column(Modifier.align(Alignment.BottomEnd).padding(end = 16.dp, bottom = 10.dp).width(viewportWidth * .34f).onSizeChanged { seekHeightPx = it.height }, horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        RingStepButton("‹", navigationIndex > 0, "ring-previous", palette) { settle(((motionTarget ?: currentIndex) - 1).toFloat()) }
                        Text("${if (currentIndex < 0) 0 else currentIndex + 1} / ${displayed.size}", fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant,
                            modifier = Modifier.testTag("ring-position").semantics { contentDescription = strings.get(R.string.ui_position_of, if (currentIndex < 0) 0 else currentIndex + 1, displayed.size) })
                        RingStepButton("›", navigationIndex >= 0 && navigationIndex < displayed.lastIndex, "ring-next", palette) { settle(((motionTarget ?: currentIndex) + 1).toFloat()) }
                    }
                    if (displayed.size > 1) {
                        RingSeekSlider(displayPosition, displayed.lastIndex.toFloat(), palette, onValueChange = {
                            motion?.cancel(); motionTarget = null; interacting = true; seeking = true; dragPosition = it; focus.clearFocus()
                        }, onValueChangeFinished = { settle(displayPosition()) })
                        Text(if (seeking) strings.get(R.string.ui_go_to, displayed[currentIndex].name) else strings.get(R.string.ui_swipe_to_browse___drag_to), fontSize = 9.sp, lineHeight = 13.sp, maxLines = 2,
                            overflow = TextOverflow.Ellipsis, color = scheme.onSurfaceVariant, modifier = Modifier.testTag("ring-seek-label"))
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(bottom = 3.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            listOf("已过期", "临期", "库存不足", "正常").forEachIndexed { index, label ->
                Box(Modifier.padding(start = if (index == 0) 0.dp else 10.dp, end = 4.dp).size(5.dp).background(palette.fills[index], androidx.compose.foundation.shape.CircleShape))
                Text(strings.label(label), fontSize = 9.sp, lineHeight = 13.sp, color = scheme.onSurfaceVariant)
            }
        }
    }
}

/** Keep the slider's per-frame value read out of the ring's composition. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RingSeekSlider(position: () -> Float, lastIndex: Float, palette: RingPalette,
    onValueChange: (Float) -> Unit, onValueChangeFinished: () -> Unit) {
    Slider(value = position().coerceIn(0f, lastIndex), onValueChange = onValueChange,
        onValueChangeFinished = onValueChangeFinished, valueRange = 0f..lastIndex,
        colors = SliderDefaults.colors(thumbColor = palette.accent, activeTrackColor = palette.accent, inactiveTrackColor = palette.track),
        thumb = { Box(Modifier.size(12.dp).background(palette.accent, androidx.compose.foundation.shape.CircleShape)
            .border(1.5.dp, palette.panel, androidx.compose.foundation.shape.CircleShape)) },
        track = { state -> SliderDefaults.Track(state, modifier = Modifier.height(3.dp)) },
        modifier = Modifier.fillMaxWidth().height(28.dp).testTag("ring-seek"))
}

private class RingPalette(private val light: Float) {
    private fun color(dark: Long, pale: Long) = androidx.compose.ui.graphics.lerp(Color(dark), Color(pale), light)
    val fills = listOf(color(0xFF58494D, 0xFFD98F85), color(0xFF575346, 0xFFE7B580),
        color(0xFF444A3F, 0xFFC4CEAC), color(0xFF353D37, 0xFFD7DCC8))
    val panel = color(0xFF242528, 0xFFF4F2DE)
    val line = color(0xFF3D3F42, 0xFFD8DFC1)
    val detailPanel = panel.copy(alpha = .60f)
    val detailLine = line.copy(alpha = .75f)
    val track = color(0xFF2B2D2B, 0xFFE8ECD9)
    val edge = color(0xFFD2D8C6, 0xFFFFFFF3)
    val seam = color(0xFF686C60, 0xFFFFFFF3)
    val ink = color(0xFFEBEBDF, 0xFF38452E)
    val accent = color(0xFFA1AD91, 0xFF657F46)
    val leaf = accent.copy(alpha = .28f)
    val lightDot = color(0xFFB4A274, 0xFFE2C16B).copy(alpha = .5f)
    val badge = color(0xFFA4AD95, 0xFF838466)
    val badgeInk = color(0xFF30392B, 0xFFFFFFF1)
}

/** Two quiet accents stay in the empty margins and never participate in ring gestures. */
private fun Modifier.ringAccents(palette: RingPalette): Modifier = drawWithCache {
    val unit = 1.dp.toPx()
    val origin = Offset(18.dp.toPx(), 10.dp.toPx())
    val sprig = Path().apply {
        moveTo(5f, 29f)
        cubicTo(12f, 23f, 14f, 16f, 18f, 7f)
        moveTo(10f, 23f)
        cubicTo(1f, 21f, 0f, 13f, 1f, 10f)
        cubicTo(8f, 12f, 12f, 17f, 10f, 23f)
        moveTo(14f, 14f)
        cubicTo(14f, 6f, 22f, 1f, 28f, 2f)
        cubicTo(26f, 9f, 20f, 14f, 14f, 14f)
    }
    val sparkle = Path().apply {
        moveTo(0f, -3.5f)
        quadraticTo(.8f, -.8f, 3.5f, 0f)
        quadraticTo(.8f, .8f, 0f, 3.5f)
        quadraticTo(-.8f, .8f, -3.5f, 0f)
        quadraticTo(-.8f, -.8f, 0f, -3.5f)
        close()
    }
    onDrawBehind {
        withTransform({ translate(origin.x, origin.y); scale(unit, unit, Offset.Zero) }) {
            drawPath(sprig, palette.leaf, style = Stroke(.9f, cap = StrokeCap.Round))
        }
        withTransform({ translate(23f * unit, size.height - 6f * unit); scale(unit, unit, Offset.Zero) }) {
            drawPath(sparkle, palette.lightDot)
        }
        drawCircle(palette.leaf, 1.5.dp.toPx(), Offset(17.dp.toPx(), size.height - 3.dp.toPx()))
        drawCircle(palette.lightDot, 1.8.dp.toPx(), Offset(34.dp.toPx(), size.height - 5.dp.toPx()))
    }
}

@Composable
private fun RingStepButton(label: String, enabled: Boolean, tag: String, palette: RingPalette, action: () -> Unit) {
    val strings = rememberUiStrings()
    TextButton(onClick = action, enabled = enabled, contentPadding = PaddingValues(0.dp),
        modifier = Modifier.size(30.dp).testTag(tag),
        colors = ButtonDefaults.textButtonColors(containerColor = palette.panel, contentColor = palette.accent, disabledContainerColor = palette.panel.copy(alpha = .65f)),
        shape = androidx.compose.foundation.shape.CircleShape) { Text(strings.label(label), fontSize = 21.sp, lineHeight = 24.sp) }
}

@Composable
private fun RingInfoCard(item: StockItem, days: Int, enabled: Boolean, open: () -> Unit, palette: RingPalette, modifier: Modifier) {
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    val status = item.status(days)
    val statusText = buildString {
        append(if (status.expired) strings.get(R.string.ui_expired_3) else strings.label(status.label))
        when { status.expired -> append(" " + strings.days(-(status.days ?: 0))); status.soon -> append(strings.get(R.string.ui___day_s__left, if (strings.english) strings.days(status.days ?: 0) else status.days)) }
        if (status.low) append(strings.get(R.string.ui___short, (item.minimum - item.quantity).display(), item.unit))
    }
    Card(onClick = open, enabled = enabled,
        modifier = modifier.testTag("ring-selected-info").semantics { contentDescription = strings.get(R.string.ui_selected_item, item.name) }, shape = RoundedCornerShape(18.dp),
        border = BorderStroke(1.dp, palette.detailLine), colors = CardDefaults.cardColors(
            containerColor = palette.detailPanel, contentColor = palette.ink,
            disabledContainerColor = palette.detailPanel, disabledContentColor = palette.ink)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                // Give the title more room on narrow phones without shrinking its text.
                val compact = maxWidth < 160.dp
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Column(Modifier.weight(if (compact) .3f else .4f)) {
                        Text(strings.label(item.category), fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant)
                        Text(item.location, fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    Text(item.name, modifier = Modifier.weight(if (compact) .7f else .6f).testTag("ring-info-name"), fontSize = 18.sp, lineHeight = 23.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.End, color = palette.ink, fontWeight = FontWeight.SemiBold,
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            Text("${item.quantity.display()} ${item.unit}", fontSize = 15.sp, lineHeight = 20.sp, color = palette.accent, fontWeight = FontWeight.Medium)
            Text(statusText, fontSize = 12.sp, lineHeight = 17.sp, color = palette.accent, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(strings.get(R.string.ui_expires, item.expiry.ifBlank { "未设置" }), fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant)
                    if (item.minimum > 0) Text(strings.get(R.string.ui_minimum, item.minimum.display(), item.unit), fontSize = 11.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant)
                }
                RingItemIllustration(item, Modifier.size(44.dp).testTag("ring-info-icon"))
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
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    var expanded by remember { mutableStateOf(false) }
    val searched = remember(items, query) { items.filter { it.name.contains(query.trim(), true) } }
    Column(modifier.animateContentSize(tween(AppMotion.Duration, easing = AppMotion.easing))
        .background(palette.panel, RoundedCornerShape(15.dp)).border(1.dp, palette.line, RoundedCornerShape(15.dp)).padding(9.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(strings.get(R.string.ui_categories), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, lineHeight = 18.sp, modifier = Modifier.padding(bottom = 3.dp))
        listOf("全部", "食品", "日用品", "其他").forEach { label ->
            val count = searched.count { (label == "全部" || it.category == label) && (!attention || it.status(days).attention) }
            val background by animateColorAsState(if (category == label) palette.accent else palette.panel,
                tween(AppMotion.Quick, easing = AppMotion.easing), label = "ring-category-background")
            val border by animateColorAsState(if (category == label) palette.accent else palette.line,
                tween(AppMotion.Quick, easing = AppMotion.easing), label = "ring-category-border")
            val foreground by animateColorAsState(if (category == label) colors.onPrimary else colors.onSurface,
                tween(AppMotion.Quick, easing = AppMotion.easing), label = "ring-category-foreground")
            Row(Modifier.fillMaxWidth().height(24.dp).clip(RoundedCornerShape(7.dp))
                .background(background)
                .border(1.dp, border, RoundedCornerShape(7.dp))
                .testTag("ring-category-$label").semantics { selected = category == label; contentDescription = strings.get(R.string.ui___items, strings.label(label), count) }
                .motionClickable { select(label) }.padding(horizontal = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(strings.label(label), fontSize = 10.sp, lineHeight = 14.sp, color = foreground, modifier = Modifier.weight(1f))
                Text(count.toString(), fontSize = 10.sp, lineHeight = 14.sp, color = foreground)
            }
        }
        HorizontalDivider(color = colors.outlineVariant, modifier = Modifier.padding(vertical = 2.dp))
        Row(Modifier.fillMaxWidth().height(27.dp).testTag("ring-attention").semantics { toggleableState = if (attention) androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off }
            .motionClickable { toggle(!attention) }, verticalAlignment = Alignment.CenterVertically) {
            Text(if (attention) "☑" else "□", fontSize = 13.sp, color = colors.primary)
            Text(strings.get(R.string.ui_needs_attention), fontSize = 10.sp, lineHeight = 14.sp, modifier = Modifier.weight(1f).padding(start = 3.dp))
            Text(searched.count { (category == "全部" || it.category == category) && it.status(days).attention }.toString(), fontSize = 10.sp, color = colors.onSurfaceVariant)
        }
        Box {
            Text("${strings.label(order.title)} ⌄", fontSize = 10.sp, lineHeight = 14.sp,
                modifier = Modifier.fillMaxWidth().height(26.dp).testTag("ring-order").motionClickable { expanded = true }.padding(top = 5.dp))
            DropdownMenu(expanded, { expanded = false }) { RingOrder.entries.forEach { option -> DropdownMenuItem(text = { Text(strings.label(option.title)) }, onClick = { sort(option); expanded = false }) } }
        }
        if (items.isEmpty()) Text(strings.get(R.string.ui___add_item), fontSize = 10.sp, lineHeight = 17.sp, color = colors.primary,
            modifier = Modifier.fillMaxWidth().height(28.dp).testTag("ring-add-inside").motionClickable(onClick = add).padding(top = 5.dp))
    }
}
