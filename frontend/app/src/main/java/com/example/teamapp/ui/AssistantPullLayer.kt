package com.example.teamapp.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.theme.LocalLightDesign

/** A full-screen curtain sits above the entire scaffold, including its navigation bar. */
@Composable
internal fun AssistantPullLayer(
    tab: Int, available: Boolean, store: InventoryStore,
    conversation: SnapshotStateList<Pair<String, Boolean>>,
    snackbar: SnackbarHostState, notify: (String) -> Unit, content: @Composable () -> Unit
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    var heightPx by remember { mutableIntStateOf(0) }
    val focus = LocalFocusManager.current
    fun dismiss() { focus.clearFocus(); expanded = false }
    val reveal by animateFloatAsState(if (expanded) 1f else 0f,
        tween(420, easing = FastOutSlowInEasing), label = "assistant-curtain")
    LaunchedEffect(tab, available) { if (tab == 0 || !available) expanded = false }
    BackHandler(expanded) { dismiss() }
    Box(Modifier.fillMaxSize().clipToBounds().onSizeChanged { heightPx = it.height }) {
        Box(if (expanded) Modifier.fillMaxSize().clearAndSetSemantics {} else Modifier.fillMaxSize()) { content() }
        if (tab in 1..3 && available && !expanded && reveal == 0f) {
            AssistantPullCord({ expanded = true }, Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(end = 16.dp))
        }
        if (expanded || reveal > 0f) {
            // This surface also blocks touches to the lower page while the curtain is moving.
            Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.scrim.copy(alpha = .14f * reveal))
                .clickable(remember { MutableInteractionSource() }, indication = null) {}.clearAndSetSemantics {})
            Surface(Modifier.fillMaxSize().graphicsLayer { translationY = (reveal - 1f) * heightPx }
                .testTag("assistant-curtain").semantics { paneTitle = "AI 助手" }, color = MaterialTheme.colorScheme.background) {
                Box(Modifier.fillMaxSize()) {
                    AssistantCurtainPage(store, conversation, notify) { dismiss() }
                    SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).navigationBarsPadding())
                }
            }
        }
    }
}

@Composable
private fun AssistantPullCord(open: () -> Unit, modifier: Modifier) {
    val density = LocalDensity.current
    val threshold = with(density) { 72.dp.toPx() }
    val maximum = with(density) { 120.dp.toPx() }
    var drag by remember { mutableFloatStateOf(0f) }
    var dragging by remember { mutableStateOf(false) }
    val extension by animateFloatAsState(if (dragging) drag else 0f,
        if (dragging) snap() else spring(dampingRatio = .65f, stiffness = 450f), label = "cord-return")
    val ready = drag >= threshold
    val color = MaterialTheme.colorScheme.primary
    val fill = MaterialTheme.colorScheme.primaryContainer
    val ink = MaterialTheme.colorScheme.onPrimaryContainer
    val latestOpen by rememberUpdatedState(open)
    Box(modifier.width(52.dp).height(76.dp + with(density) { extension.toDp() }).testTag("assistant-pull-cord")
        .semantics {
            contentDescription = "下拉打开 AI 助手"
            stateDescription = if (ready) "松手展开助手" else "向下拉动"
            role = Role.Button
            onClick("展开 AI 助手") { latestOpen(); true }
        }
        .pointerInput(threshold, maximum) {
            detectVerticalDragGestures(
                onDragStart = { dragging = true; drag = 0f },
                onVerticalDrag = { change, amount -> change.consume(); drag = (drag + amount).coerceIn(0f, maximum) },
                onDragEnd = { val release = drag >= threshold; dragging = false; drag = 0f; if (release) latestOpen() },
                onDragCancel = { dragging = false; drag = 0f }
            )
        }, contentAlignment = Alignment.BottomCenter) {
        Canvas(Modifier.fillMaxSize()) {
            val x = size.width / 2f
            val handleY = size.height - 22.dp.toPx()
            drawLine(color.copy(alpha = .7f), Offset(x, 0f), Offset(x, handleY), 2.dp.toPx(), StrokeCap.Round)
            drawCircle(fill, 17.dp.toPx(), Offset(x, handleY))
            drawCircle(color, 17.dp.toPx(), Offset(x, handleY), style = Stroke(if (ready) 2.5.dp.toPx() else 1.3.dp.toPx()))
        }
        Text(if (ready) "↓" else "AI", fontSize = if (ready) 20.sp else 12.sp, fontWeight = FontWeight.SemiBold,
            color = ink, modifier = Modifier.padding(bottom = 14.dp))
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
                    "猫又 AI 助手", Modifier.size(88.dp).testTag("assistant-ip"))
                else DarkMaoYou("thinking", Modifier.size(88.dp).testTag("assistant-ip"), "猫又 AI 助手")
                Text("猫又 · AI 助手", fontSize = 21.sp, fontWeight = FontWeight.SemiBold)
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
