package com.example.teamapp.ui.ring

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.AssistantMascotWidth

/** The production host shares inventory and actions with the rest of the app. */
@Composable
internal fun RingInventoryPage(store: InventoryStore, onOpenItem: (StockItem) -> Unit, onAdd: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("ring-inventory-page")) {
        StockRingBrowser(store.items, store.reminderDays, onOpenItem, onAdd,
            showAddAction = true, toolbarEndPadding = AssistantMascotWidth + 32.dp)
        Spacer(Modifier.height(16.dp))
    }
}
