package com.example.teamapp.ui.ring

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.data.*
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlin.math.roundToInt

/** A reveal menu, never swipe-to-dismiss. Horizontal touch slop leaves vertical scrolling to LazyColumn. */
@Composable
internal fun InventoryPreviewRow(
    item: StockItem, record: InventoryPreviewRecord, number: Int, individual: Boolean, unit: String,
    expanded: Boolean, setExpanded: (Boolean) -> Unit, edit: () -> Unit, opened: () -> Unit,
    consumed: () -> Unit, modifier: Modifier = Modifier
) {
    val s = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val visibility = remember(record.id) { MutableTransitionState(true) }
    var removing by remember(record.id) { mutableStateOf(false) }
    LaunchedEffect(removing) { visibility.targetState = !removing }
    // Observe actual transition completion, including the device animator duration scale.
    LaunchedEffect(visibility.isIdle, visibility.currentState) {
        if (removing && visibility.isIdle && !visibility.currentState) consumed()
    }
    AnimatedVisibility(visibleState = visibility, modifier = modifier,
        enter = EnterTransition.None,
        exit = fadeOut(tween(300, easing = AppMotion.easing)) +
            shrinkVertically(tween(300, easing = AppMotion.easing), shrinkTowards = Alignment.Top) +
            slideOutHorizontally(tween(240, easing = AppMotion.easing)) { -it / 10 }) {
        BoxWithConstraints(Modifier.fillMaxWidth().padding(bottom = 12.dp)
            .testTag("inventory-preview-record-${record.id}").semantics {
                stateDescription = s.get(when { removing -> R.string.ui_preview_removing; expanded -> R.string.ui_preview_menu_open; else -> R.string.ui_preview_menu_closed })
                if (individual && !removing) customActions = listOf(CustomAccessibilityAction(
                    s.get(if (expanded) R.string.ui_preview_hide_actions else R.string.ui_preview_show_actions)) {
                    setExpanded(!expanded); true
                })
            }) {
            val density = LocalDensity.current
            val menuWidth = minOf(216.dp, (maxWidth - 48.dp).coerceAtLeast(144.dp))
            val menuPx = with(density) { menuWidth.toPx() }
            val velocityThreshold = with(density) { 650.dp.toPx() }
            val position = remember(record.id) { Animatable(0f) }
            var dragging by remember(record.id) { mutableStateOf(false) }
            var dragX by remember(record.id) { mutableFloatStateOf(0f) }
            val offset = if (dragging) dragX else position.value
            val fullyOpen = individual && expanded && !dragging && !removing && offset <= -menuPx + 1f
            LaunchedEffect(expanded, dragging, menuPx, removing) {
                if (!dragging && !removing) position.animateTo(if (expanded) -menuPx else 0f,
                    spring(dampingRatio = 1f, stiffness = 550f))
            }
            val dragState = rememberDraggableState { delta -> dragX = (dragX + delta).coerceIn(-menuPx, 0f) }
            Box(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.large)) {
                if (individual) Box(Modifier.matchParentSize().graphicsLayer { alpha = (-offset / menuPx).coerceIn(0f, 1f) }
                    .then(if (fullyOpen) Modifier else Modifier.clearAndSetSemantics {}), contentAlignment = Alignment.CenterEnd) {
                    Row(Modifier.width(menuWidth).fillMaxHeight().padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        @Composable fun Action(label: String, tag: String, enabled: Boolean = true,
                            background: androidx.compose.ui.graphics.Color, foreground: androidx.compose.ui.graphics.Color, action: () -> Unit) {
                            FilledTonalButton(onClick = action, enabled = fullyOpen && enabled,
                                modifier = Modifier.weight(1f).fillMaxHeight().heightIn(min = 48.dp).testTag("inventory-preview-action-$tag-${record.id}")
                                    .semantics { contentDescription = s.get(R.string.ui_preview_record_action, label, item.name, number) },
                                shape = MaterialTheme.shapes.medium, contentPadding = PaddingValues(4.dp),
                                colors = ButtonDefaults.filledTonalButtonColors(containerColor = background, contentColor = foreground)) {
                                Text(label, style = MaterialTheme.typography.labelLarge, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                            }
                        }
                        Action(s.get(R.string.ui_edit), "edit", background = colors.surfaceVariant, foreground = colors.onSurfaceVariant) {
                            setExpanded(false); edit()
                        }
                        Action(s.get(if (record.openedAt == null) R.string.ui_preview_open else R.string.ui_preview_already_open), "open",
                            enabled = record.openedAt == null, background = colors.secondaryContainer, foreground = colors.onSecondaryContainer) {
                            setExpanded(false); opened()
                        }
                        Action(s.get(R.string.ui_preview_consume), "consume", background = colors.primaryContainer, foreground = colors.onPrimaryContainer) {
                            if (!removing) { removing = true; setExpanded(false) }
                        }
                    }
                }
                Surface(Modifier.fillMaxWidth().offset { IntOffset(offset.roundToInt(), 0) }
                    .testTag("inventory-preview-card-${record.id}")
                    .then(if (individual) Modifier.draggable(dragState, Orientation.Horizontal, enabled = !removing,
                        onDragStarted = {
                            position.stop(); dragX = position.value; dragging = true; setExpanded(true)
                        }, onDragStopped = { velocity ->
                            position.snapTo(dragX)
                            val open = when { velocity < -velocityThreshold -> true; velocity > velocityThreshold -> false; else -> dragX < -menuPx * .45f }
                            dragging = false; setExpanded(open)
                        }) else Modifier)
                    .then(if (expanded && !removing) Modifier.clickable { setExpanded(false) } else Modifier),
                    shape = MaterialTheme.shapes.large, color = colors.surfaceContainerLow,
                    border = BorderStroke(1.dp, colors.outlineVariant.copy(alpha = .6f))) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(s.get(if (individual) R.string.ui_preview_piece_title else R.string.ui_preview_batch_title,
                            item.name, number), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
                        if (!individual) Text("${record.quantity.previewText()} $unit", color = colors.primary)
                        Text(s.get(R.string.ui_preview_location, record.location.ifBlank { s.get(R.string.ui_not_set) }),
                            style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                        Text(s.get(R.string.ui_preview_expiry, record.expiryDate ?: s.get(R.string.ui_not_set)),
                            style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
                        Text(s.get(R.string.ui_preview_opened, record.openedAt ?: s.get(R.string.ui_preview_not_recorded)),
                            style = MaterialTheme.typography.bodyMedium, color = if (record.openedAt == null) colors.onSurfaceVariant else colors.primary)
                    }
                }
            }
        }
    }
}
