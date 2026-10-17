package com.example.teamapp

import android.content.ContextWrapper
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.util.UUID

class AssistantExecutionUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val args get() = InstrumentationRegistry.getArguments()
    private lateinit var current: InventoryStore
    private lateinit var scenario: ActivityScenario<AssistantHarnessActivity>

    private fun start(dark: Boolean = false) {
        val url = args.getString("executionTestUrl").orEmpty()
        assumeTrue(url.isNotBlank() && !args.getString("fixturePhone").isNullOrBlank())
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val prefix = "p4ui_${UUID.randomUUID().toString().replace("-", "")}_"
        val context = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
        runBlocking {
            val h = CloudApi(url).request("GET", "/api/v1/health")
            assertTrue(h.getBoolean("isolated_test")); assertEquals("0.9.0", h.getString("version"))
            val cloud = CloudStore(context)
            cloud.login(url, args.getString("fixturePhone")!!, args.getString("fixturePassword")!!)
            cloud.selectHousehold(args.getString("fixtureHousehold")!!)
        }
        scenario = ActivityScenario.launch(Intent(target, AssistantHarnessActivity::class.java).putExtra("test_namespace", prefix).putExtra("dark", dark))
        scenario.onActivity { current = it.store }
        // Navigate to inventory to expose the existing cat pull cord.
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("assistant-pull-cord").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.OnClick)
        compose.waitUntil(30_000) { current.cloud.assistant.capabilities != "{}" && !current.cloud.assistant.busy }
    }
    private fun send(text: String): AssistantEntry {
        val size = current.cloud.assistant.entries.size
        compose.onNodeWithTag("ai-input").performTextInput(text)
        compose.onNodeWithTag("ai-send").performClick()
        compose.waitUntil(35_000) { current.cloud.assistant.entries.size > size && !current.cloud.assistant.busy }
        return current.cloud.assistant.entries.last()
    }
    private fun find(tag: String): SemanticsNodeInteraction {
        compose.onNodeWithTag("ai-tasks").performScrollToNode(hasTestTag(tag))
        return compose.onNodeWithTag(tag)
    }
    private fun confirm(entry: AssistantEntry) {
        find("ai-confirm-${entry.requestId}").performClick()
        compose.onNodeWithTag("ai-final-confirm").performClick()
        compose.waitUntil(35_000) { !current.cloud.assistant.busy && current.cloud.assistant.entries.single { it.requestId == entry.requestId }.state == AssistantStatus.COMMITTED }
        find("ai-receipt-${entry.requestId}").assertExists()
    }
    private fun screenshot(name: String) {
        compose.waitForIdle()
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val image = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val file = target.cacheDir.resolve("phase4/$name.png"); file.parentFile!!.mkdirs()
        file.outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }; image.recycle()
    }
    @Test fun fourActionsThroughRealCardsAndActivityRecreation() {
        start()
        try {
            val query = send("纸巾还有多少"); assertEquals(AssistantStatus.ANSWERED, query.state)
            compose.onNodeWithTag("ai-confirm-${query.requestId}").assertDoesNotExist()
            val add = send("添加2袋饼干"); assertEquals(AssistantStatus.PENDING, add.state)
            find("ai-edit-location-${add.requestId}").performTextReplacement("储物柜")
            // Close/reopen retains the exact draft and edited fields.
            compose.onNodeWithTag("assistant-close").performClick()
            compose.onNodeWithTag("assistant-pull-cord").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.OnClick)
            compose.waitUntil(30_000) { !current.cloud.assistant.busy }
            find("ai-edit-location-${add.requestId}").assertTextContains("储物柜")
            scenario.recreate(); scenario.onActivity { current = it.store }
            compose.waitUntil(30_000) { !current.cloud.assistant.busy && current.cloud.assistant.entries.any { it.requestId == add.requestId } }
            find("ai-edit-location-${add.requestId}").assertTextContains("储物柜")
            confirm(current.cloud.assistant.entries.single { it.requestId == add.requestId })
            val destination = if (current.items.single { it.name == "纸巾" }.location == "储藏室") "书房" else "储藏室"
            val move = send("把纸巾移到$destination"); assertEquals(listOf("to_location"), move.editableFields)
            confirm(move)
            val consume = send("纸巾消耗1包"); confirm(consume)
            val plan = send("采购清单加2包纸巾"); confirm(plan)
            screenshot("light-committed-receipt")
            val cancel = send("纸巾消耗1包")
            find("ai-cancel-${cancel.requestId}").performClick()
            compose.waitUntil(30_000) { !current.cloud.assistant.busy }
            assertEquals(AssistantStatus.CANCELLED, current.cloud.assistant.entries.last().state)
            compose.onNodeWithTag("ai-confirm-${cancel.requestId}").assertDoesNotExist()
        } finally { scenario.close() }
    }
    @Test fun darkThemeCandidatesSelectSecondAndUnsupportedHasNoConfirm() {
        start(dark = true)
        try {
            val clarification = send("牛奶消耗1盒")
            assertEquals(AssistantStatus.CLARIFICATION, clarification.state)
            find("ai-candidate-${clarification.requestId}-1").performClick()
            compose.waitUntil(30_000) { !current.cloud.assistant.busy }
            val draft = current.cloud.assistant.entries.last()
            assertEquals(clarification.taskId, draft.taskId); assertEquals(AssistantStatus.PENDING, draft.state)
            find("ai-cancel-${draft.requestId}").performClick(); compose.waitUntil(30_000) { !current.cloud.assistant.busy }
            val open = send("纸巾昨天开封"); assertEquals(AssistantStatus.UNSUPPORTED, open.state)
            compose.onNodeWithTag("ai-confirm-${open.requestId}").assertDoesNotExist()
            find("ai-state-${open.requestId}").assertTextEquals("暂不支持")
            screenshot("dark-unsupported")
        } finally { scenario.close() }
    }
    @Test fun existingLoginScreenAuthenticatesSyntheticAccount() {
        val url = args.getString("executionTestUrl").orEmpty()
        assumeTrue(url.isNotBlank())
        runBlocking {
            val health = CloudApi(url).request("GET", "/api/v1/health")
            assertTrue(health.getBoolean("isolated_test")); assertEquals("0.9.0", health.getString("version"))
        }
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val prefix = "p4ui_${UUID.randomUUID().toString().replace("-", "")}_"
        scenario = ActivityScenario.launch(Intent(target, AssistantHarnessActivity::class.java).putExtra("test_namespace", prefix).putExtra("auth_entry", true))
        try {
            scenario.onActivity { current = it.store }
            compose.onNodeWithTag("auth-server").performScrollTo().performTextReplacement(url)
            compose.onNodeWithTag("auth-phone").performScrollTo().performTextInput(args.getString("fixturePhone")!!)
            compose.onNodeWithTag("auth-password").performScrollTo().performTextInput(args.getString("fixturePassword")!!)
            compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
            compose.waitUntil(30_000) { current.cloud.signedIn && !current.cloud.busy }
            assertTrue(current.cloud.households.any { it.id == args.getString("fixtureHousehold") })
        } finally { scenario.close() }
    }
}
