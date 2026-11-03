package com.example.teamapp

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.ContextWrapper
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.AssistantComposer
import com.example.teamapp.ui.Chat
import com.example.teamapp.ui.CloudAssistant
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.CompletableDeferred
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/** Isolated preferences and in-memory transport: no user data or live server writes. */
@RunWith(AndroidJUnit4::class)
class AssistantComposerTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private var value by mutableStateOf(TextFieldValue())
    private var sending by mutableStateOf(false)
    private var enabled by mutableStateOf(true)
    private var sends = 0
    private var voiceError = ""
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    private fun editor(dark: Boolean = false, fontScale: Float = 1f) {
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale)) {
                TeamAppTheme(darkTheme = dark) {
                    Surface {
                        Box(Modifier.fillMaxSize().navigationBarsPadding().imePadding().padding(16.dp)) {
                            AssistantComposer(value, { value = it }, { sends++; sending = true }, { voiceError = it },
                                Modifier.widthIn(max = 320.dp).align(Alignment.BottomCenter), enabled, sending)
                        }
                    }
                }
            }
        }
    }

    private fun bounds() = compose.onNodeWithTag("ai-composer").fetchSemanticsNode().boundsInRoot
    private fun shot(name: String) {
        compose.waitForIdle()
        instrumentation.waitForIdleSync()
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val file = context.cacheDir.resolve("assistant-composer/$name.png")
        file.parentFile!!.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
    private fun isolatedContext(): ContextWrapper {
        val prefix = "composer_${UUID.randomUUID()}_"
        return object : ContextWrapper(context) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
    }

    private fun shell(command: String): String = instrumentation.uiAutomation.executeShellCommand(command).use { fd ->
        java.io.FileInputStream(fd.fileDescriptor).bufferedReader().use { it.readText() }.trim()
    }

    @Test fun reducedMotionUsesSystemScaleAndChangesHeightWithoutTween() {
        val original = shell("settings get global animator_duration_scale")
        try {
            shell("settings put global animator_duration_scale 0")
            editor()
            compose.mainClock.autoAdvance = false
            compose.runOnIdle { value = TextFieldValue("一\n二\n三\n四") }
            compose.mainClock.advanceTimeByFrame()
            compose.mainClock.advanceTimeByFrame()
            val immediate = bounds()
            compose.mainClock.advanceTimeBy(300)
            assertTrue(immediate.height > 56f * compose.activity.resources.displayMetrics.density)
            assertEquals("Reduced motion reaches its final height in the first layout frames", immediate.height, bounds().height, 1f)
            compose.runOnIdle { value = TextFieldValue() }
            compose.mainClock.advanceTimeByFrame()
            compose.mainClock.advanceTimeByFrame()
            compose.onNodeWithTag("ai-composer").assertHeightIsEqualTo(56.dp)
        } finally {
            compose.mainClock.autoAdvance = true
            shell(if (original == "null") "settings delete global animator_duration_scale" else "settings put global animator_duration_scale $original")
        }
    }

    @Test fun whitespaceAndComposingTextCannotSendButCommittedTextCan() {
        editor()
        compose.onNodeWithTag("ai-send").assertIsNotEnabled()
        compose.runOnIdle { value = TextFieldValue(" \n　 ") }
        compose.onNodeWithTag("ai-send").assertIsNotEnabled()
        compose.runOnIdle { value = TextFieldValue("ni", TextRange(2), TextRange(0, 2)) }
        compose.onNodeWithTag("ai-send").assertIsNotEnabled()
        compose.runOnIdle { value = TextFieldValue("你好", TextRange(2)) }
        compose.onNodeWithTag("ai-send").assertIsEnabled().assertWidthIsEqualTo(48.dp).assertHeightIsEqualTo(48.dp)
        compose.onNodeWithTag("ai-voice").assertWidthIsEqualTo(48.dp).assertHeightIsEqualTo(48.dp)
        compose.onNodeWithContentDescription("发送消息").performClick()
        compose.onNodeWithTag("ai-send").assertIsNotEnabled()
        compose.onNodeWithTag("ai-voice").assertIsNotEnabled()
        compose.runOnIdle { assertEquals(1, sends); assertEquals("你好", value.text) }
    }

    @Test fun multilineCapsAtFourLinesAndInterruptsWithoutMovingItsBottom() {
        editor()
        compose.onNodeWithTag("ai-composer").assertHeightIsEqualTo(56.dp)
        val initial = bounds()
        compose.runOnIdle { value = TextFieldValue("一\n二\n三\n四") }
        val four = bounds()
        assertTrue(four.height > initial.height)
        assertEquals(initial.bottom, four.bottom, 1f)
        compose.runOnIdle { value = TextFieldValue("一\n二\n三\n四\n五\n六\n七\n八") }
        val overflow = bounds()
        assertEquals(four.height, overflow.height, 1f)
        compose.mainClock.autoAdvance = false
        compose.runOnIdle { value = TextFieldValue("短") }
        compose.mainClock.advanceTimeBy(64)
        compose.runOnIdle { value = TextFieldValue("一\n二\n三") }
        compose.mainClock.advanceTimeBy(48)
        compose.runOnIdle { value = TextFieldValue() }
        compose.mainClock.advanceTimeBy(300)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithTag("ai-composer").assertHeightIsEqualTo(56.dp)
        assertEquals(initial.bottom, bounds().bottom, 1f)
        shot("light-empty")
    }

    @Test fun largeTypeOnSmallWidthRetainsTextAndButtonsInDarkMode() {
        editor(dark = true, fontScale = 2f)
        compose.runOnIdle { value = TextFieldValue("一\n二\n三\n四\n五") }
        compose.onNodeWithTag("ai-input").assertTextContains(value.text)
        compose.onNodeWithTag("ai-send").assertIsDisplayed().assertIsEnabled().assertWidthIsEqualTo(48.dp)
        compose.onNodeWithTag("ai-voice").assertIsDisplayed().assertWidthIsEqualTo(48.dp)
        val field = compose.onNodeWithTag("ai-input").fetchSemanticsNode().boundsInRoot
        val voice = compose.onNodeWithTag("ai-voice").fetchSemanticsNode().boundsInRoot
        assertTrue(field.width > 0f)
        assertTrue(field.right <= voice.left)
        shot("dark-large-type")
    }

    @Test fun keyboardOpenCloseAndTextResizeKeepFocusAndDraft() {
        compose.runOnUiThread {
            compose.activity.enableEdgeToEdge()
            compose.activity.window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        editor()
        compose.onNodeWithTag("ai-input").performClick().performTextInput("保留草稿")
        compose.onNodeWithTag("ai-input").assertIsFocused()
        compose.runOnIdle { value = value.copy(text = "第一行\n第二行\n第三行", selection = TextRange(11)) }
        compose.onNodeWithTag("ai-input").assertIsFocused()
        val before = value.text
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.waitForIdle()
        compose.onNodeWithTag("ai-input").assertTextContains(before)
        compose.onNodeWithTag("ai-input").performClick()
        compose.onNodeWithTag("ai-input").assertIsFocused().assertTextContains(before)
        shot("keyboard-multiline")
    }

    @Test fun curtainKeyboardUsesOneInsetAndPreservesDraftOnClose() {
        val store = InventoryStore(isolatedContext())
        compose.runOnUiThread {
            compose.activity.enableEdgeToEdge()
            compose.activity.window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("assistant-pull-cord").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.waitUntil(5_000) {
            compose.onAllNodes(hasTestTag("assistant-curtain") and hasStateDescription("已展开")).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("ai-input").performClick().performTextInput("键盘开合草稿")
        fun insets() = androidx.core.view.ViewCompat.getRootWindowInsets(compose.activity.window.decorView)
        compose.waitUntil(5_000) { insets()?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) == true }
        compose.waitForIdle()
        val originalInsets = insets()!!
        val nativeIme = originalInsets.getInsets(androidx.core.view.WindowInsetsCompat.Type.ime()).bottom
        val rootHeight = compose.activity.window.decorView.height
        // MuMu's Sogou IME is floating (visible with zero bottom inset). Exercise
        // docked-keyboard geometry with real Android inset dispatch on that device.
        val ime = nativeIme.takeIf { it > 0 } ?: (rootHeight * .36f).toInt()
        if (nativeIme == 0) compose.runOnUiThread {
            val docked = androidx.core.view.WindowInsetsCompat.Builder(originalInsets)
                .setInsets(androidx.core.view.WindowInsetsCompat.Type.ime(), androidx.core.graphics.Insets.of(0, 0, 0, ime))
                .setVisible(androidx.core.view.WindowInsetsCompat.Type.ime(), true).build()
            androidx.core.view.ViewCompat.dispatchApplyWindowInsets(compose.activity.window.decorView, docked)
        }
        compose.waitUntil(5_000) { bounds().bottom <= rootHeight - ime + 1f }
        val bottom = bounds().bottom
        val density = compose.activity.resources.displayMetrics.density
        println("COMPOSER_IME rootHeight=$rootHeight imeHeight=$ime composerBottom=$bottom")
        assertTrue("Composer remains above the actual IME", bottom <= rootHeight - ime + 1f)
        assertTrue("IME is not padded twice", rootHeight - ime - bottom < 32f * density)
        compose.onNodeWithTag("ai-input").assertIsFocused()
        shot(if (nativeIme > 0) "curtain-keyboard" else "curtain-keyboard-simulated")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        if (nativeIme == 0) compose.runOnUiThread {
            androidx.core.view.ViewCompat.dispatchApplyWindowInsets(compose.activity.window.decorView,
                androidx.core.view.WindowInsetsCompat.Builder(originalInsets)
                    .setInsets(androidx.core.view.WindowInsetsCompat.Type.ime(), androidx.core.graphics.Insets.NONE)
                    .setVisible(androidx.core.view.WindowInsetsCompat.Type.ime(), false).build())
        }
        compose.waitUntil(5_000) { insets()?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) == false }
        compose.onNodeWithTag("ai-input").assertTextContains("键盘开合草稿")
        shot("curtain-draft")
    }

    @Test fun systemVoiceCancellationPreservesDraftAndResultOnlyFillsText() {
        editor()
        compose.runOnIdle { value = TextFieldValue("原始草稿") }
        val cancel = instrumentation.addMonitor(IntentFilter(RecognizerIntent.ACTION_RECOGNIZE_SPEECH), ActivityResult(Activity.RESULT_CANCELED, null), true)
        try {
            compose.onNodeWithTag("ai-voice").performClick()
            compose.waitUntil(5_000) { cancel.hits > 0 }
            compose.onNodeWithTag("ai-voice").assertIsEnabled()
            compose.onNodeWithTag("ai-input").assertTextContains("原始草稿")
        } finally { instrumentation.removeMonitor(cancel) }
        val intent = Intent().putStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS, arrayListOf("语音转写原文"))
        val success = instrumentation.addMonitor(IntentFilter(RecognizerIntent.ACTION_RECOGNIZE_SPEECH), ActivityResult(Activity.RESULT_OK, intent), true)
        try {
            compose.onNodeWithTag("ai-voice").performClick()
            compose.waitUntil(5_000) { success.hits > 0 }
            compose.onNodeWithTag("ai-input").assertTextContains("语音转写原文")
            compose.runOnIdle { assertEquals(0, sends); assertTrue(voiceError.isBlank()) }
        } finally { instrumentation.removeMonitor(success) }
    }

    @Test fun guestSendClearsOnlyAfterLocalAnswerAndKeepsInputFocus() {
        val store = InventoryStore(isolatedContext())
        compose.setContent { TeamAppTheme(darkTheme = false) { Surface { Chat(store, remember { mutableStateListOf() }, "", {}, {}) } } }
        compose.onNodeWithTag("ai-input").performClick().performTextInput("家里有什么？")
        compose.onNodeWithTag("ai-send").performClick()
        compose.onNodeWithTag("ai-input").assertTextEquals("").assertIsFocused()
        compose.onNodeWithTag("ai-composer").assertHeightIsEqualTo(56.dp)
        shot("light-guest-sent")
    }

    private fun cloud(fake: ComposerAgent): AssistantStore {
        val isolated = isolatedContext()
        CloudCredentials(isolated).save(CloudAccount(BuildConfig.CLOUD_API_URL, "offline-composer", USER, "测试", HOME))
        val cloud = CloudStore(isolated)
        val assistant = AssistantStore(isolated, cloud, { fake }, {})
        compose.setContent { TeamAppTheme(darkTheme = false) { Surface { CloudAssistant(cloud, assistant = assistant) } } }
        compose.waitUntil(5_000) { assistant.capabilities != "{}" && !assistant.busy }
        return assistant
    }

    @Test fun cloudSuccessClearsDraftAndRapidTapsCreateOneRequest() {
        val fake = ComposerAgent()
        val assistant = cloud(fake)
        compose.onNodeWithTag("ai-input").performTextInput("查询库存")
        // Exercise two accessibility actions before a recomposition updates enabled state.
        compose.onNodeWithTag("ai-send").performSemanticsAction(SemanticsActions.OnClick) { click -> click(); click() }
        compose.waitUntil(5_000) { fake.posts == 1 }
        compose.onNodeWithTag("ai-send").assertIsNotEnabled()
        compose.onNodeWithTag("ai-input").assertTextContains("查询库存")
        compose.runOnIdle { fake.release.complete(Unit) }
        compose.waitUntil(5_000) { !assistant.busy }
        compose.onNodeWithTag("ai-input").assertTextEquals("")
        compose.runOnIdle { assertEquals(1, fake.posts); assertTrue(assistant.error.isBlank()) }
        shot("cloud-success")
    }

    @Test fun cloudFailureRetainsDraftAndAllowsEditing() {
        val fake = ComposerAgent(reject = true)
        val assistant = cloud(fake)
        compose.onNodeWithTag("ai-input").performTextInput("不要丢掉这条草稿")
        compose.onNodeWithTag("ai-send").performClick()
        compose.waitUntil(5_000) { fake.posts == 1 }
        compose.runOnIdle { fake.release.complete(Unit) }
        compose.waitUntil(5_000) { !assistant.busy && assistant.error.isNotBlank() }
        compose.onNodeWithTag("ai-input").assertTextContains("不要丢掉这条草稿")
        compose.onNodeWithTag("ai-send").assertIsEnabled()
        compose.onNodeWithTag("ai-input").performTextInput("，继续编辑")
        compose.onNodeWithTag("ai-input").assertTextContains("继续编辑", substring = true)
        shot("cloud-failure-draft")
    }

    @Test fun editsMadeWhileSendingSurviveSuccessfulReply() {
        val fake = ComposerAgent()
        val assistant = cloud(fake)
        compose.onNodeWithTag("ai-input").performTextInput("查询库存")
        compose.onNodeWithTag("ai-send").performClick()
        compose.waitUntil(5_000) { fake.posts == 1 }
        compose.onNodeWithTag("ai-input").performTextReplacement("下一条草稿")
        compose.runOnIdle { fake.release.complete(Unit) }
        compose.waitUntil(5_000) { !assistant.busy }
        compose.onNodeWithTag("ai-input").assertTextContains("下一条草稿")
        compose.onNodeWithTag("ai-send").assertIsEnabled()
    }

    private class ComposerAgent(private val reject: Boolean = false) : AgentClient(BuildConfig.CLOUD_API_URL, "never-used") {
        var posts = 0
        val release = CompletableDeferred<Unit>()
        override suspend fun capabilities() = JSONObject().put("conversation_memory_protocol", "conversation-memory-1").put("actions", JSONObject())
        override suspend fun currentConversation(householdId: String, cursor: String?) = JSONObject()
            .put("protocol_version", "conversation-memory-1").put("household_id", HOME).put("conversation_id", CONVERSATION)
            .put("conversation_revision", 0).put("requires_reset", false).put("messages", JSONArray()).put("active_task", JSONObject.NULL)
        override suspend fun conversationTurn(body: JSONObject): JSONObject {
            posts++
            release.await()
            if (reject) throw CloudFailure(422, "测试发送失败；草稿应保留", "INVALID_REQUEST")
            return JSONObject().put("protocol_version", "conversation-memory-1").put("request_id", body.getString("request_id"))
                .put("original_text", body.getString("text")).put("conversation_id", CONVERSATION)
                .put("conversation_revision", 1).put("current_conversation_revision", 1).put("inventory_written", false)
                .put("reply", "测试回复").put("kind", "explain").put("task", JSONObject.NULL).put("active_task", JSONObject.NULL).put("model_calls", 1)
        }
    }

    companion object {
        private const val USER = "00000000-0000-4000-8000-000000000001"
        private const val HOME = "00000000-0000-4000-8000-000000000002"
        private const val CONVERSATION = "00000000-0000-4000-8000-000000000003"
    }
}
