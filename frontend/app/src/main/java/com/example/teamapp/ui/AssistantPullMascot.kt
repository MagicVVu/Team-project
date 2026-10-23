package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import kotlin.math.max

private const val PullMascotScale = .6f
internal val AssistantMascotWidth = 96.dp * PullMascotScale
internal val AssistantMascotRestHeight = 32.dp * PullMascotScale + AssistantMascotWidth * (768f / 600f)

/** All facial PNGs share the body's 600 x 768 canvas and its rope attachment point. */
@Composable
internal fun AssistantPullMascot(dragging: Boolean, smiling: Boolean, modifier: Modifier = Modifier) {
    val strings = rememberUiStrings()
    val images = listOf(
            R.drawable.maoyou_pull_rope,
            R.drawable.maoyou_pull_body,
            R.drawable.maoyou_pull_eyes_open,
            R.drawable.maoyou_pull_eyes_closed,
            R.drawable.maoyou_pull_mouth_idle,
            R.drawable.maoyou_pull_mouth_smile
        ).map { ImageBitmap.imageResource(it) }
    val expression = animateFloatAsState(if (smiling) 1f else 0f, tween(80), label = "pull-cat-smile")
    val lean = animateFloatAsState(
        if (dragging) -1.5f else 0f,
        spring(dampingRatio = .65f, stiffness = 350f), label = "pull-cat-lean"
    )
    // Infinite transitions honor the system animation scale and do not keep UI tests busy.
    val idle = if (!dragging && !smiling) rememberInfiniteTransition(label = "pull-cat-idle") else null
    val blink = idle?.animateFloat(0f, 0f, infiniteRepeatable(keyframes {
        durationMillis = 4200
        0f at 0
        0f at 3300
        1f at 3370
        1f at 3440
        0f at 3540
        0f at 4200
    }), label = "pull-cat-blink")
    val sway = idle?.animateFloat(0f, 0f, infiniteRepeatable(keyframes {
        durationMillis = 4200
        0f at 0 using FastOutSlowInEasing
        .6f at 1050 using FastOutSlowInEasing
        0f at 2100 using FastOutSlowInEasing
        -.6f at 3150 using FastOutSlowInEasing
        0f at 4200
    }), label = "pull-cat-sway")

    Canvas(modifier.fillMaxSize().testTag("assistant-pull-mascot").semantics {
        stateDescription = if (smiling) strings.get(R.string.ui_smiling_with_eyes_closed) else strings.get(R.string.ui_waiting_with_eyes_open)
    }) {
        val imageScale = size.width / 600f
        val ropeLength = ((size.height - 768f * imageScale) / imageScale).coerceAtLeast(0f)
        val eyesClosed = max(expression.value, blink?.value ?: 0f)
        withTransform({ scale(imageScale, imageScale, Offset.Zero) }) {
            // Continue the original rope's phase at the top of the pendant. Tile, never stretch.
            clipRect(left = 263f, top = 0f, right = 367f, bottom = ropeLength + 1f) {
                var y = ropeLength - 31f
                while (y > -65f) {
                    drawImage(images[0], Offset(263f, y))
                    y -= 65f
                }
            }
            // Rotate the complete tail/knot/body assembly around the fixed rope join.
            withTransform({
                translate(top = ropeLength)
                rotate(lean.value + (sway?.value ?: 0f), Offset(317.5f, 0f))
            }) {
                drawImage(images[1])
                drawImage(images[2], alpha = 1f - eyesClosed)
                drawImage(images[3], alpha = eyesClosed)
                drawImage(images[4], alpha = 1f - expression.value)
                drawImage(images[5], alpha = expression.value)
            }
        }
    }
}
