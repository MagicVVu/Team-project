package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.*
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/** Theme changes must preserve scene identity, including the real navigation and modal routes. */
class MewConsistencyTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private val dark = mutableStateOf(false)
    private val auth = mutableStateOf(false)

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("mew_consistency_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        store.saveItem(StockItem(name = "核对牛奶", quantity = 1.0, unit = "盒", minimum = 3.0, location = "冰箱"))
    }

    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }

    private fun launch(login: Boolean = false) {
        auth.value = login
        compose.setContent {
            TeamAppTheme(darkTheme = dark.value) {
                if (auth.value) AuthScreen { auth.value = false } else MagicApp(store)
            }
        }
    }

    private fun mode(value: Boolean) { compose.runOnIdle { dark.value = value }; compose.waitForIdle() }
    private fun tab(label: String) {
        compose.onAllNodesWithText(label, useUnmergedTree = true).onLast().performClick()
        compose.waitForIdle()
    }
    private fun hasPose(pose: MewPose) = SemanticsMatcher.expectValue(MewPoseKey, pose.name)
    private fun poseAt(description: String, pose: MewPose) {
        compose.onNodeWithContentDescription(description, useUnmergedTree = true).assert(hasPose(pose))
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val folder = context.cacheDir.resolve("mew-unification").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun navigationProfileShoppingAndCurtainKeepTheirPosesAcrossThemes() {
        launch()
        for (isDark in listOf(false, true)) {
            mode(isDark)
            val prefix = if (isDark) "dark" else "light"
            tab("首页")
            compose.onAllNodes(hasPose(MewPose.Overview), useUnmergedTree = true).assertCountEquals(1)
            shot("$prefix-home")
            tab("清单")
            compose.onAllNodes(hasPose(MewPose.Shopping), useUnmergedTree = true).assertCountEquals(1)
            compose.onAllNodes(hasPose(MewPose.Empty), useUnmergedTree = true).assertCountEquals(1)
            val title = compose.onNodeWithText("慢慢补齐").fetchSemanticsNode().boundsInRoot
            val cord = compose.onNodeWithTag("assistant-pull-cord").fetchSemanticsNode().boundsInRoot
            assertTrue("Shopping introduction stays clear of the hanging mascot", title.right < cord.left)
            shot("$prefix-shopping")
            tab("我的")
            poseAt("Mew 个人资料", MewPose.Overview)
            shot("$prefix-profile")
            tab("库存")
            compose.onNodeWithTag("assistant-pull-cord").performTouchInput {
                val start = Offset(width / 2f, height * .7f)
                swipe(start, start + Offset(0f, height * 2f), 500)
            }
            compose.onNodeWithTag("assistant-ip").assert(hasPose(MewPose.Thinking))
            shot("$prefix-assistant")
            mode(!isDark)
            compose.onNodeWithTag("assistant-ip").assert(hasPose(MewPose.Thinking))
            compose.onNodeWithTag("assistant-close").performClick()
        }
    }

    @Test fun loginRegistrationAndAboutUseTheSameIdentityInBothThemes() {
        launch(login = true)
        for (isDark in listOf(false, true)) {
            mode(isDark)
            val prefix = if (isDark) "dark" else "light"
            compose.onNodeWithText("先逛逛 ›").performScrollTo()
            poseAt("Mew 陪你记录生活", MewPose.Welcome)
            shot("$prefix-login")
            compose.onNodeWithText("去注册").performScrollTo().performClick()
            poseAt("Mew 陪你记录生活", MewPose.Welcome)
            compose.onNodeWithText("去登录").performScrollTo().performClick()
        }
        compose.runOnIdle { auth.value = false }
        tab("我的")
        compose.onNodeWithText("关于 Mewstow").performScrollTo().performClick()
        for (isDark in listOf(false, true)) {
            mode(isDark)
            poseAt("Mew · Nekomata 猫又", MewPose.Overview)
            shot("${if (isDark) "dark" else "light"}-about")
        }
    }

    @Test fun addMethodsKeepListeningAndConfirmationDistinctAcrossThemes() {
        launch()
        for (isDark in listOf(false, true)) {
            mode(isDark)
            val prefix = if (isDark) "dark" else "light"
            for ((mode, pose) in listOf("拍照添加" to MewPose.Confirming, "语音添加" to MewPose.Listening)) {
                compose.onNodeWithText(mode).performScrollTo().performClick()
                compose.onAllNodes(hasPose(pose), useUnmergedTree = true).assertCountEquals(1)
                shot("$prefix-${pose.name.lowercase()}")
                if (mode == "拍照添加") compose.onNodeWithTag("photo-close").performClick()
                else compose.onNodeWithText("关闭").performClick()
            }
        }
    }
}
