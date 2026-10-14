package com.example.teamapp.ui.ring

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
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
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.status
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.theme.LocalLightDesign

/** The production host shares inventory and actions with the rest of the app. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun RingInventoryPage(store: InventoryStore, onOpenItem: (StockItem) -> Unit, onAdd: () -> Unit) {
    val light = LocalLightDesign.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("ring-inventory-page")) {
        Row(
            Modifier.fillMaxWidth().background(if (light) Color(0xFFB2C57D) else Color(0xFF202124))
                .padding(horizontal = 18.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("我的库存", fontSize = 25.sp, lineHeight = 31.sp, fontWeight = FontWeight.Bold)
                Text("${store.items.size} 种物品 · ${store.items.count { it.status(store.reminderDays).attention }} 项需关注",
                    fontSize = 10.sp, lineHeight = 15.sp, modifier = Modifier.padding(top = 3.dp))
            }
            CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides 0.dp) {
                IconButton(onClick = onAdd,
                    modifier = Modifier.size(48.dp).semantics { contentDescription = "添加物品" }.testTag("ring-add")) {
                    Box(Modifier.size(30.dp).background(MaterialTheme.colorScheme.primary, CircleShape), contentAlignment = Alignment.Center) {
                        DesignGlyph("plus", Modifier.size(20.dp), MaterialTheme.colorScheme.onPrimary)
                    }
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        StockRingBrowser(store.items, store.reminderDays, onOpenItem, onAdd)
        Spacer(Modifier.height(16.dp))
    }
}
