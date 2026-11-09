package com.example.teamapp.ui.ring

import android.graphics.PathMeasure
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.lerp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.asAndroidPath
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.LayoutDirection
import kotlin.math.abs
import kotlin.math.max

/** Snapshot the actual selected sector once, in root coordinates, before the ring recedes. */
internal class SectorDetailOrigin private constructor(
    val bounds: Rect,
    private val contour: List<Offset>,
    val labelCenter: Offset,
    val labelSize: Size,
    val labelScale: Float,
    val rotation: Float,
    val fill: Color,
    val edge: Color,
    val edgeWidth: Float
) {
    fun shape(target: Size, corner: Float, progress: () -> Float): Shape {
        // Project the same outline points outward onto the rounded detail rectangle.
        // The paired vertices let the serrated edge straighten without switching shapes.
        val end = contour.map { point ->
            val dx = point.x - .5f
            val dy = point.y - .5f
            if (dx == 0f && dy == 0f) return@map point
            var lo = 0f
            var hi = .5f / max(abs(dx), abs(dy))
            repeat(12) {
                val mid = (lo + hi) / 2
                val x = (abs(dx * mid) * target.width - (target.width / 2 - corner)).coerceAtLeast(0f)
                val y = (abs(dy * mid) * target.height - (target.height / 2 - corner)).coerceAtLeast(0f)
                if (x * x + y * y <= corner * corner) lo = mid else hi = mid
            }
            Offset(.5f + dx * lo, .5f + dy * lo)
        }
        return object : Shape {
            override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline {
                val t = progress().coerceIn(0f, 1f)
                return Outline.Generic(Path().apply {
                    contour.forEachIndexed { index, point ->
                        val p = lerp(point, end[index], t)
                        if (index == 0) moveTo(p.x * size.width, p.y * size.height)
                        else lineTo(p.x * size.width, p.y * size.height)
                    }
                    close()
                })
            }
        }
    }

    companion object {
        fun capture(path: Path, transform: (Offset) -> Offset, labelCenter: Offset, labelSize: Size,
            labelScale: Float, rotation: Float, fill: Color, edge: Color, edgeWidth: Float): SectorDetailOrigin? {
            val measure = PathMeasure(path.asAndroidPath(), true)
            if (measure.length <= 0f) return null
            val coords = FloatArray(2)
            val points = List(384) { i ->
                measure.getPosTan(measure.length * i / 384, coords, null)
                transform(Offset(coords[0], coords[1]))
            }
            val bounds = Rect(points.minOf { it.x }, points.minOf { it.y }, points.maxOf { it.x }, points.maxOf { it.y })
            if (bounds.width < 1f || bounds.height < 1f) return null
            val contour = points.map { Offset((it.x - bounds.left) / bounds.width, (it.y - bounds.top) / bounds.height) }
            return SectorDetailOrigin(bounds, contour, labelCenter, labelSize, labelScale, rotation, fill, edge, edgeWidth)
        }
    }
}
