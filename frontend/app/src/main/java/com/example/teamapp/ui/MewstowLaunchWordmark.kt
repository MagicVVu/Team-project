package com.example.teamapp.ui

import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.ContentDrawScope
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

private const val AssemblyStart = 170f
private const val LetterStagger = 108f
private const val LetterDuration = 490f

private enum class LetterForm { Angular, Curved, Box }

private data class LetterCue(val rightPx: Int, val form: LetterForm, val tilt: Float)

// Boundaries of the original 1624 px wordmark. The last two features are the box and double tail.
private val LetterCues = listOf(
    LetterCue(334, LetterForm.Angular, -34f),
    LetterCue(502, LetterForm.Curved, 42f),
    LetterCue(754, LetterForm.Angular, -39f),
    LetterCue(895, LetterForm.Curved, -46f),
    LetterCue(1028, LetterForm.Angular, 28f),
    LetterCue(1217, LetterForm.Box, -19f),
    LetterCue(1624, LetterForm.Angular, 48f)
)

private data class LetterPiece(val mask: Path, val pivot: Offset, val from: Offset, val turn: Float)
private data class LaunchLetter(val right: Float, val center: Offset, val width: Float, val cue: LetterCue, val pieces: List<LetterPiece>)

internal fun Modifier.assembleMewstowWordmark(accent: Color, elapsed: () -> Float): Modifier = drawWithCache {
    val imageScale = size.width / LetterCues.last().rightPx
    val artHeight = 312 * imageScale
    val top = (size.height - artHeight) / 2f
    val bottom = top + artHeight
    val letters = LetterCues.mapIndexed { index, cue ->
        val left = if (index == 0) 0f else LetterCues[index - 1].rightPx * imageScale
        val right = cue.rightPx * imageScale
        val width = right - left
        val middle = (left + right) / 2f
        val direction = if (cue.tilt < 0) -1f else 1f
        val boxLetter = cue.form == LetterForm.Box
        val slant = if (boxLetter) 0f else direction * artHeight * .18f
        val bands = if (boxLetter) listOf(0f, .56f, 1f) else listOf(0f, .42f, .67f, 1f)
        val pieces = bands.zipWithNext().mapIndexed { piece, (start, end) ->
            val upper = top + artHeight * start
            val lower = top + artHeight * end
            val upperSlant = if (piece == 0) 0f else slant
            val lowerSlant = if (piece == bands.lastIndex - 1) 0f else slant
            val mask = Path().apply {
                moveTo(left, upper + upperSlant)
                lineTo(right, upper - upperSlant)
                lineTo(right, lower - lowerSlant)
                lineTo(left, lower + lowerSlant)
                close()
            }
            val sideways = when {
                boxLetter -> 0f
                piece == 0 -> -.48f
                piece == 1 -> .62f
                else -> -.33f
            }
            val vertical = when {
                piece == 0 -> -.68f
                !boxLetter && piece == 1 -> .08f
                else -> .61f
            }
            LetterPiece(mask, Offset(middle, (upper + lower) / 2f),
                Offset(width * sideways * direction, artHeight * vertical),
                cue.tilt * if (piece == 1) -.75f else 1f)
        }
        LaunchLetter(right, Offset(middle, top + artHeight * .54f), width, cue, pieces)
    }
    onDrawWithContent {
        val time = elapsed() - AssemblyStart
        val finished = ((time - LetterDuration) / LetterStagger).let {
            if (it < 0f) 0 else (it.toInt() + 1).coerceAtMost(letters.size)
        }
        if (finished == letters.size) {
            drawContent()
        } else {
            if (finished > 0) clipRect(right = letters[finished - 1].right) { this@onDrawWithContent.drawContent() }
            for (index in finished until letters.size) {
                val age = time - index * LetterStagger
                if (age < 0f) break
                val letter = letters[index]
                drawLetterPieces(letter, age)
                drawLetterInk(letter, age / LetterDuration, accent)
            }
        }
    }
}

private fun ContentDrawScope.drawLetterPieces(letter: LaunchLetter, age: Float) {
    val lift = 5.dp.toPx()
    letter.pieces.forEachIndexed { index, piece ->
        val progress = ((age - 38f - index * 44f) / 335f).coerceIn(0f, 1f)
        if (progress > 0f) {
            val settle = AppMotion.easing.transform(progress)
            val travel = piece.from * (1f - settle)
            val arc = sin(PI.toFloat() * settle)
            val scale = .24f + .76f * settle + .13f * arc
            withTransform({
                translate(travel.x, travel.y - lift * arc)
                rotate(piece.turn * (1f - settle), piece.pivot)
                scale(scale, scale, piece.pivot)
                clipPath(piece.mask)
            }) { this@drawLetterPieces.drawContent() }
        }
    }
}

private fun DrawScope.drawLetterInk(letter: LaunchLetter, phase: Float, accent: Color) {
    val ribbon = (phase / .83f).coerceIn(0f, 1f)
    val strength = sin(PI.toFloat() * ribbon)
    if (strength > 0f) {
        val color = accent.copy(alpha = .91f * strength)
        val width = letter.width
        val stroke = 2.3.dp.toPx()
        val center = letter.center
        when (letter.cue.form) {
            LetterForm.Curved -> {
                val bounds = Size(width * .68f, 29.dp.toPx())
                drawArc(color, letter.cue.tilt + 310f * ribbon, 195f * strength, false,
                    center - Offset(bounds.width, bounds.height) * .5f, bounds,
                    style = Stroke(stroke, cap = StrokeCap.Round))
            }
            LetterForm.Angular -> {
                val direction = if (letter.cue.tilt < 0) -1f else 1f
                val head = center + Offset((ribbon - .5f) * width * direction, 13.dp.toPx() * cos(PI.toFloat() * ribbon))
                val tail = head + Offset(-width * .29f * direction, 10.dp.toPx() * (1f - ribbon))
                drawLine(color, tail, head, stroke, StrokeCap.Round)
            }
            LetterForm.Box -> {
                val lid = center + Offset(0f, (-17f + 12f * ribbon).dp.toPx())
                drawLine(color, lid - Offset(width * .27f, 0f), lid + Offset(width * .27f, 0f),
                    stroke * 1.5f, StrokeCap.Round)
            }
        }
        for (dot in 0..2) {
            val angle = (letter.cue.tilt + dot * 110f + 105f * ribbon) * PI.toFloat() / 180f
            val position = center + Offset(cos(angle), sin(angle)) * (width * .35f + 6.dp.toPx() * ribbon)
            drawCircle(color.copy(alpha = color.alpha * .62f), (1.3f - dot * .28f).dp.toPx(), position)
        }
    }
}
