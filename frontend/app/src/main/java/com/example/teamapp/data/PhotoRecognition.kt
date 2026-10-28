package com.example.teamapp.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import androidx.core.graphics.scale
import androidx.exifinterface.media.ExifInterface
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.segmentation.subject.SubjectSegmentation
import com.google.mlkit.vision.segmentation.subject.SubjectSegmenterOptions
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import kotlin.coroutines.coroutineContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max

internal data class PhotoRecognitionResult(
    val originalUri: String,
    val displayUri: String,
    val draft: PhotoDraft,
    val rawText: String,
    val cutout: Boolean,
    val textAvailable: Boolean
)

internal fun interface PhotoRecognizer {
    suspend fun recognize(uri: String, dateOnly: Boolean): PhotoRecognitionResult
}

/** Local-only recognition. Inventory is modified exclusively by the user's final confirmation. */
internal class LocalPhotoRecognizer(context: Context) : PhotoRecognizer {
    private val context = context.applicationContext

    override suspend fun recognize(uri: String, dateOnly: Boolean): PhotoRecognitionResult = withContext(Dispatchers.IO) {
        val bitmap = loadPhotoBitmap(context, uri) ?: error("无法读取这张照片，请重新拍摄或选图。")
        coroutineScope {
            val extraction = async {
                val client = TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build())
                val task = client.process(InputImage.fromBitmap(bitmap, 0))
                task.addOnCompleteListener { client.close() }
                try {
                    withTimeoutOrNull(18_000) { task.awaitPhotoTask() }
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { null }
            }
            val segmentation = async { if (dateOnly) null else cutout(bitmap) }
            val text = extraction.await()
            val foreground = segmentation.await()?.let(::cropForeground)
            coroutineContext.ensureActive()
            val photoUri = if (foreground != null) {
                val file = File.createTempFile("cutout_", ".png", photoDirectory(context))
                file.outputStream().use { check(foreground.compress(Bitmap.CompressFormat.PNG, 100, it)) }
                photoUri(context, file).toString()
            } else uri
            PhotoRecognitionResult(uri, photoUri,
                PhotoDraftParser.parse(text?.textBlocks?.flatMap { block -> block.lines.map { PhotoTextLine(it.text, it.boundingBox?.height() ?: 0) } }.orEmpty()),
                text?.text.orEmpty(), foreground != null, text != null)
        }
    }

    private suspend fun cutout(bitmap: Bitmap): Bitmap? {
        if (GoogleApiAvailability.getInstance().isGooglePlayServicesAvailable(context) != ConnectionResult.SUCCESS) return null
        return try {
            val client = SubjectSegmentation.getClient(SubjectSegmenterOptions.Builder().enableForegroundBitmap().build())
            val task = client.process(InputImage.fromBitmap(bitmap, 0))
            task.addOnCompleteListener { client.close() }
            withTimeoutOrNull(5_000) { task.awaitPhotoTask().foregroundBitmap }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { null }
    }
}

internal fun photoDirectory(context: Context): File = File(context.filesDir, "photos").apply { check(isDirectory || mkdirs()) }
internal fun photoUri(context: Context, file: File): Uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)

/** Bound both decode memory and resolution; honor EXIF before OCR, display and masking. */
internal fun loadPhotoBitmap(context: Context, value: String, maxEdge: Int = 1600): Bitmap? {
    if (value.isBlank()) return null
    return runCatching {
        val uri = value.toUri()
        fun stream() = requireNotNull(context.contentResolver.openInputStream(uri))
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        stream().use { BitmapFactory.decodeStream(it, null, bounds) }
        require(bounds.outWidth > 0 && bounds.outHeight > 0)
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / sample > maxEdge * 2) sample *= 2
        val decoded = stream().use { BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) } ?: return null
        val orientation = runCatching { stream().use { ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL) } }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        val matrix = Matrix().apply {
            when (orientation) {
                ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
                ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
                ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
                ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
                ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(270f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(270f)
            }
        }
        val rotated = if (matrix.isIdentity) decoded else Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        val scale = maxEdge.toFloat() / max(rotated.width, rotated.height)
        if (scale < 1f) rotated.scale((rotated.width * scale).toInt().coerceAtLeast(1), (rotated.height * scale).toInt().coerceAtLeast(1)) else rotated
    }.getOrNull()
}

private fun cropForeground(bitmap: Bitmap): Bitmap? {
    val pixels = IntArray(bitmap.width * bitmap.height)
    bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
    var left = bitmap.width; var right = -1; var top = bitmap.height; var bottom = -1
    for (y in 0 until bitmap.height) for (x in 0 until bitmap.width) {
        if ((pixels[y * bitmap.width + x] ushr 24) > 64) {
            left = minOf(left, x); right = maxOf(right, x); top = minOf(top, y); bottom = maxOf(bottom, y)
        }
    }
    if (right < left || bottom < top) return null
    left = (left - 12).coerceAtLeast(0); top = (top - 12).coerceAtLeast(0)
    right = (right + 12).coerceAtMost(bitmap.width - 1); bottom = (bottom + 12).coerceAtMost(bitmap.height - 1)
    return Bitmap.createBitmap(bitmap, left, top, right - left + 1, bottom - top + 1)
}

private suspend fun <T> Task<T>.awaitPhotoTask(): T = suspendCancellableCoroutine { continuation ->
    addOnSuccessListener { if (continuation.isActive) continuation.resume(it) }
    addOnFailureListener { if (continuation.isActive) continuation.resumeWithException(it) }
    addOnCanceledListener { continuation.cancel() }
}
