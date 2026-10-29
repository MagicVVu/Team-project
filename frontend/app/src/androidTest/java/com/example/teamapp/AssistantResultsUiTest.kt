package com.example.teamapp

import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.AgentResultCards
import com.example.teamapp.ui.AssistantTaskCard
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AssistantResultsUiTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun stoppedDialogueShowsReasonAlongsideVerifiedReply() {
        val f = ResultsFixture()
        val entry = AssistantEntry("stop-reason", JSONObject().put("text", "查询牛奶").toString(),
            conversationReply = "已查到牛奶在冷藏室。", state = AssistantStatus.ANSWERED,
            conversationResponse = JSONObject().put("dialogue", JSONObject().put("status", "stopped").put("stop_reason", "timeout")).toString())
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { Surface {
            AssistantTaskCard(entry, f.cloud, false, {})
        } } } }
        compose.onNodeWithText("已查到牛奶在冷藏室。").assertIsDisplayed()
        compose.onNodeWithTag("ai-dialogue-stop-reason").assertTextContains("处理超时", substring = true).assertIsDisplayed()
        compose.onNodeWithTag("ai-confirm-stop-reason").assertDoesNotExist()
    }

    @Test fun productUnknownsAndMissingPendingSourcesRemainUnknown() {
        var selected = ""
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { Surface {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                AgentResultCards(AssistantResultsExecutionTest.productResult(), { batch, _ -> selected = batch }, {})
            }
        } } } }
        compose.onNodeWithText("商品汇总 · 测试牛奶").assertExists()
        compose.onNodeWithText("可用量：未知 / 尚不足以判断").assertExists()
        screenshot("product-light-zh")
        compose.onNodeWithText("待购来源尚未核对完整，不能当成零待购").performScrollTo().assertIsDisplayed()
        screenshot("planning-gaps-light-zh")
        compose.onNodeWithText("核对这批资料").performScrollTo().performClick()
        assertEquals(ResultAgent.BATCH, selected)
    }

    @Test fun evidenceOnlyResultIsShownOnceWithoutATask() {
        val f = ResultsFixture()
        val result = AssistantResultsExecutionTest.productResult()
        val entry = AssistantEntry("read", JSONObject().put("text", "查商品").toString(), state = AssistantStatus.ANSWERED,
            conversationResponse = JSONObject().put("evidence", JSONArray().put(JSONObject().put("kind", "verified_calculation").put("result", result))
                .put(JSONObject().put("kind", "verified_calculation").put("result", JSONObject(result.toString())))).toString())
        compose.setContent { AppLanguageProvider("en") { TeamAppTheme(darkTheme = true) { Surface {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) { AssistantTaskCard(entry, f.cloud, false, {}) }
        } } } }
        compose.onAllNodesWithText("Product · 测试牛奶").assertCountEquals(1)
        compose.onNodeWithText("Usable quantity: Unknown / insufficient data").assertExists()
        compose.onNodeWithTag("ai-confirm-read").assertDoesNotExist()
        screenshot("evidence-dark-en")
    }

    @Test fun expiredChoicesAreVisibleButNotClickable(): Unit = runBlocking {
        val f = ResultsFixture(); f.remote.expired = true
        val s = f.store(); s.connectAndRecover()
        val entry = s.activeEntry!!
        f.cloud.assistant.bind()
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { Surface {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) { AssistantTaskCard(entry, f.cloud, false, {}) }
        } } } }
        // Task was already classified expired; no active candidate actions survive.
        compose.onNodeWithTag("ai-candidate-${entry.requestId}-0").assertDoesNotExist()
        compose.onNodeWithTag("ai-confirm-${entry.requestId}").assertDoesNotExist()
        compose.onNodeWithTag("ai-recover-${entry.requestId}").assertExists()
    }

    @Test fun blockedPlanningReviewNeverOffersAutomaticCommit() {
        val f = ResultsFixture()
        val review = JSONObject().put("status", "blocked").put("blockers", JSONArray().put("AUTOMATIC_PLANNING_NOT_APPROVED"))
        compose.setContent { AppLanguageProvider("zh-CN") { TeamAppTheme(darkTheme = false) { Surface {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                AgentResultCards(JSONObject().put("planning_review", review), { _, _ -> }, {})
            }
        } } } }
        compose.onNodeWithText("仍缺少必要资料，暂不能自动提交").assertExists()
        compose.onNodeWithText("自动补货提交尚未开放").assertExists()
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        val folder = instrumentation.targetContext.cacheDir.resolve("assistant-results-review").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
