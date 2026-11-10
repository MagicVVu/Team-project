package com.example.teamapp.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.ClipOp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.flow.first
import kotlin.math.roundToInt

private val PaperEndPadding = 12.dp

/** The first lazy item is the page intro. The next [paperItems] items share one paper surface. */
@Composable
internal fun ShoppingPaperList(paperItems: Int, content: LazyListScope.() -> Unit) {
    val state = rememberLazyListState()
    val roll = remember {
        val atTop = state.firstVisibleItemIndex == 0 && state.firstVisibleItemScrollOffset == 0
        Animatable(if (paperItems > 0 && atTop) 0f else 1f)
    }
    val light = LocalLightDesign.current
    val artwork = ImageBitmap.imageResource(R.drawable.shopping_paper_botanical)
    // Only the measurements near each end matter for keeping the artwork attached during scroll.
    val edgeHeights = remember(paperItems) { mutableMapOf<Int, Int>() }

    LaunchedEffect(roll) {
        if (roll.value < 1f) {
            snapshotFlow { state.layoutInfo.visibleItemsInfo.isNotEmpty() }.first { it }
            roll.animateTo(1f, tween(650, easing = AppMotion.easing))
        }
    }
    LaunchedEffect(roll) {
        if (roll.value < 1f) {
            snapshotFlow { state.isScrollInProgress }.first { it }
            roll.snapTo(1f)
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("shopping-paper-list").drawWithCache {
            val inset = 18.dp.toPx()
            val paperWidth = (size.width - inset * 2).coerceAtLeast(1f)
            val paper = if (light) Color(0xFFFBF8F1) else Color(0xFF2C2D29)
            val edge = if (light) Color(0xFFD9D5CB) else Color(0xFF4E5049)
            val tape = if (light) Color(0xC9FFFCF0) else Color(0x9DE0DCD0)
            val darkPrint = if (light) null else ColorFilter.colorMatrix(ColorMatrix(floatArrayOf(
                .298f, -.680f, -.069f, 0f, 156f,
                -.202f, -.180f, -.069f, 0f, 159f,
                -.202f, -.680f, .431f, 0f, 159f,
                0f, 0f, 0f, 1f, 0f
            )))
            val tapeWidth = 47.dp.toPx()
            val tapeHeight = 18.dp.toPx()
            val tapeShape = Path().apply {
                moveTo(0f, 0f)
                lineTo(tapeWidth, 0f)
                for (tooth in 1..8) lineTo(tapeWidth * if (tooth % 2 == 0) 1f else .88f, tapeHeight * tooth / 8)
                lineTo(0f, tapeHeight)
                for (tooth in 7 downTo 0) lineTo(tapeWidth * if (tooth % 2 == 0) 0f else .12f, tapeHeight * tooth / 8)
                close()
            }
            val cover = Path()
            onDrawWithContent {
                val info = state.layoutInfo
                val first = info.visibleItemsInfo.firstOrNull { it.index in 1..paperItems }
                val last = info.visibleItemsInfo.lastOrNull { it.index in 1..paperItems }
                if (first == null || last == null) {
                    drawContent()
                    return@onDrawWithContent
                }
                for (item in info.visibleItemsInfo) {
                    if (item.index in 1..paperItems && (item.index <= 4 || item.index > paperItems - 4)) {
                        edgeHeights[item.index] = item.size
                    }
                }
                fun knownHeight(indices: IntRange): Int? {
                    if (indices.count() > 3) return null
                    return indices.sumOf { index ->
                        edgeHeights[index] ?: if (index == paperItems) PaperEndPadding.roundToPx() else return null
                    }
                }
                val origin = info.beforeContentPadding
                val top = knownHeight(1 until first.index)?.let { (origin + first.offset - it).toFloat() }
                val bottom = knownHeight(last.index + 1..paperItems)?.let { (origin + last.offset + last.size + it).toFloat() }
                val visibleTop = (top ?: 0f).coerceAtLeast(0f)
                val visibleBottom = (bottom ?: size.height).coerceAtMost(size.height)
                val progress = roll.value
                val rolling = progress < 1f && top != null && top >= 0f && visibleBottom - visibleTop > 20.dp.toPx()
                val reveal = if (rolling) {
                    val start = visibleTop + 13.dp.toPx()
                    start + (visibleBottom - start) * progress
                } else visibleBottom
                if (reveal > visibleTop) clipRect(top = visibleTop, bottom = reveal) {
                    drawRect(paper, Offset(inset, visibleTop), Size(paperWidth, reveal - visibleTop))
                    val capScale = if (top != null && bottom != null) {
                        ((bottom - top) / 302.dp.toPx()).coerceIn(.18f, 1f)
                    } else 1f
                    if (top != null && top + 152.dp.toPx() * capScale > visibleTop) {
                        drawPaperPrint(artwork, inset, top, paperWidth, 152.dp.toPx() * capScale,
                            paper, darkPrint, atTop = true)
                    }
                    val lowerHeight = 150.dp.toPx() * capScale
                    if (bottom != null && bottom - lowerHeight < reveal) {
                        drawPaperPrint(artwork, inset, bottom - lowerHeight, paperWidth, lowerHeight,
                            paper, darkPrint, atTop = false)
                    }
                    val right = inset + paperWidth
                    drawLine(edge, Offset(inset, visibleTop), Offset(inset, reveal), 1.dp.toPx())
                    drawLine(edge, Offset(right, visibleTop), Offset(right, reveal), 1.dp.toPx())
                    if (top == visibleTop) drawLine(edge, Offset(inset, visibleTop), Offset(right, visibleTop), 1.dp.toPx())
                    if (!rolling && bottom == reveal) drawLine(edge, Offset(inset, reveal), Offset(right, reveal), 1.dp.toPx())
                }
                if (rolling) {
                    cover.reset()
                    cover.addRect(Rect(0f, reveal, size.width, visibleBottom))
                    clipPath(cover, ClipOp.Difference) { this@onDrawWithContent.drawContent() }
                    drawPaperCoil(inset, reveal, paperWidth, progress, paper, edge)
                } else drawContent()
                if (top != null && top + tapeHeight > 0f) {
                    val left = inset + 1.dp.toPx()
                    val right = inset + paperWidth - tapeWidth
                    for ((x, angle) in listOf(left to -15f, right to 13f)) {
                        val y = top - tapeHeight * .49f
                        translate(x, y) {
                            rotate(angle, Offset(tapeWidth / 2, tapeHeight / 2)) {
                                drawPath(tapeShape, edge.copy(alpha = .48f), style = Stroke(1.5.dp.toPx()))
                                drawPath(tapeShape, tape)
                            }
                        }
                    }
                }
            }
        },
        state = state,
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp),
        content = content
    )
}

private fun DrawScope.drawPaperPrint(
    artwork: ImageBitmap, x: Float, y: Float, width: Float, height: Float,
    paper: Color, filter: ColorFilter?, atTop: Boolean
) {
    val sourceY = if (atTop) 0 else artwork.height * 71 / 100
    val sourceHeight = if (atTop) artwork.height * 43 / 100 else artwork.height - sourceY
    drawImage(
        artwork, srcOffset = IntOffset(0, sourceY), srcSize = IntSize(artwork.width, sourceHeight),
        dstOffset = IntOffset(x.roundToInt(), y.roundToInt()),
        dstSize = IntSize(width.roundToInt(), height.roundToInt().coerceAtLeast(1)), colorFilter = filter
    )
    val fade = height * .12f
    val seam = if (atTop) y + height - fade else y
    val colors = if (atTop) listOf(paper.copy(alpha = 0f), paper) else listOf(paper, paper.copy(alpha = 0f))
    drawRect(Brush.verticalGradient(colors, seam, seam + fade), Offset(x, seam), Size(width, fade))
}

private fun DrawScope.drawPaperCoil(x: Float, y: Float, width: Float, progress: Float, paper: Color, edge: Color) {
    val height = 20.dp.toPx() * (1f - .86f * progress)
    val alpha = ((1f - progress) * 8f).coerceAtMost(1f)
    val top = y - height / 2
    val end = Offset(x + width - height * .24f, y)
    val brush = Brush.verticalGradient(listOf(edge, paper, paper, edge).map { it.copy(alpha = alpha) }, top, top + height)
    drawRoundRect(brush, Offset(x, top), Size(width, height), CornerRadius(height * .3f))
    drawOval(edge.copy(alpha = alpha), Offset(end.x - height * .24f, top), Size(height * .48f, height))
    drawOval(paper.copy(alpha = alpha), Offset(end.x - height * .16f, top + height * .15f), Size(height * .32f, height * .7f))
    drawOval(edge.copy(alpha = alpha), Offset(end.x - height * .08f, top + height * .28f), Size(height * .16f, height * .44f))
}

@Composable
internal fun ShoppingPaperHeading(count: Int) {
    val strings = rememberUiStrings()
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 9.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(strings.get(R.string.ui_to_buy_3), Modifier.weight(1f),
            fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold, fontSize = 21.sp, lineHeight = 26.sp)
        Text(strings.itemCount(count), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
    }
}

@Composable
internal fun ShoppingPaperRow(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().padding(horizontal = 12.dp)) {
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .8f))
        content()
    }
}

@Composable
internal fun ShoppingPaperEnd() {
    Spacer(Modifier.height(PaperEndPadding))
}
