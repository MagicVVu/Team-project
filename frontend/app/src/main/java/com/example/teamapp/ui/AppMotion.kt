package com.example.teamapp.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp

/** Shared, interruptible motion. Compose also applies the system animator duration scale. */
internal object AppMotion {
    const val Quick = 160
    const val Duration = 260
    const val Page = 320
    val easing = FastOutSlowInEasing
}

/** Short travel keeps form controls readable while their container changes size. */
@Composable
internal fun <T> AppMotionContent(
    targetState: T,
    modifier: Modifier = Modifier,
    label: String = "content",
    contentKey: (T) -> Any? = { it },
    content: @Composable (T) -> Unit
) {
    val travel = with(LocalDensity.current) { 12.dp.roundToPx() }
    AnimatedContent(
        targetState = targetState,
        modifier = modifier,
        transitionSpec = {
            (fadeIn(tween(AppMotion.Duration, easing = AppMotion.easing)) +
                slideInVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) { travel })
                .togetherWith(fadeOut(tween(AppMotion.Quick)) +
                    slideOutVertically(tween(AppMotion.Duration, easing = AppMotion.easing)) { -travel / 2 })
                .using(SizeTransform(clip = true) { _, _ -> tween(AppMotion.Duration, easing = AppMotion.easing) })
        },
        label = label,
        contentKey = contentKey
    ) { state ->
        // Exiting controls must not accept a second action or remain in the accessibility tree.
        Box(Modifier.motionInput(state == targetState)) { content(state) }
    }
}

internal fun Modifier.motionInput(active: Boolean): Modifier = if (active) this else
    clearAndSetSemantics {}.onPreviewKeyEvent { true }.pointerInput(Unit) {
        awaitPointerEventScope {
            while (true) awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }
        }
    }

/** Scale is read in the rendering layer; pressing does not remeasure the card or its siblings. */
internal fun Modifier.motionClickable(enabled: Boolean = true, onClick: () -> Unit): Modifier = composed {
    val interactions = remember { MutableInteractionSource() }
    val pressed by interactions.collectIsPressedAsState()
    val scale = animateFloatAsState(
        if (pressed && enabled) .975f else 1f,
        spring(dampingRatio = 1f, stiffness = 750f), label = "press-feedback"
    )
    graphicsLayer { scaleX = scale.value; scaleY = scale.value }
        .clickable(interactionSource = interactions, indication = LocalIndication.current, enabled = enabled, onClick = onClick)
}
