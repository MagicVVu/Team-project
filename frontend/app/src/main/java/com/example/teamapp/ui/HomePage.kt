package com.example.teamapp.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.display
import com.example.teamapp.data.status
import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.ui.ring.RingItemIllustration
import com.example.teamapp.ui.theme.LocalLightDesign

@Composable
internal fun Home(store: InventoryStore, open: (StockItem) -> Unit, all: () -> Unit, panel: (String) -> Unit, ask: (String) -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val type = MaterialTheme.typography
    val items = store.items
    val reminderDays = store.reminderDays
    val attention = items.count { it.status(reminderDays).attention }
    val overview = items.sortedBy { it.status(reminderDays).priority }.take(4)

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(strings.get(R.string.ui_welcome_home_2), style = type.labelLarge, color = colors.onSurfaceVariant)
                Text(
                    if (items.isEmpty()) strings.get(R.string.ui_add_your_first_item)
                    else strings.get(R.string.ui_items___need_attention, strings.stockCount(items.size), attention),
                    style = type.titleMedium, fontWeight = FontWeight.SemiBold, color = colors.onSurface
                )
                Text(
                    strings.get(if (store.cloud.signedIn) R.string.ui_based_on_household_cloud_inventory else R.string.ui_based_on_local_inventory),
                    style = type.bodySmall, color = colors.onSurfaceVariant
                )
            }
            MewMascot(MewPose.Overview, Modifier.size(56.dp), strings.get(R.string.ui_mew__your_stock_companion))
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HomeAddButton("camera", strings.get(R.string.ui_photo), primary = true, Modifier.weight(1f)) { panel("拍照添加") }
            HomeAddButton("mic", strings.get(R.string.ui_voice), primary = false, Modifier.weight(1f)) { panel("语音添加") }
        }

        HomeAssistantCard(ask = ask, open = { panel("AI 智能管家") })

        Column {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(strings.get(R.string.ui_recent_stock), Modifier.weight(1f).semantics { heading() },
                    style = type.titleMedium, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                TextButton(onClick = all) { Text(strings.get(R.string.ui_view_all)) }
            }
            if (overview.isEmpty()) {
                MewEmptyState(strings.get(R.string.ui_no_items_yet), strings.get(R.string.ui_add_your_first_item_by_photo))
            }
            overview.forEachIndexed { index, item ->
                key(item.id) {
                    if (index > 0) HorizontalDivider(color = colors.outlineVariant)
                    HomeStockRow(item, reminderDays) { open(item) }
                }
            }
        }

        if (store.cloud.signedIn) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(strings.tr("登记日期与阈值提醒", "Recorded dates & stock thresholds"),
                    Modifier.weight(1f), style = type.labelMedium, color = colors.onSurfaceVariant)
                TextButton(onClick = { panel("关注概览") }) { Text(strings.tr("AI 关注概览", "AI overview")) }
            }
        }
    }
}

@Composable
private fun HomeAddButton(icon: String, label: String, primary: Boolean, modifier: Modifier, action: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val ink = if (primary) colors.onPrimaryContainer else colors.primary
    OutlinedButton(
        onClick = action, modifier = modifier.heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, colors.outlineVariant),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = if (primary) colors.primaryContainer else Color.Transparent, contentColor = ink
        ),
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp)
    ) {
        DesignGlyph(icon, Modifier.size(20.dp), ink)
        Spacer(Modifier.width(6.dp))
        Text(label)
    }
}

@Composable
private fun HomeAssistantCard(ask: (String) -> Unit, open: () -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val focus = LocalFocusManager.current
    var question by rememberSaveable { mutableStateOf("") }
    val hasQuestion = question.isNotBlank()
    fun submit() {
        focus.clearFocus()
        if (hasQuestion) {
            ask(question)
            question = ""
        } else open()
    }
    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), color = colors.surface,
        border = BorderStroke(1.dp, colors.outlineVariant)) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(strings.get(R.string.ui_mew_assistant),
                    Modifier.weight(1f).padding(start = 2.dp).semantics { heading() },
                    style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                TextButton(onClick = { focus.clearFocus(); ask("哪些快过期了？") }, modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 4.dp)) {
                    Text(strings.get(R.string.ui_expiring_soon), textAlign = TextAlign.Center)
                }
                TextButton(onClick = { focus.clearFocus(); ask("需要补什么？") }, modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 4.dp)) {
                    Text(strings.get(R.string.ui_restock), textAlign = TextAlign.Center)
                }
            }
            OutlinedTextField(
                question, { question = it }, modifier = Modifier.fillMaxWidth().testTag("home-assistant-input"),
                singleLine = true, shape = RoundedCornerShape(10.dp),
                textStyle = MaterialTheme.typography.bodyMedium,
                placeholder = {
                    Text(strings.get(R.string.ui_ask_about_stock__add_items), maxLines = 1, overflow = TextOverflow.Ellipsis,
                        style = MaterialTheme.typography.bodyMedium)
                },
                keyboardOptions = KeyboardOptions(imeAction = if (hasQuestion) ImeAction.Send else ImeAction.Done),
                keyboardActions = KeyboardActions(onSend = { submit() }, onDone = { focus.clearFocus() }),
                trailingIcon = {
                    TextButton(onClick = ::submit, modifier = Modifier.testTag("home-assistant-action"),
                        contentPadding = PaddingValues(horizontal = 8.dp)) {
                        Text(strings.get(if (hasQuestion) R.string.ui_send else R.string.ui_home_ask_mew))
                    }
                }
            )
        }
    }
}

@Composable
private fun HomeStockRow(item: StockItem, reminderDays: Int, open: () -> Unit) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val type = MaterialTheme.typography
    val status = item.status(reminderDays)
    val statusColor = when {
        status.expired -> colors.error
        status.attention && !LocalLightDesign.current -> colors.tertiary
        status.attention -> colors.secondary
        else -> colors.onSurfaceVariant
    }
    val facts = buildList {
        add("${item.quantity.display()} ${item.unit}")
        if (item.location.isNotBlank()) add(item.location)
        if (item.expiry.isNotBlank()) add("${strings.get(R.string.ui_expiry_date)} ${item.expiry}")
    }
    Row(Modifier.fillMaxWidth().heightIn(min = 58.dp).clip(RoundedCornerShape(10.dp))
        .semantics { role = Role.Button }.motionClickable(onClick = open).padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(38.dp).background(colors.surfaceVariant, RoundedCornerShape(9.dp)), contentAlignment = Alignment.Center) {
            RingItemIllustration(item, Modifier.size(28.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(item.name, style = type.titleSmall, color = colors.onSurface, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(facts.joinToString(" · "), style = type.bodySmall, color = colors.onSurfaceVariant,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        Text(strings.label(status.label), Modifier.widthIn(max = 88.dp), style = type.labelMedium, color = statusColor)
    }
}
