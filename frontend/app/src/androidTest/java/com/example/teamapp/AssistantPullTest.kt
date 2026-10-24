package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.unit.dp
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.espresso.Espresso
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.data.StockItem
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.*
import org.junit.runner.RunWith

/** All records belong to isolated test preferences, never the user's inventory. */
@RunWith(AndroidJUnit4::class)
class AssistantPullTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("assistant_pull_test_$name", mode)
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        store.saveItem(StockItem(name = "测试纯牛奶", quantity = 1.0, unit = "盒", location = "冰箱", minimum = 3.0))
    }

    @After fun cleanup() { context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit() }
    private fun launch(dark: Boolean = false) { compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } } }
    private fun pull(factor: Float) {
        compose.onNodeWithTag("assistant-pull-cord").performTouchInput {
            val start = Offset(width / 2f, height * .7f)
            swipe(start, start + Offset(0f, height * factor), 500)
        }
        compose.waitForIdle()
    }
    private fun shot(name: String) {
        compose.waitForIdle()
        // The emulator may present the previous transition frame after Compose is idle.
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        android.os.SystemClock.sleep(500)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val file = context.cacheDir.resolve("assistant-pull/$name.png")
        file.parentFile!!.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    private fun checkTabs(dark: Boolean) {
        launch(dark)
        compose.onNodeWithTag("app-top-bar").assertHeightIsEqualTo(56.dp)
        compose.onNodeWithContentDescription("个人中心").assertDoesNotExist()
        val homeNotification = compose.onNodeWithTag("app-top-bar-notifications").fetchSemanticsNode().boundsInRoot
        val homeTitle = compose.onNodeWithTag("app-top-bar-title").fetchSemanticsNode().boundsInRoot
        compose.onNodeWithTag("app-top-bar-icon").assertDoesNotExist()
        var pageTitleLeft: Float? = null
        shot("${if (dark) "dark" else "light"}-home-header")
        compose.onNodeWithTag("assistant-pull-cord").assertDoesNotExist()
        for (tab in listOf("库存", "清单", "我的")) {
            compose.onNodeWithText(tab, useUnmergedTree = true).performClick()
            compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
            val bar = compose.onNodeWithTag("app-top-bar").fetchSemanticsNode().boundsInRoot
            compose.onNodeWithTag("app-top-bar").assertHeightIsEqualTo(56.dp)
            compose.onNodeWithTag("app-top-bar-icon").assertIsDisplayed()
            val notification = compose.onNodeWithTag("app-top-bar-notifications").fetchSemanticsNode().boundsInRoot
            val title = compose.onNodeWithTag("app-top-bar-title").fetchSemanticsNode().boundsInRoot
            Assert.assertEquals(homeNotification, notification)
            Assert.assertTrue("Home wordmark starts before the other pages' icon/title pairs", title.left > homeTitle.left)
            pageTitleLeft?.let { Assert.assertEquals(it, title.left, 1f) }
            pageTitleLeft = title.left
            compose.onNodeWithContentDescription("库存提醒").performClick()
            compose.onNodeWithText("关闭").performClick()
            val cord = compose.onNodeWithTag("assistant-pull-cord").fetchSemanticsNode().boundsInRoot
            Assert.assertEquals("Cord starts at the app bar's lower edge", bar.bottom, cord.top, 1f)
            shot("${if (dark) "dark" else "light"}-$tab-cord")
            pull(.3f)
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            pull(2f)
            compose.onNodeWithTag("assistant-curtain").assertIsDisplayed()
            compose.onNodeWithTag("assistant-ip").assertIsDisplayed()
            compose.onNodeWithText("首页").assertDoesNotExist()
            val curtain = compose.onNodeWithTag("assistant-curtain").fetchSemanticsNode().boundsInRoot
            val root = compose.onRoot().fetchSemanticsNode().boundsInRoot
            Assert.assertEquals(root.width, curtain.width, 1f)
            Assert.assertEquals(root.height, curtain.height, 1f)
            shot("${if (dark) "dark" else "light"}-$tab")
            compose.onNodeWithTag("assistant-close").performClick()
            compose.waitForIdle()
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
        }
        pull(2f)
        Espresso.pressBack()
        compose.waitForIdle()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
    }

    @Test fun lightPullThresholdAndCoverageWorkAcrossAllThreeTabs() { checkTabs(false) }
    @Test fun darkPullThresholdAndCoverageWorkAcrossAllThreeTabs() { checkTabs(true) }
    @Test fun activationRetainsCordRecoilAndPaperHasOneDampedImpact() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        val restHeight = compose.onNodeWithTag("assistant-cord-recoil").fetchSemanticsNode().boundsInRoot.height
        val pixelsPerDp = context.resources.displayMetrics.density
        val fullHeight = compose.onRoot().fetchSemanticsNode().boundsInRoot.height
        compose.mainClock.autoAdvance = false
        compose.onNodeWithTag("assistant-pull-cord").performTouchInput {
            val start = Offset(width / 2f, height * .7f)
            swipe(start, start + Offset(0f, 110f * pixelsPerDp), 500)
        }
        var minimumCordHeight = restHeight
        val edges = mutableListOf<Float>()
        val surfaceHeights = mutableListOf<Float>()
        repeat(75) { frame ->
            compose.mainClock.advanceTimeBy(16)
            edges += compose.onNodeWithTag("assistant-curtain").fetchSemanticsNode().boundsInRoot.bottom
            surfaceHeights += compose.onNodeWithTag("assistant-impact-surface").fetchSemanticsNode().boundsInRoot.height
            if (frame < 20) {
                minimumCordHeight = minOf(minimumCordHeight,
                    compose.onNodeWithTag("assistant-cord-recoil").fetchSemanticsNode().boundsInRoot.height)
            }
        }
        Assert.assertTrue("Activated cord stays mounted through its overshoot", minimumCordHeight < restHeight - 1f)
        Assert.assertTrue("Paper descends while the cord starts recoiling", edges[5] > fullHeight * .01f)
        val firstLanding = edges.indexOfFirst { it > fullHeight - pixelsPerDp }
        Assert.assertTrue("Gravity fall lands around 472ms plus startup frames", firstLanding in 28..32)
        Assert.assertTrue("Descent accelerates after release", edges[14] - edges[7] > edges[7] - edges[0])
        Assert.assertTrue("Descent keeps accelerating toward landing", edges[22] - edges[17] > edges[17] - edges[12])
        val lifts = edges.drop(firstLanding).map { fullHeight - it }
        Assert.assertTrue("Impact rebounds only a few physical pixels", lifts.max() in 6f..11f)
        val rising = lifts.zipWithNext().count { (previous, next) -> previous <= 1f && next > 1f }
        Assert.assertEquals("One rebound without sustained oscillation", 1, rising)
        Assert.assertTrue("Collision briefly compresses the sheet",
            surfaceHeights.subList(firstLanding, firstLanding + 4).min() < fullHeight * .998f)
        // During descent bounds are clipped by the screen; inspect deformation only after contact.
        Assert.assertTrue("Collision deformation stays below one percent",
            surfaceHeights.drop(firstLanding).min() >= fullHeight * .99f)
        Assert.assertEquals("Paper settles within 740ms including startup", fullHeight, edges[45], 1f)
        Assert.assertEquals("Compression fully recovers", fullHeight, surfaceHeights.last(), 1f)
        Assert.assertEquals("Paper settles with full coverage", fullHeight, edges.last(), 1f)
        compose.onNodeWithTag("assistant-cord-recoil").assertDoesNotExist()
        compose.mainClock.autoAdvance = true
    }
    @Test fun fallingCurtainCanBeDismissedAndOpenedAgain() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.waitForIdle()
        repeat(3) {
            compose.mainClock.autoAdvance = false
            compose.onNodeWithTag("assistant-pull-cord").performSemanticsAction(SemanticsActions.OnClick) { it() }
            compose.mainClock.advanceTimeBy(160)
            Espresso.pressBack()
            compose.mainClock.autoAdvance = true
            compose.waitForIdle()
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()
        }
        pull(2f)
        compose.onNodeWithTag("assistant-close").performClick()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
    }
    @Test fun recoilOvershootsAndScalesWithDistanceAndReleaseSpeed() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        val cord = compose.onNodeWithTag("assistant-pull-cord")
        val restHeight = cord.fetchSemanticsNode().boundsInRoot.height
        val pixelsPerDp = context.resources.displayMetrics.density
        compose.mainClock.autoAdvance = false
        fun recoil(distanceDp: Float, duration: Long): Float {
            cord.performTouchInput {
                val start = Offset(width / 2f, height * .7f)
                swipe(start, start + Offset(0f, distanceDp * pixelsPerDp), duration)
            }
            var minimum = restHeight
            repeat(100) {
                compose.mainClock.advanceTimeBy(16)
                minimum = minOf(minimum, cord.fetchSemanticsNode().boundsInRoot.height)
            }
            compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
            Assert.assertEquals("Spring settles back at its anchor", restHeight,
                cord.fetchSemanticsNode().boundsInRoot.height, 1f)
            return restHeight - minimum
        }
        val gentle = recoil(32f, 500)
        val deeper = recoil(64f, 500)
        val faster = recoil(64f, 120)
        Assert.assertTrue("Release must overshoot the resting position", gentle > 0f)
        Assert.assertTrue("A deeper pull has stronger recoil", deeper > gentle)
        Assert.assertTrue("A faster release has stronger recoil", faster > deeper)
        compose.mainClock.autoAdvance = true
    }
    @Test fun mascotExpressionTracksPullThresholdAndCanBeCancelled() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        val cord = compose.onNodeWithTag("assistant-pull-cord")
        val mascot = compose.onNodeWithTag("assistant-pull-mascot", useUnmergedTree = true)
        cord.assertWidthIsEqualTo(57.6.dp)
        mascot.assertIsDisplayed().assert(
            SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "睁眼待机"))
        val pixelsPerDp = context.resources.displayMetrics.density
        compose.mainClock.autoAdvance = false
        cord.performTouchInput {
            down(Offset(width / 2f, height * .8f))
            moveBy(Offset(0f, 96f * pixelsPerDp), 500)
        }
        compose.mainClock.advanceTimeBy(160)
        mascot.assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "闭眼微笑"))
        shot("light-mascot-ready")
        cord.performTouchInput { moveBy(Offset(0f, -60f * pixelsPerDp), 300) }
        compose.mainClock.advanceTimeBy(160)
        mascot.assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "睁眼待机"))
        cord.performTouchInput { up() }
        compose.mainClock.autoAdvance = true
        compose.waitForIdle()
        compose.onNodeWithTag("assistant-curtain").assertDoesNotExist()
        mascot.assertIsDisplayed()
    }

    @Test fun mascotSlidesDownOnEntryAndUpOnExitAndCanReverse() {
        launch()
        val pixelsPerDp = context.resources.displayMetrics.density
        compose.mainClock.autoAdvance = false
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.mainClock.advanceTimeBy(32)
        val appearance = compose.onNodeWithTag("assistant-cord-appearance")
        val firstTop = appearance.fetchSemanticsNode().boundsInRoot.top
        val anchor = compose.onNodeWithTag("app-top-bar").fetchSemanticsNode().boundsInRoot.bottom
        compose.mainClock.advanceTimeBy(112)
        val enteringTop = appearance.fetchSemanticsNode().boundsInRoot.top
        Assert.assertTrue("Cat emerges down from above its anchor", enteringTop > firstTop)
        Assert.assertTrue("Entrance takes more than one frame", enteringTop < anchor - pixelsPerDp)
        compose.mainClock.advanceTimeBy(400)
        Assert.assertEquals("Cat settles at the app bar", anchor,
            appearance.fetchSemanticsNode().boundsInRoot.top, 1f)

        compose.onNodeWithText("首页", useUnmergedTree = true).performClick()
        compose.mainClock.advanceTimeBy(112)
        val exitingTop = appearance.fetchSemanticsNode().boundsInRoot.top
        Assert.assertTrue("Cat moves up before removal", exitingTop < anchor - pixelsPerDp)
        compose.onNodeWithTag("assistant-pull-cord").assertDoesNotExist()

        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.mainClock.advanceTimeBy(16)
        val reversedTop = appearance.fetchSemanticsNode().boundsInRoot.top
        Assert.assertTrue("Reversing does not restart the cat off-screen",
            kotlin.math.abs(reversedTop - exitingTop) < 12f * pixelsPerDp)
        compose.mainClock.advanceTimeBy(500)
        Assert.assertEquals(anchor, appearance.fetchSemanticsNode().boundsInRoot.top, 1f)
        compose.onNodeWithTag("assistant-pull-cord").assertIsDisplayed()

        compose.onNodeWithText("首页", useUnmergedTree = true).performClick()
        compose.mainClock.advanceTimeBy(400)
        appearance.assertDoesNotExist()
        compose.mainClock.autoAdvance = true
    }

    @Test fun inventoryAnswerAndReplenishmentRequireConfirmation() {
        launch()
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        pull(2f)
        compose.onNodeWithText("补货建议").performClick()
        compose.onNodeWithText("测试纯牛奶：", substring = true).assertExists()
        compose.runOnIdle { Assert.assertTrue(store.purchases.isEmpty()) }
        compose.onNodeWithText("核对补货").performClick()
        compose.onNodeWithText("确认补货建议").assertIsDisplayed()
        compose.runOnIdle { Assert.assertTrue(store.purchases.isEmpty()) }
        compose.onNodeWithText("确认").performClick()
        compose.runOnIdle {
            Assert.assertEquals(2.0, store.purchases.single().quantity, 0.0)
            Assert.assertEquals(1.0, store.items.single().quantity, 0.0)
        }
    }
}
