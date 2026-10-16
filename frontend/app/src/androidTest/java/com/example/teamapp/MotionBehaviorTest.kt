package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.content.Intent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.espresso.Espresso
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.AppMotionContent
import com.example.teamapp.ui.AuthScreen
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise interrupted transitions against isolated records, without touching user preferences. */
@RunWith(AndroidJUnit4::class)
class MotionBehaviorTest {
    @get:Rule val compose = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private lateinit var context: Context
    private lateinit var store: InventoryStore

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("motion_behavior_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE).edit().clear().commit()
        store = InventoryStore(context)
        store.saveItem(StockItem(name = "动画测试牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0))
        store.saveItem(StockItem(name = "动画测试毛巾", quantity = 2.0, unit = "条", category = "日用品", location = "储物柜"))
    }

    @After fun cleanup() {
        compose.mainClock.autoAdvance = true
        val stopped = CountDownLatch(1)
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) stopped.countDown() }
        compose.runOnUiThread {
            compose.activity.lifecycle.addObserver(observer)
            compose.activity.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        stopped.await(5, TimeUnit.SECONDS)
        compose.runOnUiThread { compose.activity.lifecycle.removeObserver(observer) }
        context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE).edit().clear().commit()
    }

    private fun launch() {
        compose.setContent { TeamAppTheme(darkTheme = false) { MagicApp(store) } }
    }

    private fun SemanticsNodeInteraction.assertInput(value: String) =
        assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString(value)))

    @Test fun rapidTabChangesKeepInventorySearchAndFilters() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-search").performScrollTo().performTextInput("动画测试")
        compose.onNodeWithTag("ring-category-食品").performScrollTo().performClick()
        compose.onNodeWithTag("ring-attention").performScrollTo().performClick()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")

        compose.mainClock.autoAdvance = false
        for (tab in listOf("清单", "我的", "首页", "库存")) {
            compose.onNodeWithText(tab, useUnmergedTree = true).performClick()
            compose.mainClock.advanceTimeBy(48)
        }
        compose.mainClock.autoAdvance = true
        compose.waitForIdle()

        compose.onNodeWithTag("app-top-bar-title").assertTextEquals("我的库存")
        compose.onNodeWithTag("ring-search").assertInput("动画测试")
        compose.onNodeWithTag("ring-category-食品").assertIsSelected()
        compose.onNodeWithTag("ring-attention").assertIsOn()
        compose.onNodeWithTag("ring-position").assertTextEquals("1 / 1")
        compose.onNodeWithTag("ring-selected-info").assertContentDescriptionEquals("已选中物品：动画测试牛奶")
        compose.runOnIdle { assertEquals(2, store.items.size) }
    }

    @Test fun reversingAuthModeClearsPasswordsAndValidationWithoutLosingTypedEdits() {
        compose.setContent { TeamAppTheme(darkTheme = false) { AuthScreen {} } }
        compose.onNodeWithTag("auth-password").performScrollTo().performTextInput("green123456")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithText("请输入大陆 11 位手机号或带国家码的号码").assertExists()
        compose.onNodeWithTag("auth-phone").performScrollTo().performTextInput("13800138000")
        compose.onNodeWithText("请输入大陆 11 位手机号或带国家码的号码").assertDoesNotExist()
        compose.onNodeWithText("显示").performClick()
        compose.onNodeWithTag("auth-password").assertInput("green123456")
        compose.onNodeWithText("隐藏").performClick()
        compose.onNodeWithText("去注册").performScrollTo()

        compose.mainClock.autoAdvance = false
        compose.onNodeWithText("去注册").performClick()
        compose.mainClock.advanceTimeBy(64)
        compose.onNodeWithTag("auth-password").assertInput("")
        Espresso.pressBack()
        compose.mainClock.advanceTimeBy(64)
        compose.mainClock.autoAdvance = true
        compose.waitForIdle()

        compose.onNodeWithTag("auth-password").assertInput("")
        compose.onNodeWithTag("auth-nickname").assertDoesNotExist()
        compose.onNodeWithText("请输入大陆 11 位手机号或带国家码的号码").assertDoesNotExist()
        compose.onNodeWithTag("auth-phone").performScrollTo().performTextInput("13900139000")
        compose.onNodeWithTag("auth-password").performScrollTo().performTextInput("fresh123")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithTag("auth-service-notice").assertExists()
    }

    @Test fun closingAndReopeningAnAddPanelDiscardsOnlyTheUnconfirmedDraft() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("物品名称 *").performTextInput("应丢弃的未确认项")

        compose.mainClock.autoAdvance = false
        compose.onNodeWithText("关闭").performClick()
        compose.mainClock.advanceTimeBy(64)
        // Closing starts immediately disabling form actions, before the sheet is removed.
        compose.onNodeWithText("物品名称 *").assertDoesNotExist()
        compose.mainClock.autoAdvance = true
        compose.waitForIdle()
        compose.runOnIdle { assertEquals(2, store.items.size) }

        compose.onNodeWithTag("ring-add").performClick()
        compose.onNodeWithText("物品名称 *").assertInput("").performTextInput("重新打开后保存")
        compose.onNodeWithText("数量 *").performScrollTo().performTextInput("1")
        compose.onNodeWithText("单位 *（如盒、袋、瓶、个）").performScrollTo().performTextInput("盒")
        compose.onNodeWithText("确认添加").performScrollTo().performClick()
        compose.waitForIdle()
        compose.onNodeWithText("关闭").assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(3, store.items.size)
            assertTrue(store.items.any { it.name == "重新打开后保存" })
            assertFalse(store.items.any { it.name == "应丢弃的未确认项" })
        }
    }

    @Test fun outgoingControlsStayComposedForExitButCannotReceiveTouch() {
        val showingNew = mutableStateOf(false)
        var outgoingDisposed = false
        var outgoingClicks = 0
        var incomingClicks = 0
        compose.setContent {
            TeamAppTheme(darkTheme = false) {
                AppMotionContent(showingNew.value, Modifier.fillMaxSize().testTag("motion-root")) { incoming ->
                    DisposableEffect(incoming) {
                        onDispose { if (!incoming) outgoingDisposed = true }
                    }
                    Box(Modifier.fillMaxSize().padding(24.dp)) {
                        Button(
                            onClick = { if (incoming) incomingClicks++ else outgoingClicks++ },
                            modifier = Modifier.align(if (incoming) Alignment.BottomEnd else Alignment.TopStart)
                                .testTag(if (incoming) "incoming-action" else "outgoing-action")
                        ) { Text(if (incoming) "新页面操作" else "旧页面操作") }
                    }
                }
            }
        }
        val oldCenter = compose.onNodeWithTag("outgoing-action").fetchSemanticsNode().boundsInRoot.center
        compose.mainClock.autoAdvance = false
        compose.runOnUiThread { showingNew.value = true }
        compose.mainClock.advanceTimeBy(64)
        compose.runOnIdle { assertFalse(outgoingDisposed) }
        compose.onNodeWithTag("outgoing-action").assertDoesNotExist()
        compose.onNodeWithTag("motion-root").performTouchInput { click(oldCenter) }
        compose.runOnIdle { assertEquals(0, outgoingClicks) }

        compose.mainClock.autoAdvance = true
        compose.waitForIdle()
        compose.runOnIdle { assertTrue(outgoingDisposed) }
        compose.onNodeWithTag("incoming-action").performClick()
        compose.runOnIdle { assertEquals(1, incomingClicks) }
    }

    @Test fun cancellingAssistantDuringCordRecoilRestoresPage() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
        val restHeight = compose.onNodeWithTag("assistant-pull-cord").fetchSemanticsNode().boundsInRoot.height
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("assistant-pull-cord").performTouchInput {
            val start = Offset(width / 2f, height * .7f)
            swipe(start, start + Offset(0f, height * 2f), 500)
        }
        compose.mainClock.advanceTimeBy(96)
        Espresso.pressBack()
        compose.mainClock.autoAdvance = true
        compose.waitForIdle()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
        compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
        assertEquals(restHeight, compose.onNodeWithTag("assistant-pull-cord").fetchSemanticsNode().boundsInRoot.height, 1f)
        compose.onNodeWithTag("app-top-bar-title").assertTextEquals("我的库存")
        compose.runOnIdle { assertEquals(2, store.items.size) }
    }

    @Test fun reversingAssistantEntranceKeepsItsExitUntilItFinishes() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("assistant-pull-cord").performSemanticsAction(SemanticsActions.OnClick) { it() }
        // Advance beyond the cord's recoil lead-in and interrupt the moving paper.
        compose.mainClock.advanceTimeBy(360)
        Espresso.pressBack()
        compose.mainClock.advanceTimeBy(32)
        compose.onNodeWithTag("assistant-curtain").assertExists()
        compose.onNodeWithTag("assistant-close").assertDoesNotExist()
        compose.onNodeWithTag("assistant-pull-cord").assertDoesNotExist()

        compose.mainClock.autoAdvance = true
        compose.waitForIdle()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
        compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
        compose.onNodeWithTag("app-top-bar-title").assertTextEquals("我的库存")
        compose.runOnIdle { assertEquals(2, store.items.size) }
    }
}
