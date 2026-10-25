package com.example.teamapp.ui.ring

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.StockItemImage
import androidx.compose.foundation.layout.fillMaxSize

/** Code-drawn illustrations share the existing app's cream, sage and peach palette. */
@Composable
internal fun RingItemIllustration(item: StockItem, modifier: Modifier) {
    if (item.image.isNotBlank()) {
        StockItemImage(item, modifier) { RingItemIllustration(item.copy(image = ""), Modifier.fillMaxSize()) }
        return
    }
    val ink = Color(0xFF667F51)
    val kind = when {
        item.name.contains("奶") -> "milk"
        item.name.contains("面包") -> "bread"
        item.name.contains("苹果") || item.name.contains("番茄") -> "apple"
        item.name.contains("香蕉") -> "banana"
        item.name.contains("蛋") -> "egg"
        item.name.contains("纸") -> "paper"
        item.name.contains("电池") -> "battery"
        item.category == "日用品" -> "bottle"
        else -> "box"
    }
    if (kind in listOf("milk", "bread", "apple", "box")) {
        DesignGlyph(kind, modifier, ink)
        return
    }
    Canvas(modifier) {
        withTransform({ scale(size.width / 24f, size.height / 24f, Offset.Zero) }) {
            val stroke = Stroke(1.15f, cap = StrokeCap.Round)
            val cream = Color(0xFFFFFFE9)
            val sage = Color(0xFFC9D4B3)
            fun line(a: Offset, b: Offset) = drawLine(ink, a, b, 1.1f, StrokeCap.Round)
            when (kind) {
                "banana" -> {
                    val shape = Path().apply {
                        moveTo(3f, 4f); cubicTo(8f, 16f, 17f, 17f, 22f, 9f)
                        cubicTo(23f, 20f, 8f, 25f, 3f, 9f); close()
                    }
                    drawPath(shape, Color(0xFFF0D579)); drawPath(shape, ink, style = stroke)
                    line(Offset(3f, 4f), Offset(2f, 1f)); line(Offset(2f, 1f), Offset(4f, 1f))
                }
                "egg" -> {
                    val shape = Path().apply {
                        moveTo(12f, 2f); cubicTo(4f, 2f, 1f, 14f, 5f, 19f)
                        cubicTo(11f, 27f, 23f, 18f, 19f, 10f); cubicTo(17f, 5f, 15f, 2f, 12f, 2f); close()
                    }
                    drawPath(shape, cream); drawPath(shape, ink, style = stroke)
                    drawArc(ink, 70f, 85f, false, Offset(6f, 11f), Size(11f, 9f), style = stroke)
                }
                "paper" -> {
                    drawRoundRect(cream, Offset(3f, 7f), Size(18f, 15f), CornerRadius(2f))
                    drawRoundRect(ink, Offset(3f, 7f), Size(18f, 15f), CornerRadius(2f), style = stroke)
                    drawRect(sage, Offset(4f, 15f), Size(16f, 6f))
                    val tissue = Path().apply { moveTo(9f, 11f); lineTo(6f, 4f); lineTo(11f, 2f); lineTo(16f, 4f); lineTo(14f, 11f); close() }
                    drawPath(tissue, cream); drawPath(tissue, ink, style = stroke)
                    line(Offset(8f, 11f), Offset(16f, 11f))
                }
                "battery" -> {
                    drawRoundRect(sage, Offset(7f, 4f), Size(10f, 19f), CornerRadius(2f))
                    drawRect(Color(0xFFE4CFA0), Offset(7f, 5f), Size(10f, 6f))
                    drawRoundRect(ink, Offset(7f, 4f), Size(10f, 19f), CornerRadius(2f), style = stroke)
                    drawRect(ink, Offset(10f, 1f), Size(4f, 3f))
                    line(Offset(10f, 15f), Offset(14f, 15f)); line(Offset(12f, 13f), Offset(12f, 17f))
                }
                "bottle" -> {
                    val shape = Path().apply { moveTo(9f, 6f); lineTo(15f, 6f); lineTo(18f, 10f); lineTo(18f, 22f); lineTo(6f, 22f); lineTo(6f, 10f); close() }
                    drawPath(shape, cream); drawPath(shape, ink, style = stroke)
                    drawRoundRect(sage, Offset(7f, 12f), Size(10f, 7f), CornerRadius(1f))
                    drawRoundRect(ink, Offset(9f, 2f), Size(6f, 4f), CornerRadius(1f), style = stroke)
                    val leaf = Path().apply { moveTo(10f, 17f); cubicTo(10f, 12f, 15f, 13f, 15f, 14f); cubicTo(15f, 18f, 12f, 19f, 10f, 17f); close() }
                    drawPath(leaf, ink, style = Stroke(.8f))
                }
            }
        }
    }
}
