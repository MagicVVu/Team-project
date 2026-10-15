package com.example.teamapp.ui

import androidx.compose.foundation.background
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
    val glyph = listOf("leaf", "box", "cart", "person")[tab]
    val title = listOf(if (light) "拾物" else "你好，欢迎回家", "我的库存", "采购清单", "我的")[tab]
    val count = store.items.count {
        val status = it.status(store.reminderDays)
        (status.low && store.notifications[0]) || (status.soon && store.notifications[1]) || (status.expired && store.notifications[2])
    }
    Row(modifier.fillMaxWidth().heightIn(min = 56.dp)
        .background(if (light) DesignHeaderColor else DarkHeaderColor)
        .padding(horizontal = 18.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (light) DesignGlyph(glyph, Modifier.size(26.dp).testTag("app-top-bar-icon"), ink)
        else DarkGlyph(glyph, Modifier.size(26.dp).testTag("app-top-bar-icon"), ink)
        Text(title, fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold,
            color = ink, modifier = Modifier.weight(1f).testTag("app-top-bar-title"))
        IconButton(onClick = reminders, modifier = Modifier.size(48.dp)
            .testTag("app-top-bar-notifications").semantics { contentDescription = "库存提醒" }) {
            BadgedBox(badge = {
                if (count > 0) Badge(containerColor = if (light) MaterialTheme.colorScheme.error else Color(0xFF6C4740)) {
                    Text(count.toString())
                }
            }) {
                if (light) DesignGlyph("bell", Modifier.size(22.dp), ink)
                else DarkGlyph("bell", Modifier.size(22.dp), ink)
            }
        }
    }
}
