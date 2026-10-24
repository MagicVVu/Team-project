package com.example.teamapp

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.ui.HouseholdPullRefresh
import com.example.teamapp.ui.i18n.AppLanguageProvider
import kotlinx.coroutines.CompletableDeferred
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Offline gesture tests: no accounts, preferences or server data are touched. */
@RunWith(AndroidJUnit4::class)
class HouseholdPullRefreshTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun host(enabled: Boolean = true, busy: Boolean = false, refresh: suspend () -> Unit) {
        compose.setContent {
            MaterialTheme {
                AppLanguageProvider("en") {
                    HouseholdPullRefresh(enabled, busy, refresh, Modifier.fillMaxSize()) {
                        Text("Content")
                    }
                }
            }
        }
    }

    private fun pull(fraction: Float) {
        compose.onNodeWithTag("household-pull-refresh").performTouchInput {
            swipe(Offset(width * .3f, height * .08f), Offset(width * .3f, height * fraction), 600)
        }
        compose.waitForIdle()
    }

    @Test fun shortPullCancelsAndLongPullRefreshesOnceUntilComplete() {
        var calls = 0
        val finished = CompletableDeferred<Unit>()
        host { calls++; finished.await() }
        pull(.12f)
        compose.runOnIdle { assertEquals(0, calls) }
        pull(.85f)
        compose.runOnIdle { assertEquals(1, calls) }
        compose.onNodeWithTag("household-pull-refresh").assert(
            SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "Refreshing"))
        pull(.85f)
        compose.runOnIdle { assertEquals(1, calls); finished.complete(Unit) }
        compose.waitForIdle()
        compose.onNodeWithTag("household-pull-refresh").assert(
            SemanticsMatcher.keyNotDefined(SemanticsProperties.StateDescription))
    }

    @Test fun busyStoreDoesNotQueueAnotherRefresh() {
        var calls = 0
        host(busy = true) { calls++ }
        pull(.85f)
        compose.runOnIdle { assertEquals(0, calls) }
    }

    @Test fun unavailableCloudDoesNotRefresh() {
        var calls = 0
        host(enabled = false) { calls++ }
        pull(.85f)
        compose.runOnIdle { assertEquals(0, calls) }
        compose.onNodeWithTag("household-refresh-indicator").assertDoesNotExist()
    }

    @Test fun failureStopsAnimationAndAllowsRetry() {
        var calls = 0
        host { calls++; error("Offline") }
        pull(.85f)
        compose.runOnIdle { assertEquals(1, calls) }
        compose.onNodeWithTag("household-pull-refresh").assert(
            SemanticsMatcher.keyNotDefined(SemanticsProperties.StateDescription))
        pull(.85f)
        compose.runOnIdle { assertEquals(2, calls) }
    }

    @Test fun scrollingListAwayFromTopDoesNotRefresh() {
        var calls = 0
        compose.setContent {
            MaterialTheme {
                HouseholdPullRefresh(true, false, { calls++ }, Modifier.fillMaxSize()) {
                    LazyColumn(state = rememberLazyListState(initialFirstVisibleItemIndex = 70),
                        modifier = Modifier.fillMaxSize().testTag("scrolling-content")) {
                        items(100) { Text("Row $it", Modifier.height(64.dp)) }
                    }
                }
            }
        }
        pull(.85f)
        compose.runOnIdle { assertEquals(0, calls) }
    }
}
