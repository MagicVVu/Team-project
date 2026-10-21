package com.example.teamapp.ui

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.painter.BitmapPainter
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.semantics.SemanticsPropertyKey
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R

/** V14 is the identity source in both themes. Frames exclude export padding, never recolor Mew. */
internal enum class MewPose(
    @param:DrawableRes val resource: Int, val label: String,
    x: Int, y: Int, width: Int, height: Int
) {
    Welcome(R.drawable.mew_welcome, "新手引导", 66, 171, 380, 234),
    Listening(R.drawable.mew_listening, "录入倾听", 75, 188, 362, 216),
    Confirming(R.drawable.mew_confirming, "信息确认", 77, 171, 358, 234),
    Overview(R.drawable.mew_overview, "首页概览", 63, 162, 386, 242),
    Expiring(R.drawable.mew_expiring, "临期提醒", 56, 165, 399, 240),
    Expired(R.drawable.mew_expired, "过期提醒", 72, 167, 367, 237),
    LowStock(R.drawable.mew_low_stock, "补货提醒", 56, 152, 398, 253),
    Shopping(R.drawable.mew_shopping, "采购计划", 77, 137, 358, 268),
    Success(R.drawable.mew_success, "操作成功", 86, 152, 339, 253),
    Empty(R.drawable.mew_empty, "空白状态", 73, 182, 366, 223),
    Thinking(R.drawable.mew_thinking, "AI思考", 77, 183, 359, 221),
    Retry(R.drawable.mew_retry, "异常重试", 68, 150, 378, 254);

    val offset = IntOffset(x, y)
    val size = IntSize(width, height)
}

// Tests can compare scene identity across themes without exposing implementation text in the UI.
internal val MewPoseKey = SemanticsPropertyKey<String>("MewPose")

@Composable
internal fun MewMascot(
    pose: MewPose = MewPose.Welcome,
    modifier: Modifier = Modifier,
    description: String? = "Mew"
) {
    val bitmap = ImageBitmap.imageResource(pose.resource)
    val painter = remember(bitmap, pose) { BitmapPainter(bitmap, pose.offset, pose.size) }
    Image(painter, description, modifier.semantics { this[MewPoseKey] = pose.name })
}

@Composable
internal fun MewIntro(pose: MewPose, title: String, subtitle: String, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        MewMascot(pose, Modifier.size(61.dp), description = null)
        Column(Modifier.weight(1f).padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold)
            Text(subtitle, fontSize = 12.sp, lineHeight = 18.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
internal fun MewChatIntro() {
    MewIntro(MewPose.Thinking, "Mew", "家里的物品，一起记清楚", Modifier.padding(vertical = 12.dp))
}

@Composable
internal fun MewAddIntro(mode: String) {
    MewIntro(if (mode == "语音添加") MewPose.Listening else MewPose.Confirming,
        "记一件家里的小物", "确认后，再放进小账本",
        Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(14.dp)).padding(13.dp))
}

@Composable
internal fun MewEmptyState(title: String, subtitle: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(vertical = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        MewMascot(MewPose.Empty, Modifier.size(91.dp), description = null)
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.Medium, textAlign = TextAlign.Center)
        Text(subtitle, fontSize = 11.sp, lineHeight = 18.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 20.dp))
    }
}
