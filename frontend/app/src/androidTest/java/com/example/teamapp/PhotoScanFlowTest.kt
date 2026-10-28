package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.espresso.Espresso
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import com.example.teamapp.ui.PhotoScanFlow
import com.example.teamapp.ui.theme.TeamAppTheme
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import java.io.File
import java.util.UUID

/** Isolated local records only. OCR is tested separately from deterministic UI transitions. */
class PhotoScanFlowTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var context: Context
    private lateinit var store: InventoryStore
    private lateinit var fixture: File
    private lateinit var uri: String
    private val dark = mutableStateOf(false)

    @Before fun setup() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        context = object : ContextWrapper(instrumentation.targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences("photo_scan_test_$name", mode)
        }
        if (androidx.core.content.ContextCompat.checkSelfPermission(context, android.Manifest.permission.CAMERA) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand("pm grant ${context.packageName} android.permission.CAMERA")).use { it.readBytes() }
        }
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
        store = InventoryStore(context)
        fixture = File(photoDirectory(context), "test-recognition-${UUID.randomUUID()}.png")
        val bitmap = Bitmap.createBitmap(1000, 1400, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.rgb(247, 245, 234))
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        paint.color = Color.WHITE; canvas.drawRoundRect(140f, 90f, 860f, 1270f, 70f, 70f, paint)
        paint.color = Color.rgb(42, 59, 38); paint.textSize = 128f; paint.textAlign = Paint.Align.CENTER
        canvas.drawText("纯牛奶", 500f, 420f, paint)
        paint.textSize = 62f
        canvas.drawText("净含量 250mL", 500f, 590f, paint)
        canvas.drawText("计量单位：瓶", 500f, 730f, paint)
        paint.textSize = 48f
        canvas.drawText("生产日期 2026-10-25", 500f, 900f, paint)
        canvas.drawText("有效期至 2026-10-28", 500f, 1020f, paint)
        fixture.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        uri = photoUri(context, fixture).toString()
    }

    @After fun cleanup() {
        fixture.delete()
        context.getSharedPreferences("magicvvu_v1", 0).edit().clear().commit()
    }

    private fun recognized() = PhotoRecognitionResult(uri, uri, PhotoDraft("纯牛奶", "250ml", "瓶", "食品"), "纯牛奶\n净含量250ml", false, true)
    private fun launch(service: PhotoRecognizer = PhotoRecognizer { _, _ -> recognized() }, closed: () -> Unit = {}) {
        compose.setContent { TeamAppTheme(dark.value) { PhotoScanFlow(store, {}, closed, service, uri) } }
        awaitReview()
    }
    private fun awaitReview() = compose.waitUntil(8_000) { compose.onAllNodesWithTag("photo-name").fetchSemanticsNodes().isNotEmpty() }
    private fun shot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        android.os.SystemClock.sleep(350)
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val folder = File(context.cacheDir, "photo-scan-review").apply { mkdirs() }
        File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
    }

    @Test fun realBundledOcrReadsPackageAndDoesNotWriteStock() = runBlocking {
        val result = LocalPhotoRecognizer(context).recognize(uri, false)
        assertTrue("Bundled OCR must run on the device", result.rawText.contains("纯牛奶"))
        assertEquals("纯牛奶", result.draft.name)
        assertEquals("250ml", result.draft.specification)
        assertEquals("2026-10-28", result.draft.expiry)
        assertTrue(store.items.isEmpty())
        if(!result.cutout) assertEquals(uri, result.displayUri)
    }

    @Test fun realCameraShutterProducesAReadablePhotoBeforeReview() {
        var captured = ""
        compose.setContent { TeamAppTheme { PhotoScanFlow(store, {}, {}, PhotoRecognizer { value, _ ->
            captured = value
            PhotoRecognitionResult(value, value, PhotoDraft(), "", false, true)
        }) } }
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("photo-shutter").filter(isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("photo-shutter").performClick()
        awaitReview()
        assertTrue(captured.startsWith("content://"))
        assertNotNull(loadPhotoBitmap(context, captured, 128))
        compose.runOnIdle { assertTrue(store.items.isEmpty()) }
    }

    @Test fun onlyExplicitConfirmationWritesAndPreservesPhoto() {
        var closed = false
        launch(closed = { closed = true })
        compose.runOnIdle { assertTrue(store.items.isEmpty()) }
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.waitUntil(5_000) { store.items.size == 1 }
        compose.runOnIdle {
            assertEquals(1.0, store.items.single().quantity, 0.0)
            assertEquals("瓶", store.items.single().unit)
            assertEquals(uri, store.items.single().image)
            assertEquals("", store.items.single().expiry)
            assertTrue(closed)
        }
    }

    @Test fun failedRecognitionRetainsImageAndRequiresNameAndUnit() {
        compose.setContent { TeamAppTheme { PhotoScanFlow(store, {}, {}, PhotoRecognizer { _, _ -> error("test failure") }, uri) } }
        compose.waitUntil(5_000) { compose.onAllNodesWithText("保留照片，手动填写").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("保留照片，手动填写").performClick(); awaitReview()
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.onNodeWithTag("photo-review-error").assertExists()
        compose.runOnIdle { assertTrue(store.items.isEmpty()) }
        compose.onNodeWithTag("photo-name").performScrollTo().performTextInput("手填物品")
        Espresso.closeSoftKeyboard()
        compose.onNodeWithText("单位", substring = false).performScrollTo().performClick()
        compose.onNodeWithText("瓶", substring = false).performClick()
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.waitUntil(5_000) { store.items.isNotEmpty() }
        compose.runOnIdle { assertEquals(uri, store.items.single().image) }
    }

    @Test fun cancelStopsPendingRecognitionAndDoesNotCreateAResult() {
        var cancelled = false
        val started = CompletableDeferred<Unit>()
        compose.setContent { TeamAppTheme { PhotoScanFlow(store, {}, {}, PhotoRecognizer { _, _ ->
            started.complete(Unit)
            try { awaitCancellation() } finally { cancelled = true }
        }, uri) } }
        compose.waitUntil(5_000) { started.isCompleted }
        compose.onNodeWithTag("photo-cancel-recognition").performClick()
        compose.onNodeWithTag("photo-viewfinder").assertExists()
        compose.onNodeWithTag("photo-name").assertDoesNotExist()
        compose.runOnIdle { assertTrue(cancelled); assertTrue(store.items.isEmpty()) }
    }

    @Test fun editedDraftAndDateSurviveRestoreWithoutDuplicateWrites() {
        val restorer = StateRestorationTester(compose)
        restorer.setContent { TeamAppTheme { PhotoScanFlow(store, {}, {}, PhotoRecognizer { _, _ -> recognized() }, uri) } }
        awaitReview()
        compose.onNodeWithTag("photo-name").performTextReplacement("核对后的纯牛奶")
        compose.onNodeWithTag("photo-quantity").performScrollTo().performTextReplacement("2")
        Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("photo-expiry").performScrollTo().performClick()
        compose.onNodeWithTag("photo-date-input").performTextInput("2026-10-30")
        compose.onNodeWithText("使用此日期").performClick()
        restorer.emulateSavedInstanceStateRestore()
        awaitReview()
        compose.onNodeWithTag("photo-name").performScrollTo().assertTextContains("核对后的纯牛奶")
        compose.onNodeWithTag("photo-quantity").performScrollTo().assertTextContains("2")
        compose.onNodeWithTag("photo-expiry").performScrollTo().assertTextContains("2026-10-30", substring = true)
        compose.runOnIdle { assertTrue(store.items.isEmpty()) }
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.waitUntil(5_000) { store.items.size == 1 }
        compose.runOnIdle { assertEquals("2026-10-30", store.items.single().expiry); assertEquals(2.0, store.items.single().quantity, 0.0) }
    }

    @Test fun incompatibleLocalBatchNeverSilentlyMerges() {
        store.saveItem(StockItem(name = "纯牛奶（250ml）", quantity = 3.0, unit = "瓶", expiry = "2026-10-28", location = "冰箱"))
        launch()
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.onNodeWithText("已有同名物品").assertExists()
        compose.onNodeWithText("增加库存", substring = false).assertDoesNotExist()
        compose.runOnIdle { assertEquals(1, store.items.size); assertEquals(3.0, store.items.single().quantity, 0.0); assertEquals("2026-10-28", store.items.single().expiry) }
    }

    @Test fun explicitlyMergingCompatibleStockAlsoUpdatesItsPhoto() {
        store.saveItem(StockItem(name = "纯牛奶（250ml）", quantity = 3.0, unit = "瓶", location = "冰箱"))
        launch()
        compose.onNodeWithTag("photo-confirm").performClick()
        compose.onNodeWithText("增加库存", substring = false).performClick()
        compose.waitUntil(5_000) { store.items.single().quantity == 4.0 }
        compose.runOnIdle { assertEquals(1, store.items.size); assertEquals(uri, store.items.single().image) }
    }

    @Test fun nativeCameraProcessingAndReviewScreensInBothThemes() {
        var scene by mutableIntStateOf(0)
        var completion = CompletableDeferred<PhotoRecognitionResult>()
        val service = PhotoRecognizer { _, _ -> completion.await() }
        compose.setContent {
            TeamAppTheme(dark.value) {
                key(scene) { PhotoScanFlow(store, {}, {}, service, if(scene % 2 == 0) "" else uri) }
            }
        }
        for ((index, isDark) in listOf(false, true).withIndex()) {
            compose.runOnIdle { dark.value = isDark; scene = index * 2 }
            compose.onNodeWithTag("photo-viewfinder").assertExists(); shot(if(isDark) "dark-camera" else "light-camera")
            compose.runOnIdle { completion = CompletableDeferred(); scene++ }
            compose.onNodeWithTag("photo-cancel-recognition").assertExists(); shot(if(isDark) "dark-processing" else "light-processing")
            compose.runOnIdle { completion.complete(recognized()) }
            awaitReview(); shot(if(isDark) "dark-review" else "light-review")
        }
        compose.runOnIdle { assertTrue(store.items.isEmpty()) }
    }
}
