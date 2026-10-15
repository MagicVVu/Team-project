package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.DesignGlyph

/** The production host shares inventory and actions with the rest of the app. */
@Composable
internal fun RingInventoryPage(store: InventoryStore, onOpenItem: (StockItem) -> Unit, onAdd: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("ring-inventory-page")) {
        // Keep adding available in the page; the app bar has one consistent notification action.
        TextButton(onClick = onAdd, modifier = Modifier.align(Alignment.Start).padding(start = 18.dp).testTag("ring-add")) {
            DesignGlyph("plus", Modifier.size(18.dp), MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(4.dp))
            Text("添加物品")
        }
        StockRingBrowser(store.items, store.reminderDays, onOpenItem, onAdd)
        Spacer(Modifier.height(16.dp))
    }
}
