package com.example.teamapp.ui.ring

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.paneTitle
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.lerp
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.CloudProduct
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.AssistantMascotWidth
import com.example.teamapp.ui.Detail
import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.ui.motionInput
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

internal enum class InventoryDetailPhase { Idle, Expanding, Expanded, Collapsing }

/** All business data/actions still belong to the shared store and the existing app panels. */
@Composable
internal fun RingInventoryPage(
    store: InventoryStore,
    onItemAction: (StockItem, String) -> Unit,
    onAdd: () -> Unit,
    notify: (String) -> Unit,
    active: Boolean = true,
    onDetailVisibilityChanged: (Boolean) -> Unit = {}
) {
    val strings = rememberUiStrings()
    val density = LocalDensity.current
    val focus = LocalFocusManager.current
    val light = LocalLightDesign.current
    val palette = remember(light) { RingPalette(if (light) 1f else 0f) }
    // Deliberately not saveable: a disposed page must never restore a stranded overlay.
    var phase by remember { mutableStateOf(InventoryDetailPhase.Idle) }
    var detailId by remember { mutableStateOf<String?>(null) }
    var previewBounds by remember { mutableStateOf(Rect.Zero) }
    var compactPreview by remember { mutableStateOf(false) }
    var hostBounds by remember { mutableStateOf(Rect.Zero) }
    var pendingAction by remember { mutableStateOf<String?>(null) }
    var actionBatch by remember { mutableStateOf<StockItem?>(null) }
    val products = store.cloud.products
    val ringItems = if (store.cloud.signedIn) products.map { it.ringItem(strings.english) } else store.items
    val product = products.firstOrNull { "product:${it.id}" == detailId }
    val expansion = remember { Animatable(0f) }
    val ringFocus = remember { Animatable(0f) }
    val groups = remember { List(4) { Animatable(0f) } }
    val currentAction by rememberUpdatedState(onItemAction)
    val item = ringItems.firstOrNull { it.id == detailId }
    val showing = phase != InventoryDetailPhase.Idle && active && item != null
    val visibilityCallback by rememberUpdatedState(onDetailVisibilityChanged)
    DisposableEffect(showing) {
        visibilityCallback(showing)
        onDispose { visibilityCallback(false) }
    }

    fun close(action: String? = null) {
        if (phase == InventoryDetailPhase.Idle || phase == InventoryDetailPhase.Collapsing) return
        focus.clearFocus()
        pendingAction = action
        phase = InventoryDetailPhase.Collapsing
    }

    // Cancellation on tab changes, family changes/deletion and composition disposal is automatic.
    LaunchedEffect(active, detailId, item != null, phase, store.cloud.scopeKey) {
        if (!active || (detailId != null && item == null)) {
            expansion.snapTo(0f)
            ringFocus.snapTo(0f)
            groups.forEach { it.snapTo(0f) }
            detailId = null
            pendingAction = null
            phase = InventoryDetailPhase.Idle
            return@LaunchedEffect
        }
        when (phase) {
            InventoryDetailPhase.Idle, InventoryDetailPhase.Expanded -> Unit
            InventoryDetailPhase.Expanding -> {
                coroutineScope {
                    // Focus and card expansion share the same start frame.
                    launch { ringFocus.animateTo(1f, tween(180, easing = AppMotion.easing)) }
                    launch { expansion.animateTo(1f, spring(dampingRatio = .88f, stiffness = Spring.StiffnessMediumLow)) }
                    launch {
                        snapshotFlow { expansion.value >= .68f }.first { it }
                        coroutineScope {
                            groups.forEachIndexed { index, group ->
                                launch { group.animateTo(1f, tween(160, delayMillis = index * 50, easing = AppMotion.easing)) }
                            }
                        }
                    }
                }
                phase = InventoryDetailPhase.Expanded
            }
            InventoryDetailPhase.Collapsing -> {
                coroutineScope { groups.forEach { launch { it.animateTo(0f, tween(100)) } } }
                coroutineScope {
                    launch { expansion.animateTo(0f, tween(260, easing = AppMotion.easing)) }
                    launch { ringFocus.animateTo(0f, tween(180, easing = AppMotion.easing)) }
                }
                val action = pendingAction
                val actionItem = actionBatch ?: store.items.firstOrNull { it.id == detailId }
                detailId = null
                pendingAction = null
                actionBatch = null
                phase = InventoryDetailPhase.Idle
                if (action != null && actionItem != null && active) currentAction(actionItem, action)
            }
        }
    }

    BackHandler(showing) { close() }
    BoxWithConstraints(Modifier.fillMaxSize().clipToBounds().testTag("ring-inventory-page")
        .onGloballyPositioned { hostBounds = it.boundsInRoot() }
        .semantics { stateDescription = phase.name }) {
        Column(Modifier.fillMaxSize()) {
        if (store.cloud.signedIn) {
            store.cloud.productError?.let {
                Text(if (strings.english) "Product sync failed. Pull down to retry. $it" else "商品同步失败，请下拉刷新重试。$it",
                    color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(horizontal = 18.dp))
            }
            if (store.cloud.productError == null && store.cloud.unlinkedItems.isNotEmpty()) {
                Text(if (strings.english) "${store.cloud.unlinkedItems.size} batches have no product link; they are excluded from the ring."
                    else "${store.cloud.unlinkedItems.size} 条库存尚未关联商品，暂不计入商品圆环。",
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(horizontal = 18.dp))
            }
        }
        StockRingBrowser(ringItems, store.reminderDays, onOpenItem = { selected ->
            if (phase == InventoryDetailPhase.Idle && active && previewBounds.width > 0 && previewBounds.height > 0) {
                focus.clearFocus()
                detailId = selected.id
                phase = InventoryDetailPhase.Expanding
            }
        }, onAdd = onAdd,
            modifier = Modifier.weight(1f).motionInput(!showing),
            showAddAction = true, toolbarEndPadding = AssistantMascotWidth + 32.dp,
            detailFocus = { ringFocus.value }, hidePreview = showing,
            onPreviewBounds = { bounds, compact -> previewBounds = bounds; compactPreview = compact })
        }

        if (showing) {
            val start = previewBounds.translate(-hostBounds.topLeft)
            val horizontalMargin = 16.dp
            val verticalMargin = 12.dp
            val targetWidth = (maxWidth - horizontalMargin * 2).coerceAtLeast(1.dp)
            val targetHeight = (maxHeight - verticalMargin * 2).coerceAtLeast(1.dp)
            val target = with(density) {
                val top = ((maxHeight - targetHeight) / 2).coerceAtLeast(0.dp).toPx()
                Rect(horizontalMargin.toPx(), top, (horizontalMargin + targetWidth).toPx(), top + targetHeight.toPx())
            }
            val scrimColor = MaterialTheme.colorScheme.scrim
            Box(Modifier.fillMaxSize().testTag("inventory-detail-backdrop")
                .graphicsLayer { alpha = .16f * ringFocus.value }
                .background(scrimColor)
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { close() })

            // Only this surface is remeasured per frame. Its children keep their final widths,
            // so text never reflows while the measured preview bounds grow into the detail bounds.
            Box(Modifier.layout { measurable, _ ->
                val bounds = androidx.compose.ui.geometry.lerp(start, target, expansion.value.coerceIn(0f, 1f))
                val width = bounds.width.roundToInt().coerceAtLeast(1)
                val height = bounds.height.roundToInt().coerceAtLeast(1)
                val placeable = measurable.measure(Constraints.fixed(width, height))
                layout(width, height) { placeable.place(bounds.left.roundToInt(), bounds.top.roundToInt()) }
            }.graphicsLayer {
                shape = RoundedCornerShape(lerp(18.dp, 24.dp, expansion.value.coerceIn(0f, 1f)))
                clip = true
                shadowElevation = with(density) { 5.dp.toPx() } * expansion.value.coerceIn(0f, 1f)
            }.background(palette.panel)
                .border(1.dp, palette.line, RoundedCornerShape(24.dp))
                .pointerInput(Unit) { detectTapGestures {} }
                .testTag("inventory-detail-card").semantics { paneTitle = strings.label("详情") }) {
                Box(Modifier.wrapContentSize(Alignment.TopStart, unbounded = true)
                    .requiredSize(with(density) { start.width.toDp() }, with(density) { start.height.toDp() })
                    .graphicsLayer { alpha = (1f - expansion.value / .35f).coerceIn(0f, 1f) }
                    .clearAndSetSemantics {}) {
                    RingInfoCard(item, store.reminderDays, false, {}, palette, Modifier.fillMaxWidth(), compactPreview)
                }
                Column(Modifier.wrapContentSize(Alignment.TopStart, unbounded = true).requiredSize(targetWidth, targetHeight)
                    .graphicsLayer { alpha = ((expansion.value - .5f) / .18f).coerceIn(0f, 1f) }) {
                    Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = 6.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(strings.label("详情"), color = MaterialTheme.colorScheme.onSurface,
                            style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        TextButton(onClick = { close() }, modifier = Modifier.testTag("inventory-detail-close")) {
                            Text(strings.get(R.string.ui_close_2))
                        }
                    }
                    Box(Modifier.weight(1f).fillMaxWidth().motionInput(phase == InventoryDetailPhase.Expanded)) {
                        if (product != null) ProductInventoryDetail(product) { batch, action ->
                            actionBatch = batch
                            close(action)
                        } else Detail(store, item, { close(it) }, notify, { close() },
                            reveal = { index ->
                                Modifier.graphicsLayer {
                                    alpha = groups[index].value
                                    translationY = with(density) { 12.dp.toPx() } * (1f - groups[index].value)
                                }
                            })
                    }
                }
            }
        }
    }
}
