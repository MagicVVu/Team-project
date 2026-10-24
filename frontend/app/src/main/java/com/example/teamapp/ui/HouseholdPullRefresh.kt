package com.example.teamapp.ui

import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.rememberScrollableState
import androidx.compose.foundation.gestures.scrollable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.pullToRefresh
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Only user-initiated refreshes show the spinner; background polling stays unobtrusive. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun HouseholdPullRefresh(
    enabled: Boolean,
    busy: Boolean,
    onRefresh: suspend () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit
) {
    val strings = rememberUiStrings()
    val state = rememberPullToRefreshState()
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    val currentRefresh by rememberUpdatedState(onRefresh)
    val canRefresh = enabled && !busy && !refreshing
    val refreshLabel = strings.get(R.string.ui_refresh)
    val refreshingLabel = strings.tr("正在刷新", "Refreshing")
    val threshold = 80.dp
    val refresh: () -> Unit = {
        if (canRefresh && !refreshing) {
            refreshing = true
            scope.launch {
                try {
                    currentRefresh()
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    // CloudStatus retains the store's error and sign-in recovery action.
                } finally {
                    refreshing = false
                }
            }
        }
    }
    Box(modifier.clipToBounds().testTag("household-pull-refresh")
        .semantics {
            if (refreshing) stateDescription = refreshingLabel
            if (canRefresh) customActions = listOf(CustomAccessibilityAction(refreshLabel) { refresh(); true })
        }
        .pullToRefresh(refreshing, state, enabled = canRefresh, threshold = threshold, onRefresh = refresh)
    ) {
        // Dispatch unconsumed vertical gestures on fixed/empty pages too. Nested lists
        // still consume their own scrolling first, so refresh starts only at their top.
        Box(Modifier.fillMaxSize().scrollable(
            rememberScrollableState { 0f }, Orientation.Vertical, enabled = enabled
        ), content = content)
        if (enabled || refreshing) {
            PullToRefreshDefaults.Indicator(
                state = state,
                isRefreshing = refreshing,
                modifier = Modifier.align(Alignment.TopCenter).testTag("household-refresh-indicator"),
                threshold = threshold,
                containerColor = MaterialTheme.colorScheme.surface,
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}
