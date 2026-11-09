package com.example.teamapp.ui.ring

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.AppMotion

internal class RingArrival(val item: StockItem)

@Composable
internal fun RingArrivalEffect(
    arrival: RingArrival, start: Offset, landing: Offset, palette: RingPalette,
    onFinished: (RingArrival) -> Unit
) {
    val progress = remember(arrival) { Animatable(0f) }
    val finish = rememberUpdatedState(onFinished)
    LaunchedEffect(arrival) {
        progress.animateTo(1f, tween(720, easing = LinearEasing))
        finish.value(arrival)
    }
    val control = Offset(start.x - (start.y - landing.y) * .46f, start.y)
    fun pointAt(fraction: Float): Offset {
        val t = AppMotion.easing.transform(fraction.coerceIn(0f, 1f))
        val remaining = 1f - t
        return start * (remaining * remaining) + control * (2f * remaining * t) + landing * (t * t)
    }
    Box(Modifier.fillMaxSize().testTag("ring-arrival").clearAndSetSemantics {}) {
        Canvas(Modifier.fillMaxSize()) {
            val flight = (progress.value / .72f).coerceAtMost(1f)
            val ripple = ((progress.value - .62f) / .38f).coerceIn(0f, 1f)
            val trailAlpha = (1f - ripple) * (flight * 5f).coerceAtMost(1f)
            for (dot in 1..3) {
                val lag = .055f * dot
                if (flight > lag) {
                    drawCircle(palette.accent.copy(alpha = trailAlpha * (.63f - .14f * dot)),
                        (4.6f - dot * .85f).dp.toPx(), pointAt(flight - lag))
                }
            }
            if (ripple > 0f) {
                drawCircle(palette.accent.copy(alpha = .6f * (1f - ripple)),
                    (6f + 20f * ripple).dp.toPx(), landing, style = Stroke(1.5.dp.toPx()))
                drawCircle(palette.accent.copy(alpha = .18f * (1f - ripple)),
                    (4f + 12f * ripple).dp.toPx(), landing)
            }
        }
        Box(Modifier.size(36.dp).graphicsLayer {
            val flight = (progress.value / .72f).coerceAtMost(1f)
            val point = pointAt(flight)
            translationX = point.x - size.width / 2
            translationY = point.y - size.height / 2
            alpha = minOf(flight * 7f, (1f - flight) * 5f, 1f)
            scaleX = .64f + .36f * flight
            scaleY = scaleX
        }.background(palette.panel, CircleShape).border(1.dp, palette.accent, CircleShape),
            contentAlignment = Alignment.Center) {
            RingItemIllustration(arrival.item, Modifier.size(25.dp))
        }
    }
}

@Composable
internal fun RingResultCount(position: Int, total: Int, color: Color, modifier: Modifier) {
    val style = TextStyle(color = color, fontSize = 11.sp, lineHeight = 16.sp, fontFeatureSettings = "tnum")
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Text("$position / ", style = style, maxLines = 1, softWrap = false)
        AnimatedContent(total, transitionSpec = {
            val direction = if (targetState > initialState) 1 else -1
            (slideInVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) { it * direction } +
                fadeIn(tween(AppMotion.Duration)))
                .togetherWith(slideOutVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) { -it * direction } +
                    fadeOut(tween(AppMotion.Quick)))
        }, label = "ring-result-total") { count ->
            Text(count.toString(), style = style, maxLines = 1, softWrap = false)
        }
    }
}
