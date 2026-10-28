package com.example.teamapp.ui.ring

import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.updateTransition
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalMinimumInteractiveComponentSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.lerp
import androidx.compose.ui.unit.sp
import com.example.teamapp.R
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.ui.motionInput
import kotlinx.coroutines.flow.first

/** UI-only mode; the caller retains the existing query/filter data flow and add action. */
@Composable
internal fun InventorySearchToolbar(
    query: String,
    onQueryChange: (String) -> Unit,
    onAdd: () -> Unit,
    palette: RingPalette,
    modifier: Modifier = Modifier
) {
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val requester = remember { FocusRequester() }
    var searching by rememberSaveable { mutableStateOf(query.isNotEmpty()) }
    val transition = updateTransition(searching, label = "inventory-search-mode")
    // One interruptible progress value keeps geometry, opacity and icon rotation in sync.
    val progress by transition.animateFloat(
        transitionSpec = { tween(300, easing = AppMotion.easing) }, label = "search-expansion"
    ) { if (it) 1f else 0f }

    LaunchedEffect(searching) {
        if (searching) {
            // Wait for the actual transition, including system animation scale. Cancellation
            // prevents a quick cancel from reopening the IME after the field has closed.
            snapshotFlow { transition.currentState && !transition.isRunning }.first { it }
            requester.requestFocus()
            keyboard?.show()
        }
    }

    val buttonSize = 40.dp
    val buttonGap = 8.dp
    CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides buttonSize) {
        BoxWithConstraints(modifier.height(buttonSize).testTag("ring-toolbar")) {
            // Reserve room for the action and its gap. Both controls share one row, so
            // the action follows the animated search edge in either direction.
            val expandedWidth = (maxWidth - buttonSize - buttonGap).coerceAtLeast(buttonSize)
            Row(Modifier.fillMaxWidth().height(buttonSize),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(buttonGap)) {
                // A constant 20dp radius turns the same surface from a circle into a capsule.
                Row(Modifier.width(lerp(buttonSize, expandedWidth, progress)).height(buttonSize)
                    .clip(CircleShape)
                    .border(1.dp, palette.line, CircleShape).testTag("ring-search-surface"),
                    verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = {
                        if (!searching) searching = true
                        else if (!transition.isRunning) { requester.requestFocus(); keyboard?.show() }
                    }, modifier = Modifier.size(buttonSize).testTag("ring-search-toggle")
                        .semantics { contentDescription = strings.get(R.string.ui_search_items) }) {
                        DesignGlyph("search", Modifier.size(18.dp), scheme.onSurfaceVariant)
                    }
                    // Keep the field mounted through collapse. Its full-width contents are clipped
                    // by the shrinking surface, so neither text reflow nor a replacement icon jumps.
                    if (searching || progress > 0f) {
                        Box(Modifier.weight(1f).padding(end = 12.dp).graphicsLayer { alpha = progress }
                            .motionInput(searching)) {
                            BasicTextField(query, onQueryChange, singleLine = true, enabled = searching,
                                textStyle = TextStyle(color = scheme.onSurface, fontSize = 12.sp),
                                modifier = Modifier.wrapContentSize(Alignment.CenterStart, unbounded = true)
                                    .requiredWidth((expandedWidth - buttonSize - 12.dp).coerceAtLeast(1.dp))
                                    .focusRequester(requester).testTag("ring-search")
                                    .semantics { contentDescription = strings.get(R.string.ui_search_item_names) },
                                decorationBox = { field ->
                                    Box {
                                        if (query.isEmpty()) Text(strings.get(R.string.ui_search_items),
                                            fontSize = 12.sp, lineHeight = 16.sp, color = scheme.onSurfaceVariant)
                                        field()
                                    }
                                })
                        }
                    }
                }
                IconButton(onClick = {
                    focus.clearFocus(force = true)
                    keyboard?.hide()
                    if (searching) {
                        searching = false
                        onQueryChange("")
                    } else onAdd()
                }, modifier = Modifier.size(buttonSize).clip(CircleShape)
                    .background(scheme.primaryContainer).testTag("ring-add")
                    .semantics {
                        contentDescription = strings.get(if (searching) R.string.ui_cancel else R.string.ui_add_items)
                    }) {
                    DesignGlyph("plus", Modifier.size(18.dp).graphicsLayer { rotationZ = 45f * progress },
                        scheme.onPrimaryContainer)
                }
            }
        }
    }
}
