package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.i18n.AppLanguageProvider
import com.example.teamapp.ui.ring.InventoryDetailContent
import com.example.teamapp.ui.theme.TeamAppTheme
import org.json.JSONArray
import org.json.JSONObject
import org.junit.*
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.ChronoUnit
import kotlin.math.abs

/** Isolated local storage and fake cached sign-in only; never connects to the live server. */
@RunWith(AndroidJUnit4::class)
class InventoryRecordActionsTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private lateinit var ids: List<String>
    private val item = StockItem(id = "record-melon", name = "西瓜", quantity = 3.0, unit = "个", location = "冰箱", expiry = "2026-10-26")
    private val names = listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")
    private fun preview() = store.inventoryPreviews.preview(store.inventoryPreviewScope, store.items.single())
    private fun recordTag(id: String) = "inventory-preview-record-$id"
    private fun actionTag(action: String, id: String) = "inventory-preview-action-$action-$id"

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences("record_actions_test_$name", mode)
        }
        names.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() }
        store = InventoryStore(context)
        store.saveItem(item)
        ids = preview().records.map { it.id }
        store.inventoryPreviews.updateRecord("local", item.id, ids[1], "冰箱", "2026-11-10", null)
        store.inventoryPreviews.updateRecord("local", item.id, ids[2], "冰箱", "2026-11-20", null)
    }
    @After fun cleanup() { names.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() } }

    private fun show(dark: Boolean = false, english: Boolean = false, width: Int = 360, height: Int = 640) {
        compose.setContent { AppLanguageProvider(if (english) "en" else "zh-CN") { TeamAppTheme(darkTheme = dark) {
            Box(Modifier.requiredSize(width.dp, height.dp)) { InventoryDetailContent(store, store.items.single(), {}, {}, { Modifier }) }
        } } }
    }
    private fun scrollTo(tag: String) { compose.onNodeWithTag("inventory-detail-content").performScrollToNode(hasTestTag(tag)) }
    private fun swipe(id: String) {
        scrollTo(recordTag(id))
        compose.onNodeWithTag(recordTag(id)).performTouchInput { swipeLeft(durationMillis = 250) }
        compose.onNodeWithTag(actionTag("edit", id)).assertIsEnabled()
    }
    private fun top() = compose.onNodeWithTag("inventory-detail-content").performScrollToIndex(0)
    private fun chooseDate(date: LocalDate) {
        // All callers in this test open an empty date field.
        compose.onNodeWithTag("inventory-receive-date-confirm").assertIsNotEnabled()
        val months = ChronoUnit.MONTHS.between(YearMonth.now(), YearMonth.from(date)).toInt()
        repeat(abs(months)) { compose.onNodeWithTag(if (months >= 0) "inventory-expiry-next" else "inventory-expiry-previous").performClick() }
        compose.onNodeWithTag("inventory-expiry-$date").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-receive-date-confirm").performClick()
    }

    @Test fun leftSwipeRevealsFixedActionsAndRightSwipeOrBodyTapClosesThem() {
        show()
        swipe(ids[0])
        val actions = listOf("edit", "open", "consume").map { compose.onNodeWithTag(actionTag(it, ids[0])).assertIsDisplayed().fetchSemanticsNode().boundsInRoot }
        Assert.assertTrue(actions[0].right <= actions[1].left && actions[1].right <= actions[2].left)
        screenshot("swipe-light")
        compose.onNodeWithTag(recordTag(ids[0])).performTouchInput { swipeRight(durationMillis = 250) }
        compose.onNodeWithTag(actionTag("edit", ids[0])).assertDoesNotExist()
        swipe(ids[0])
        compose.onNodeWithTag("inventory-preview-card-${ids[0]}").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.onNodeWithTag(actionTag("edit", ids[0])).assertDoesNotExist()
    }

    @Test fun shortSlowDragReturnsToOriginAndVerticalGestureDoesNotRevealActions() {
        show()
        scrollTo(recordTag(ids[0]))
        compose.onNodeWithTag(recordTag(ids[0])).performTouchInput {
            swipe(Offset(width * .8f, height * .4f), Offset(width * .7f, height * .4f), durationMillis = 700)
        }
        compose.onNodeWithTag(actionTag("edit", ids[0])).assertDoesNotExist()
        val row = compose.onNodeWithTag(recordTag(ids[0])).fetchSemanticsNode().boundsInRoot
        val card = compose.onNodeWithTag("inventory-preview-card-${ids[0]}").fetchSemanticsNode().boundsInRoot
        Assert.assertTrue(abs(row.left - card.left) < 2f)
        compose.onNodeWithTag(recordTag(ids[0])).performTouchInput { swipeUp(durationMillis = 400) }
        ids.forEach { compose.onNodeWithTag(actionTag("edit", it)).assertDoesNotExist() }
    }

    @Test fun openingAnotherRowClosesPreviousMenu() {
        show()
        swipe(ids[0]); swipe(ids[1])
        compose.onNodeWithTag(actionTag("edit", ids[0])).assertDoesNotExist()
        compose.onNodeWithTag(actionTag("edit", ids[1])).assertIsDisplayed()
    }

    @Test fun recordEditorChangesOnlySecondPieceAndPreservesIdentityAndParent() {
        val before = preview().records
        val saved = store.export()
        show()
        swipe(ids[1])
        compose.onNodeWithTag(actionTag("edit", ids[1])).performClick()
        compose.onNodeWithTag(actionTag("edit", ids[1])).assertDoesNotExist()
        compose.onNodeWithTag("inventory-preview-record-location").onChildren().filter(hasClickAction()).onFirst().performClick()
        compose.onNodeWithText("阳台").performClick()
        compose.onNodeWithTag("inventory-preview-record-clear-expiry").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-preview-record-expiry").performScrollTo().performClick()
        chooseDate(LocalDate.parse("2026-12-01"))
        compose.onNodeWithTag("inventory-preview-record-opened").performScrollTo().performClick()
        chooseDate(LocalDate.parse("2026-10-27"))
        compose.onNodeWithTag("inventory-preview-record-save").performClick()
        compose.onNodeWithTag("inventory-preview-record-editor").assertDoesNotExist()
        compose.runOnIdle {
            val after = preview().records
            Assert.assertEquals(before[0], after[0]); Assert.assertEquals(before[2], after[2])
            Assert.assertEquals(before[1].copy(location = "阳台", expiryDate = "2026-12-01", openedAt = "2026-10-27"), after[1])
            Assert.assertEquals(saved, store.export())
        }
    }

    @Test fun editorCancelPreservesDatesAndCanClearBothDateFieldsOnSave() {
        val before = preview().records
        show()
        swipe(ids[1]); compose.onNodeWithTag(actionTag("edit", ids[1])).performClick()
        compose.onNodeWithTag("inventory-preview-record-clear-expiry").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-preview-record-cancel").performClick()
        compose.runOnIdle { Assert.assertEquals(before, preview().records) }
        store.inventoryPreviews.markOpened("local", item.id, ids[1])
        swipe(ids[1]); compose.onNodeWithTag(actionTag("edit", ids[1])).performClick()
        compose.onNodeWithTag("inventory-preview-record-clear-expiry").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-preview-record-clear-opened").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-preview-record-save").performClick()
        compose.runOnIdle { Assert.assertNull(preview().records[1].expiryDate); Assert.assertNull(preview().records[1].openedAt) }
    }

    @Test fun openUsesDeviceDateOnceAndChangesOnlyTargetRecord() {
        val before = preview().records
        val saved = store.export()
        val today = LocalDate.now().toString()
        show()
        swipe(ids[0]); compose.onNodeWithTag(actionTag("open", ids[0])).performClick()
        compose.onNodeWithTag(actionTag("open", ids[0])).assertDoesNotExist()
        compose.runOnIdle {
            Assert.assertEquals(before[0].copy(openedAt = today), preview().records[0])
            Assert.assertEquals(before.drop(1), preview().records.drop(1))
            Assert.assertEquals(saved, store.export())
        }
        swipe(ids[0]); compose.onNodeWithTag(actionTag("open", ids[0])).assertTextEquals("已开封").assertIsNotEnabled()
    }

    @Test fun consumeWaitsForExitAnimationAndDoubleClickRemovesOnlyOneRecord() {
        val before = preview().records
        val saved = store.export()
        show()
        swipe(ids[1])
        val initialHeight = compose.onNodeWithTag(recordTag(ids[1])).fetchSemanticsNode().boundsInRoot.height
        compose.mainClock.autoAdvance = false
        try {
            compose.onNodeWithTag(actionTag("consume", ids[1])).performSemanticsAction(SemanticsActions.OnClick) { click -> click(); click() }
            compose.mainClock.advanceTimeBy(120)
            compose.runOnIdle { Assert.assertEquals(before, preview().records) }
            val during = compose.onNodeWithTag(recordTag(ids[1])).fetchSemanticsNode().boundsInRoot.height
            Assert.assertTrue("The row must visibly shrink before removal", during > 0f && during < initialHeight)
            screenshot("consume-mid")
            compose.mainClock.advanceTimeBy(850)
        } finally { compose.mainClock.autoAdvance = true }
        compose.onNodeWithTag(recordTag(ids[1])).assertDoesNotExist()
        compose.runOnIdle {
            Assert.assertEquals(listOf(before[0], before[2]), preview().records)
            Assert.assertEquals("2", preview().total.previewText())
            Assert.assertEquals(saved, store.export())
        }
        top(); compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2 个")
    }

    @Test fun consumingLastPieceShowsEmptyStateWithoutChangingPersistedStock() {
        ids.drop(1).forEach { store.inventoryPreviews.consumeRecord("local", item.id, it) }
        show()
        swipe(ids[0]); compose.onNodeWithTag(actionTag("consume", ids[0])).performClick()
        scrollTo("inventory-detail-empty-receive")
        compose.onNodeWithText("暂无单件库存记录").assertExists()
        top(); compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("0 个")
        Assert.assertEquals(3.0, store.items.single().quantity, 0.0)
        Assert.assertEquals(3.0, InventoryStore(context).items.single().quantity, 0.0)
    }

    @Test fun aggregateRecordHasNoIndividualActions() {
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        store.saveItem(item.copy(quantity = 2.5, unit = "kg"))
        val aggregate = preview().records.single()
        show()
        scrollTo(recordTag(aggregate.id))
        compose.onNodeWithTag(recordTag(aggregate.id)).performTouchInput { swipeLeft() }
        listOf("edit", "open", "consume").forEach { compose.onNodeWithTag(actionTag(it, aggregate.id)).assertDoesNotExist() }
        compose.runOnIdle { Assert.assertEquals("2.5", preview().total.previewText()) }
    }

    @Test fun englishDark320dpMenuKeepsThreeUsableButtonsAndEditor() {
        show(dark = true, english = true, width = 320, height = 480)
        swipe(ids[0])
        for (action in listOf("edit", "open", "consume")) {
            compose.onNodeWithTag(actionTag(action, ids[0])).assertIsDisplayed()
            val bounds = compose.onNodeWithTag(actionTag(action, ids[0])).fetchSemanticsNode().boundsInRoot
            val minimum = 48f * context.resources.displayMetrics.density
            Assert.assertTrue(bounds.width >= minimum && bounds.height >= minimum)
        }
        screenshot("swipe-dark-english-320")
        compose.onNodeWithTag(actionTag("edit", ids[0])).performClick()
        compose.onNodeWithTag("inventory-preview-record-save").assertIsDisplayed()
        screenshot("editor-dark-english-320")
        compose.onNodeWithTag("inventory-preview-record-cancel").performClick()
    }

    @Test fun cachedCloudModeRecordOperationsNeverChangeSavedStockCacheOrGuestState() {
        val account = CloudAccount(BuildConfig.CLOUD_API_URL, "fixture-token-never-used", "preview-user", "Preview", "preview-home")
        CloudCredentials(context).save(account)
        val cache = context.getSharedPreferences("magicvvu_cloud_cache", 0)
        cache.edit().putString("${account.address}|${account.userId}|${account.householdId}", JSONObject()
            .put("inventory", JSONArray().put(item.toCloudJson().put("version", 1))).put("shopping", JSONArray()).put("lastSync", "fixture").toString()).commit()
        store = InventoryStore(context)
        Assert.assertTrue(store.cloud.signedIn)
        ids = preview().records.map { it.id }
        val original = store.export()
        val persisted = names.associateWith { context.getSharedPreferences(it, 0).all.toMap() }
        show()
        swipe(ids[0]); compose.onNodeWithTag(actionTag("edit", ids[0])).performClick()
        compose.onNodeWithTag("inventory-preview-record-clear-expiry").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-preview-record-save").performClick()
        swipe(ids[0]); compose.onNodeWithTag(actionTag("open", ids[0])).performClick()
        swipe(ids[0]); compose.onNodeWithTag(actionTag("consume", ids[0])).performClick()
        top(); compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2 个")
        compose.onNodeWithTag("inventory-detail-saved-quantity").assertTextEquals("服务器已保存：3.0 个")
        compose.runOnIdle {
            Assert.assertEquals(original, store.export())
            Assert.assertEquals(persisted, names.associateWith { context.getSharedPreferences(it, 0).all.toMap() })
            Assert.assertEquals(3.0, InventoryStore(context).items.single().quantity, 0.0)
        }
    }

    @Test fun globalEditShoppingAndDeleteStillUseExistingPanels() {
        val originalRecords = preview().records
        compose.setContent { TeamAppTheme { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-edit").performClick()
        compose.onNodeWithText("物品名称 *").performTextReplacement("西瓜资料")
        compose.onNodeWithText("保存修改").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-detail-name").assertTextEquals("西瓜资料")
        compose.runOnIdle { Assert.assertEquals(originalRecords, preview().records) }
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
        scrollTo("inventory-detail-shopping"); compose.onNodeWithTag("inventory-detail-shopping").performClick()
        compose.onNodeWithText("加入采购清单").assertExists()
        compose.onNodeWithText("确认保存").performClick()
        compose.waitUntil(5_000) { store.purchases.any { it.itemId == item.id } }
        // The taller detail reaches the snackbar area; wait before tapping its bottom actions.
        compose.waitUntil(5_000) { compose.onAllNodesWithText("采购计划已保存").fetchSemanticsNodes().isNotEmpty() }
        compose.waitUntil(8_000) { compose.onAllNodesWithText("采购计划已保存").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("ring-selected-info").performClick()
        scrollTo("inventory-detail-shopping"); compose.onNodeWithTag("inventory-detail-shopping").performClick()
        compose.onNodeWithText("调整采购数量").assertExists()
        compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
        scrollTo("inventory-detail-delete"); compose.onNodeWithTag("inventory-detail-delete").performClick()
        compose.onNodeWithText("删除西瓜资料？").assertExists()
        compose.onNodeWithText("取消").performClick()
        Assert.assertEquals(1, store.items.size)
    }

    @Test fun closingAndReopeningDetailClearsSwipeStateButKeepsRecordIdentities() {
        val original = preview().records
        compose.setContent { TeamAppTheme { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
        swipe(ids[0])
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("inventory-detail-card").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("ring-selected-info").performClick()
        scrollTo(recordTag(ids[0]))
        compose.onNodeWithTag(actionTag("edit", ids[0])).assertDoesNotExist()
        compose.runOnIdle { Assert.assertEquals(original, preview().records) }
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        android.os.SystemClock.sleep(400)
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val folder = context.cacheDir.resolve("inventory-record-actions").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
