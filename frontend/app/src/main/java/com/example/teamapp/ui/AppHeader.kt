package com.example.teamapp.ui

import androidx.compose.foundation.background
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.status
import com.example.teamapp.ui.theme.LocalLightDesign

/** One layout keeps all four pages' titles and notification actions aligned. */
@Composable
internal fun AppHeader(tab: Int, store: InventoryStore, reminders: () -> Unit, modifier: Modifier = Modifier) {
    val light = LocalLightDesign.current
    val ink = if (light) DesignInk else DarkInk
    val background = if (light) DesignHeaderColor else DarkHeaderColor
    val count = store.items.count {
        val status = it.status(store.reminderDays)
        (status.low && store.notifications[0]) || (status.soon && store.notifications[1]) || (status.expired && store.notifications[2])
    }
    Row(modifier.fillMaxWidth().heightIn(min = 56.dp)
        .background(background)
        .padding(horizontal = 18.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        AppMotionContent(tab, Modifier.size(26.dp), label = "header-icon") { page ->
            val glyph = listOf("leaf", "box", "cart", "person")[page]
            if (light) DesignGlyph(glyph, Modifier.size(26.dp).testTag("app-top-bar-icon"), ink)
            else DarkGlyph(glyph, Modifier.size(26.dp).testTag("app-top-bar-icon"), ink)
        }
        AppMotionContent(tab, Modifier.weight(1f), label = "header-title") { page ->
            val title = listOf(if (light) "拾物" else "你好，欢迎回家", "我的库存", "采购清单", "我的")[page]
            Text(title, fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold,
                color = ink, modifier = Modifier.testTag("app-top-bar-title"))
        }
        IconButton(onClick = reminders, modifier = Modifier.size(48.dp)
            .testTag("app-top-bar-notifications").semantics { contentDescription = "库存提醒" }) {
            BadgedBox(badge = {
                androidx.compose.animation.AnimatedVisibility(count > 0, enter = fadeIn(tween(AppMotion.Quick)) + scaleIn(tween(AppMotion.Duration)),
                    exit = fadeOut(tween(AppMotion.Quick)) + scaleOut(tween(AppMotion.Quick))) {
                    Badge(containerColor = if (light) MaterialTheme.colorScheme.error else Color(0xFF6C4740)) {
                        AppMotionContent(count, label = "reminder-count") { value -> Text(value.toString()) }
                    }
                }
            }) {
                if (light) DesignGlyph("bell", Modifier.size(22.dp), ink)
                else DarkGlyph("bell", Modifier.size(22.dp), ink)
            }
        }
    }
}
