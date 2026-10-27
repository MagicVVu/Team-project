package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
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
import org.junit.*
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.ChronoUnit

/** Isolated guest storage only. Receipts must never alter persisted stock or create cards. */
@RunWith(AndroidJUnit4::class)
class InventoryPreviewUiTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private val names = listOf("magicvvu_v1", "magicvvu_cloud_credentials", "magicvvu_cloud_cache")
    private val melon = StockItem(id = "preview-melon", name = "西瓜", quantity = 2.0, unit = "个",
        location = "冰箱", expiry = "2026-10-26")

    @Before fun setup() {
        context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("inventory_preview_test_$name", mode)
        }
        names.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() }
        store = InventoryStore(context)
        store.saveItem(melon)
    }
    @After fun cleanup() { names.forEach { context.getSharedPreferences(it, 0).edit().clear().commit() } }

    private fun show(dark: Boolean = false) {
        compose.setContent { TeamAppTheme(darkTheme = dark) { MagicApp(store) } }
        compose.onNodeWithText("库存", useUnmergedTree = true).performClick()
        compose.onNodeWithTag("ring-selected-info").performClick()
    }
    private fun scrollTo(tag: String) {
        compose.onNodeWithTag("inventory-detail-content").performScrollToNode(hasTestTag(tag))
    }
    private fun top() { compose.onNodeWithTag("inventory-detail-content").performScrollToIndex(0) }
    private fun openReceipt() {
        scrollTo("inventory-detail-receive")
        compose.onNodeWithTag("inventory-detail-receive").performClick()
    }
    private fun enter(value: String) {
        compose.onNodeWithTag("inventory-receive-quantity").performClick().performTextReplacement(value)
    }
    private fun choose(date: LocalDate) {
        compose.onNodeWithTag("inventory-receive-pick-date").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-receive-date-confirm").assertIsNotEnabled()
        val months = ChronoUnit.MONTHS.between(YearMonth.now(), YearMonth.from(date)).toInt()
        repeat(kotlin.math.abs(months)) {
            compose.onNodeWithTag(if (months >= 0) "inventory-expiry-next" else "inventory-expiry-previous").performClick()
        }
        compose.onNodeWithTag("inventory-expiry-$date").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-receive-date-confirm").performClick()
    }
    private fun recordContains(index: Int, text: String) {
        val record = store.inventoryPreviews.preview(store.inventoryPreviewScope, store.items.first { it.id == melon.id }).records[index - 1]
        val tag = "inventory-preview-record-${record.id}"
        scrollTo(tag)
        compose.onNode(hasText(text) and hasAnyAncestor(hasTestTag(tag))).assertExists()
    }

    @Test fun existingPiecesShowAllFactsAndThreeNewPiecesKeepChosenExpiryWithoutSaving() {
        val original = store.export()
        show()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2 个")
        recordContains(1, "位置：冰箱")
        recordContains(1, "有效期：2026-10-26")
        recordContains(2, "开封日期：未登记")
        openReceipt()
        enter("3")
        choose(LocalDate.parse("2026-11-15"))
        screenshot("receipt-light")
        compose.onNodeWithTag("inventory-receive-confirm").performClick()
        compose.onNodeWithTag("inventory-receive-dialog").assertDoesNotExist()
        recordContains(3, "有效期：2026-11-15")
        recordContains(5, "开封日期：未登记")
        top()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("5 个")
        compose.onNodeWithTag("inventory-detail-saved-quantity").assertTextEquals("本机已保存：2 个")
        screenshot("five-pieces-light")
        compose.runOnIdle {
            Assert.assertEquals(1, store.items.size)
            Assert.assertEquals(original, store.export())
            Assert.assertEquals(5, store.inventoryPreviews.preview("local", melon).records.size)
        }
    }

    @Test fun twoReceiptsKeepSeparateDatesAndSurviveClosingAndChangingItems() {
        store.saveItem(melon.copy(quantity = 0.0))
        store.saveItem(StockItem(id = "other", name = "纸巾", quantity = 1.0, unit = "包"))
        show()
        for ((quantity, date) in listOf("2" to "2026-11-10", "3" to "2026-11-20")) {
            openReceipt(); enter(quantity); choose(LocalDate.parse(date))
            compose.onNodeWithTag("inventory-receive-confirm").performClick()
        }
        recordContains(2, "有效期：2026-11-10")
        recordContains(5, "有效期：2026-11-20")
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("inventory-detail-card").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("ring-card-other").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("ring-selected-info").fetchSemanticsNodes().size == 1 }
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("1 包")
        compose.onNodeWithTag("inventory-detail-close").performClick()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("inventory-detail-card").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("ring-card-preview-melon").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("ring-selected-info").fetchSemanticsNodes().size == 1 }
        compose.onNodeWithTag("ring-selected-info").performClick()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("5 个")
    }

    @Test fun cancelAndInvalidInputsDoNotChangeStockAndMissingExpiryStaysEmpty() {
        show()
        openReceipt()
        compose.onNodeWithTag("inventory-receive-confirm").assertIsNotEnabled()
        for (value in listOf("0", "-1", "abc", "1.5", "1.0", "")) {
            enter(value)
            compose.onNodeWithTag("inventory-receive-confirm").assertIsNotEnabled()
        }
        enter("3")
        compose.onNodeWithTag("inventory-receive-cancel").performClick()
        top()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2 个")
        openReceipt(); enter("1")
        compose.onNodeWithTag("inventory-receive-confirm").performClick()
        recordContains(3, "有效期：未设置")
        recordContains(3, "开封日期：未登记")
    }

    @Test fun zeroStockHasEmptyStateAndEntry() {
        store.saveItem(melon.copy(quantity = 0.0))
        show()
        scrollTo("inventory-detail-empty-receive")
        compose.onNodeWithText("暂无单件库存记录").assertExists()
        compose.onNodeWithTag("inventory-preview-record-existing:preview-melon:0").assertDoesNotExist()
        compose.onNodeWithTag("inventory-detail-empty-receive").performClick()
        compose.onNodeWithTag("inventory-receive-dialog").assertExists()
    }

    @Test fun chosenExpiryCanBeClearedAndRapidConfirmationCreatesOnlyOneBatch() {
        show()
        openReceipt(); enter("3")
        choose(LocalDate.parse("2026-11-15"))
        compose.onNodeWithTag("inventory-receive-clear-date").performScrollTo().performClick()
        compose.onNodeWithTag("inventory-receive-expiry").assertTextEquals("有效期：未设置")
        compose.onNodeWithTag("inventory-receive-confirm").performSemanticsAction(SemanticsActions.OnClick) { click ->
            click(); click()
        }
        top()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("5 个")
        compose.runOnIdle {
            val records = store.inventoryPreviews.preview("local", melon).records
            Assert.assertEquals(5, records.size)
            Assert.assertTrue(records.drop(2).all { it.expiryDate == null && it.openedAt == null })
        }
    }

    @Test fun measuredStockRetainsDecimalsAndNeverPretendsToBePieces() {
        store.saveItem(melon.copy(quantity = 2.5, unit = "kg", quantityExact = "2.500000"))
        show()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2.5 kg")
        openReceipt(); enter("0.000001")
        compose.onNodeWithTag("inventory-receive-confirm").performClick()
        top()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("2.500001 kg")
        compose.runOnIdle { Assert.assertEquals("2.500000", store.items.single().quantityText) }
    }

    @Test fun savedConsumptionDisclosesMismatchAndNeverChoosesAPreviewPiece() {
        show()
        openReceipt(); enter("3")
        compose.onNodeWithTag("inventory-receive-confirm").performClick()
        compose.runOnIdle { store.changeQuantity(melon.id, -1.0) }
        top()
        compose.onNodeWithTag("inventory-detail-quantity").assertTextEquals("5 个")
        compose.onNodeWithTag("inventory-detail-saved-quantity").assertTextEquals("本机已保存：1 个")
        compose.onNodeWithTag("inventory-preview-changed").assertExists()
    }

    @Test fun secondaryActionsRemainAndDeferredEntriesAreHidden() {
        var route = ""
        var deleting = false
        compose.setContent { TeamAppTheme { InventoryDetailContent(store, store.items.single(), { route = it }, { deleting = true }, { Modifier }) } }
        scrollTo("inventory-detail-edit")
        compose.onNodeWithTag("inventory-detail-edit").performClick()
        Assert.assertEquals("编辑物品", route)
        scrollTo("inventory-detail-shopping")
        compose.onNodeWithTag("inventory-detail-shopping").assertTextEquals("加入购买清单").performClick()
        Assert.assertEquals("加入采购清单", route)
        compose.runOnIdle { store.plan(melon.id, 2.0) }
        compose.onNodeWithTag("inventory-detail-shopping").performClick()
        Assert.assertEquals("调整采购数量", route)
        compose.onNodeWithTag("inventory-detail-consume").assertDoesNotExist()
        compose.onNodeWithTag("inventory-detail-history").assertDoesNotExist()
        scrollTo("inventory-detail-delete")
        compose.onNodeWithTag("inventory-detail-delete").performClick()
        Assert.assertTrue(deleting)
        for (text in listOf("资料与盘点", "开封、丢弃与询问这批", "真实消费流水", "盘点修正数量（不计消费）", "加入清单 / 调整")) {
            compose.onNodeWithText(text).assertDoesNotExist()
        }
    }

    @Test fun englishDarkSmallViewportCanScrollAndCancelReceipt() {
        compose.setContent { AppLanguageProvider("en") { TeamAppTheme(darkTheme = true) {
            Box(Modifier.requiredSize(320.dp, 480.dp)) {
                InventoryDetailContent(store, store.items.single(), {}, {}, { Modifier })
            }
        } } }
        scrollTo("inventory-detail-receive")
        compose.onNodeWithTag("inventory-detail-receive").assertTextEquals("Add").performClick()
        compose.onNodeWithTag("inventory-receive-confirm").assertIsDisplayed().assertIsNotEnabled()
        enter("3")
        compose.onNodeWithTag("inventory-receive-confirm").assertIsEnabled()
        screenshot("receipt-dark-english")
        compose.onNodeWithTag("inventory-receive-cancel").assertIsDisplayed().performClick()
        scrollTo("inventory-detail-delete")
        compose.onNodeWithTag("inventory-detail-delete").assertIsDisplayed()
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        // Dialog window exit animations run outside Compose's test clock.
        android.os.SystemClock.sleep(500)
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val folder = context.cacheDir.resolve("inventory-preview").apply { mkdirs() }
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
