package com.example.teamapp.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.changedToDownIgnoreConsumed
import androidx.compose.ui.input.pointer.util.VelocityTracker
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import kotlin.math.roundToInt
import kotlin.math.sqrt
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** A full-screen curtain sits above the entire scaffold, including its navigation bar. */
@Composable
internal fun AssistantPullLayer(
    tab: Int, available: Boolean, store: InventoryStore,
    conversation: SnapshotStateList<Pair<String, Boolean>>,
    snackbar: SnackbarHostState, notify: (String) -> Unit, content: @Composable (Modifier) -> Unit
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    var heightPx by remember { mutableIntStateOf(0) }
    var layerTop by remember { mutableFloatStateOf(0f) }
    var headerBottom by remember { mutableStateOf<Float?>(null) }
    val headerModifier = Modifier.zIndex(1f).shadow(14.dp, clip = false,
        ambientColor = Color.Black.copy(alpha = .65f), spotColor = Color.Black.copy(alpha = .85f))
        .testTag("app-top-bar")
        .onGloballyPositioned { headerBottom = it.boundsInWindow().bottom }
    val focus = LocalFocusManager.current
    fun dismiss() { focus.clearFocus(); expanded = false }
    // Keep the landing lift the same small physical distance on phones and tablets.
    val landingLiftPx = with(LocalDensity.current) { 7.dp.toPx() }
    val landingReveal = 1f - landingLiftPx / heightPx.coerceAtLeast(landingLiftPx.roundToInt())
    val transition = updateTransition(expanded, label = "assistant-curtain")
    val reveal = transition.animateFloat(
        transitionSpec = {
            if (targetState) keyframes {
                durationMillis = 720
                // Accelerate from release through landing, then settle with a quick, small bounce.
                0f at 0 using CubicBezierEasing(.42f, 0f, 1f, 1f)
                1f at 580 using CubicBezierEasing(.2f, 0f, .4f, 1f)
                // Present at least one complete landing frame before lifting for the bounce.
                1f at 596 using CubicBezierEasing(.2f, 0f, .4f, 1f)
                landingReveal at 640 using CubicBezierEasing(.2f, 0f, .3f, 1f)
                1f at 720
            } else tween(380, easing = AppMotion.easing)
        },
        label = "reveal"
    ) { if (it) 1f else 0f }
    val visible = transition.currentState || transition.targetState || transition.isRunning
    val cordRequested = tab in 1..3 && available && !visible && headerBottom != null
    val cordState = remember { MutableTransitionState(false) }
    cordState.targetState = cordRequested
    val cordTransition = rememberTransition(cordState, label = "assistant-cord-presence")
    val cordProgress = cordTransition.animateFloat(
        transitionSpec = {
            tween(if (targetState) 360 else 240,
                easing = if (targetState) LinearOutSlowInEasing else FastOutLinearInEasing)
        }, label = "cord-slide"
    ) { if (it) 1f else 0f }
    // Keep the physical recoil alive behind the incoming curtain, even after the cat slides away.
    val retainRecoil = expanded && !transition.currentState && tab in 1..3 && available
    val cordMounted = cordState.currentState || cordState.targetState || !cordState.isIdle || retainRecoil
    LaunchedEffect(tab, available) { if (tab == 0 || !available) expanded = false }
    BackHandler(expanded) { dismiss() }
    Box(Modifier.fillMaxSize().clipToBounds().onSizeChanged { heightPx = it.height }
        .onGloballyPositioned { layerTop = it.boundsInWindow().top }) {
        Box(Modifier.fillMaxSize().motionInput(!visible)) { content(headerModifier) }
        if (cordMounted && headerBottom != null) {
            // Anchor to the measured app bar, including its actual height and system insets.
            // Retain its spring behind the falling sheet until opening has finished.
            Box(Modifier.align(Alignment.TopEnd)
                .offset { IntOffset(0, ((headerBottom ?: layerTop) - layerTop).coerceAtLeast(0f).roundToInt()) }
                .padding(end = 16.dp).testTag("assistant-cord-recoil")
                .drawWithContent {
                    // Hide the area above the app bar without clipping the spring's lower overshoot.
                    clipRect(top = 0f, bottom = size.height + AssistantMascotRestHeight.toPx()) {
                        this@drawWithContent.drawContent()
                    }
                }) {
                Box(Modifier.graphicsLayer {
                    translationY = (cordProgress.value - 1f) * size.height
                }.testTag("assistant-cord-appearance")) {
                    Box(Modifier.motionInput(cordRequested && cordState.isIdle)) {
                        AssistantPullCord({ expanded = true }, Modifier, opening = expanded)
                    }
                }
            }
        }
        if (visible) {
            // This surface also blocks touches to the lower page while the curtain is moving.
            val scrim = MaterialTheme.colorScheme.scrim
            val light = LocalLightDesign.current
            Box(Modifier.fillMaxSize().drawBehind { drawRect(scrim.copy(alpha = .14f * reveal.value.coerceIn(0f, 1f))) }
                .clickable(remember { MutableInteractionSource() }, indication = null) {}.clearAndSetSemantics {})
            Box(Modifier.fillMaxSize().graphicsLayer { translationY = (reveal.value - 1f) * heightPx }
                .drawWithCache {
                    // Draw outside the paper's Surface so its clip cannot cut off the shadow.
                    // Cache both gradients; animation only translates this complete layer.
                    val spread = 28.dp.toPx()
                    val contact = 4.dp.toPx()
                    val softShadow = Brush.verticalGradient(
                        0f to Color.Black.copy(alpha = if (light) .18f else .42f),
                        .3f to Color.Black.copy(alpha = if (light) .08f else .18f),
                        1f to Color.Transparent,
                        startY = size.height, endY = size.height + spread)
                    val edgeShadow = Brush.verticalGradient(
                        listOf(Color.Black.copy(alpha = if (light) .12f else .24f), Color.Transparent),
                        startY = size.height, endY = size.height + contact)
                    onDrawBehind {
                        drawRect(softShadow, Offset(0f, size.height), Size(size.width, spread))
                        drawRect(edgeShadow, Offset(0f, size.height), Size(size.width, contact))
                    }
                }.testTag("assistant-curtain").semantics { paneTitle = "AI 助手" }) {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    Box(Modifier.fillMaxSize().motionInput(expanded)) {
                        AssistantCurtainPage(store, conversation, notify) { dismiss() }
                        SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).navigationBarsPadding())
                    }
                }
            }
        }
    }
}

@Composable
private fun AssistantPullCord(open: () -> Unit, modifier: Modifier, opening: Boolean) {
    val density = LocalDensity.current
    val threshold = with(density) { 72.dp.toPx() }
    val maximum = with(density) { 120.dp.toPx() }
    val velocityLimit = with(density) { 700.dp.toPx() }
    var drag by remember { mutableFloatStateOf(0f) }
    var dragging by remember { mutableStateOf(false) }
    val recoil = remember { Animatable(0f) }
    val velocityTracker = remember { VelocityTracker() }
    val scope = rememberCoroutineScope()
    var recoilJob by remember { mutableStateOf<Job?>(null) }
    val ready by remember(threshold) { derivedStateOf { dragging && drag >= threshold } }
    fun extension() = if (dragging) drag else recoil.value
    fun release(openAssistant: Boolean, velocity: Float, open: () -> Unit) {
        val displacement = drag
        val releaseVelocity = velocity.coerceIn(-velocityLimit, velocityLimit)
        // Displacement stores spring energy; release velocity adds kinetic energy.
        // Stronger pulls lose less energy per oscillation, so their recoil is more visible.
        val energy = sqrt((displacement / threshold) * (displacement / threshold) +
            (releaseVelocity / velocityLimit) * (releaseVelocity / velocityLimit)).coerceIn(0f, 1f)
        recoilJob?.cancel()
        recoilJob = scope.launch {
            recoil.snapTo(displacement)
            dragging = false
            drag = 0f
            if (openAssistant) open()
            recoil.animateTo(0f,
                animationSpec = spring(dampingRatio = .64f - .24f * energy,
                    stiffness = 320f + 100f * energy, visibilityThreshold = with(density) { .1.dp.toPx() }),
                initialVelocity = releaseVelocity)
        }
    }
    val latestOpen by rememberUpdatedState(open)
    Box(modifier.width(AssistantMascotWidth).layout { measurable, constraints ->
        val height = (AssistantMascotRestHeight.roundToPx() + extension().roundToInt())
            .coerceIn(constraints.minHeight, constraints.maxHeight)
        val placeable = measurable.measure(constraints.copy(minHeight = height, maxHeight = height))
        layout(placeable.width, placeable.height) { placeable.place(0, 0) }
    }.testTag("assistant-pull-cord")
        .semantics {
            contentDescription = "下拉打开 AI 助手"
            stateDescription = if (ready) "松手展开助手" else "向下拉动"
            role = Role.Button
            onClick("展开 AI 助手") { latestOpen(); true }
        }
        .pointerInput(velocityTracker) {
            // Include the up event: holding still before release must dissipate flick velocity.
            awaitPointerEventScope {
                while (true) {
                    val change = awaitPointerEvent(PointerEventPass.Initial).changes.first()
                    if (change.changedToDownIgnoreConsumed()) velocityTracker.resetTracking()
                    velocityTracker.addPosition(change.uptimeMillis, change.position)
                }
            }
        }
        .pointerInput(threshold, maximum, velocityLimit) {
            detectVerticalDragGestures(
                onDragStart = {
                    val current = extension()
                    recoilJob?.cancel()
                    drag = current
                    dragging = true
                },
                onVerticalDrag = { change, amount ->
                    change.consume()
                    drag = (drag + amount).coerceIn(-26.dp.toPx(), maximum)
                },
                onDragEnd = { release(drag >= threshold, velocityTracker.calculateVelocity().y) { latestOpen() } },
                onDragCancel = { release(false, 0f) {} }
            )
        }, contentAlignment = Alignment.BottomCenter) {
        // Keep the smile throughout the curtain entrance and simultaneous cord recoil.
        AssistantPullMascot(dragging = dragging, smiling = ready || opening)
    }
}

@Composable
private fun AssistantCurtainPage(
    store: InventoryStore, conversation: SnapshotStateList<Pair<String, Boolean>>,
    notify: (String) -> Unit, close: () -> Unit
) {
    var initial by rememberSaveable { mutableStateOf("") }
    val light = LocalLightDesign.current
    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        Box(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp)) {
            Column(Modifier.align(Alignment.TopCenter), horizontalAlignment = Alignment.CenterHorizontally) {
                if (light) Image(painterResource(R.drawable.maoyou_welcome),
                    "Mew AI 助手", Modifier.size(88.dp).testTag("assistant-ip"))
                else DarkMaoYou("thinking", Modifier.size(88.dp).testTag("assistant-ip"), "Mew AI 助手")
                Text(stringResource(R.string.brand_assistant_title), fontSize = 21.sp, fontWeight = FontWeight.SemiBold)
                Text("看看库存，也一起安排补货", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp))
            }
            TextButton(onClick = close, modifier = Modifier.align(Alignment.TopEnd).testTag("assistant-close")) { Text("收起 ↑") }
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("查库存" to "家里有什么库存？", "临期提醒" to "哪些快过期了？", "补货建议" to "需要补什么？").forEach { (label, query) ->
                OutlinedButton(onClick = { initial = query }, modifier = Modifier.weight(1f), shape = CircleShape,
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 8.dp)) { Text(label, fontSize = 12.sp) }
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            Chat(store, conversation, initial, { initial = "" }, notify, showIntro = false)
        }
    }
}
