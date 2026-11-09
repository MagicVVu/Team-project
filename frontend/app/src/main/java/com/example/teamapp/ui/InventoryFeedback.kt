package com.example.teamapp.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** A separate notice type keeps errors and unrelated messages on the standard snackbar. */
internal data class InventorySavedNotice(override val message: String) : SnackbarVisuals {
    override val actionLabel: String? = null
    override val withDismissAction = false
    override val duration = SnackbarDuration.Short
}

@Composable
internal fun InventoryFeedbackHost(state: SnackbarHostState) {
    SnackbarHost(state) { data ->
        if (data.visuals is InventorySavedNotice) InventorySavedSnackbar(data.visuals.message)
        else Snackbar(data)
    }
}

@Composable
private fun InventorySavedSnackbar(message: String) {
    val colors = MaterialTheme.colorScheme
    var play by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { play = true }
    val badgeScale = animateFloatAsState(if (play) 1f else .76f,
        spring(dampingRatio = .68f, stiffness = 580f), label = "saved-badge")
    val progress = animateFloatAsState(if (play) 1f else 0f,
        tween(280, easing = AppMotion.easing), label = "saved-checkmark")
    val checkColor = colors.onPrimaryContainer

    Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), contentAlignment = Alignment.Center) {
        Surface(Modifier.testTag("inventory-saved-notice"), shape = CircleShape,
            color = colors.surfaceContainerHigh, contentColor = colors.onSurface, shadowElevation = 5.dp) {
            Row(Modifier.padding(start = 8.dp, end = 16.dp, top = 7.dp, bottom = 7.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.size(28.dp).graphicsLayer { scaleX = badgeScale.value; scaleY = badgeScale.value }
                    .background(colors.primaryContainer, CircleShape), contentAlignment = Alignment.Center) {
                    Canvas(Modifier.size(17.dp)) {
                        val start = Offset(size.width * .17f, size.height * .52f)
                        val corner = Offset(size.width * .41f, size.height * .73f)
                        val end = Offset(size.width * .83f, size.height * .29f)
                        val p = progress.value
                        if (p <= 0f) return@Canvas
                        val path = Path().apply {
                            moveTo(start.x, start.y)
                            if (p < .35f) {
                                val tip = start + (corner - start) * (p / .35f)
                                lineTo(tip.x, tip.y)
                            } else {
                                lineTo(corner.x, corner.y)
                                val tip = corner + (end - corner) * ((p - .35f) / .65f)
                                lineTo(tip.x, tip.y)
                            }
                        }
                        drawPath(path, checkColor, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                    }
                }
                Text(message, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
