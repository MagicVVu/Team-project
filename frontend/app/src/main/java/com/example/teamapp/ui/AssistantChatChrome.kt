package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.ui.i18n.rememberUiStrings

@Composable
internal fun rememberAssistantToolsExpanded(scopeKey: String, lastMessageKey: String?): MutableState<Boolean> {
    val expanded = rememberSaveable(scopeKey) { mutableStateOf(lastMessageKey == null) }
    // Restored history and messages sent from another entry point also start in chat mode.
    LaunchedEffect(lastMessageKey) { if (lastMessageKey != null) expanded.value = false }
    return expanded
}

@Composable
internal fun AssistantChatHeader(expanded: Boolean, toggle: () -> Unit, showBrand: Boolean, close: (() -> Unit)? = null) {
    val strings = rememberUiStrings()
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        if (showBrand) {
            MewMascot(MewPose.Thinking, Modifier.size(32.dp).testTag("assistant-ip"), description = null)
            Text(strings.get(R.string.brand_assistant_title), Modifier.weight(1f).padding(start = 8.dp),
                fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        } else Spacer(Modifier.weight(1f))
        TextButton(onClick = toggle, contentPadding = PaddingValues(horizontal = 8.dp),
            modifier = Modifier.heightIn(min = 48.dp).testTag("ai-tools-toggle").semantics {
                stateDescription = if (expanded) strings.tr("已展开", "Expanded") else strings.tr("已折叠", "Collapsed")
            }) {
            Text(strings.tr("快捷功能", "Shortcuts"), style = MaterialTheme.typography.labelMedium)
            Icon(if (expanded) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                contentDescription = null, modifier = Modifier.size(18.dp))
        }
        close?.let { onClose ->
            TextButton(onClick = onClose, modifier = Modifier.heightIn(min = 48.dp).testTag("assistant-close")) {
                Text(strings.get(R.string.ui_close))
            }
        }
    }
}

@Composable
internal fun AssistantQuickActions(enabled: Boolean = true, send: (String) -> Unit) {
    val strings = rememberUiStrings()
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("查库存" to "家里有什么库存？", "临期提醒" to "哪些快过期了？", "补货建议" to "需要补什么？").forEach { (label, query) ->
            OutlinedButton(onClick = { send(query) }, enabled = enabled,
                modifier = Modifier.weight(1f).heightIn(min = 48.dp), shape = CircleShape,
                contentPadding = PaddingValues(horizontal = 4.dp, vertical = 8.dp)) {
                Text(strings.label(label), fontSize = 12.sp)
            }
        }
    }
}
