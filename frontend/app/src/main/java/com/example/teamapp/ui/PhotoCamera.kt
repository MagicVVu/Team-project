package com.example.teamapp.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.Observer
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.example.teamapp.data.photoDirectory
import com.example.teamapp.data.photoUri
import com.example.teamapp.ui.i18n.rememberUiStrings
import java.io.File

@Composable
internal fun PhotoCamera(
    dateOnly: Boolean,
    pickPhoto: () -> Unit,
    captured: (String) -> Unit,
    manual: () -> Unit,
    flashControl: MutableState<(() -> Unit)?>,
    flashOn: MutableState<Boolean>
) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val strings = rememberUiStrings()
    val scheme = MaterialTheme.colorScheme
    var permission by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    var permissionAsked by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var ready by remember { mutableStateOf(false) }
    var capturing by remember { mutableStateOf(false) }
    var canFlip by remember { mutableStateOf(false) }
    var cameraActive by remember { mutableStateOf(true) }
    DisposableEffect(Unit) { cameraActive = true; onDispose { cameraActive = false } }
    val controller = remember(context) { LifecycleCameraController(context).apply { setEnabledUseCases(CameraController.IMAGE_CAPTURE) } }
    val preview = remember(context) { PreviewView(context).apply {
        implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        scaleType = PreviewView.ScaleType.FILL_CENTER
    } }
    val executor = remember(context) { ContextCompat.getMainExecutor(context) }
    val currentCaptured by rememberUpdatedState(captured)
    val request = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> permission = granted; permissionAsked = true }
    LaunchedEffect(Unit) { if (!permission) { permissionAsked = true; request.launch(Manifest.permission.CAMERA) } }
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) {
            permission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        } }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    DisposableEffect(permission, owner, controller) {
        var active = true
        val observer = Observer<PreviewView.StreamState> { ready = it == PreviewView.StreamState.STREAMING }
        if (permission) {
            preview.controller = controller
            preview.previewStreamState.observe(owner, observer)
            controller.initializationFuture.addListener({
                if (active) try {
                    controller.initializationFuture.get()
                    val back = controller.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)
                    val front = controller.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)
                    canFlip = back && front
                    if (!back && front) controller.cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA
                    check(back || front)
                    controller.bindToLifecycle(owner)
                    error = ""
                } catch (_: Exception) { error = strings.tr("相机暂不可用，可以从相册选择照片。", "Camera unavailable. Choose a photo instead.") }
            }, executor)
            flashControl.value = {
                if (controller.cameraInfo?.hasFlashUnit() == true) {
                    flashOn.value = !flashOn.value
                    controller.imageCaptureFlashMode = if (flashOn.value) ImageCapture.FLASH_MODE_ON else ImageCapture.FLASH_MODE_OFF
                } else error = strings.tr("当前镜头不支持闪光灯", "This camera has no flash")
            }
        }
        onDispose {
            active = false
            flashControl.value = null
            ready = false
            preview.previewStreamState.removeObserver(observer)
            preview.controller = null
            controller.unbind()
        }
    }
    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.weight(1f).fillMaxWidth().clipToBounds().background(Color(0xFF25282A)).testTag("photo-viewfinder")) {
            if (permission && error.isBlank()) AndroidView(factory = { preview }, modifier = Modifier.fillMaxSize())
            if (!permission || error.isNotBlank()) Column(Modifier.align(Alignment.Center).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ScanIcon("camera", Modifier.size(48.dp), Color(0xFFDBE2D0))
                Text(error.ifBlank { strings.tr("允许使用相机，拍下家里的物品", "Allow camera access to photograph an item") }, color = Color.White)
                if (!permission) {
                    Button(onClick = { request.launch(Manifest.permission.CAMERA) }) { Text(strings.tr("允许使用相机", "Allow camera")) }
                    if (permissionAsked) TextButton(onClick = {
                        context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, "package:${context.packageName}".toUri()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }) { Text(strings.tr("系统设置", "Open settings"), color = Color(0xFFD1DDC2)) }
                }
                OutlinedButton(onClick = pickPhoto) { Text(strings.tr("从相册选择", "Choose from photos"), color = Color.White) }
            } else {
                ViewfinderCorners(Modifier.fillMaxSize().padding(horizontal = 44.dp, vertical = 64.dp))
                Text(strings.tr(if (dateOnly) "对准包装上的有效期" else "把物品放进框内", if (dateOnly) "Frame the expiry date" else "Place one item in the frame"),
                    color = Color.White, fontSize = 13.sp,
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 18.dp).background(Color.Black.copy(alpha = .5f), CircleShape).padding(horizontal = 16.dp, vertical = 8.dp))
                Text("1×", color = Color.White, modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 16.dp)
                    .background(Color.Black.copy(alpha = .45f), CircleShape).padding(10.dp))
            }
        }
        Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            MewMascot(MewPose.Confirming, Modifier.size(30.dp), description = null)
            Text(strings.tr(if (dateOnly) "拍清日期和旁边的说明文字" else "一次拍摄一件物品", if (dateOnly) "Include the date and its printed label" else "Photograph one item at a time"),
                fontSize = 12.sp, color = scheme.onSurfaceVariant, modifier = Modifier.padding(start = 8.dp))
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 34.dp, vertical = 12.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            CameraTool("gallery", strings.tr("相册", "Photos"), pickPhoto, enabled = !capturing)
            Box(Modifier.size(78.dp).clip(CircleShape).border(3.dp, if (ready) scheme.primary else scheme.outlineVariant, CircleShape)
                .clickable(enabled = ready && !capturing, role = Role.Button) {
                    capturing = true
                    val file = File.createTempFile("capture_", ".jpg", photoDirectory(context))
                    try {
                        controller.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(), executor, object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                                capturing = false
                                if (cameraActive && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) currentCaptured(photoUri(context, file).toString()) else file.delete()
                            }
                            override fun onError(exception: ImageCaptureException) { capturing = false; file.delete(); error = strings.tr("拍摄失败，请选图或重新打开相机。", "Capture failed. Choose a photo or reopen the camera.") }
                        })
                    } catch (_: Exception) { capturing = false; file.delete(); error = strings.tr("拍摄失败，可以从相册选择。", "Capture failed. Choose a photo instead.") }
                }.testTag("photo-shutter").semantics { contentDescription = strings.tr("拍照", "Take photo") }, contentAlignment = Alignment.Center) {
                if (capturing) CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 2.dp)
                else Box(Modifier.size(62.dp).background(scheme.primary.copy(alpha = if (ready) 1f else .25f), CircleShape))
            }
            CameraTool("flip", strings.tr("翻转", "Flip"), {
                flashOn.value = false
                controller.imageCaptureFlashMode = ImageCapture.FLASH_MODE_OFF
                controller.cameraSelector = if (controller.cameraSelector == CameraSelector.DEFAULT_BACK_CAMERA) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
            }, enabled = canFlip && !capturing)
        }
        TextButton(onClick = manual, modifier = Modifier.padding(bottom = 4.dp)) { Text(strings.tr("手动填写", "Enter manually"), fontSize = 12.sp) }
    }
}

@Composable
private fun CameraTool(kind: String, label: String, action: () -> Unit, enabled: Boolean = true) {
    TextButton(onClick = action, enabled = enabled, contentPadding = PaddingValues(8.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            ScanIcon(kind, Modifier.size(26.dp), MaterialTheme.colorScheme.onSurface.copy(alpha = if (enabled) 1f else .3f))
            Text(label, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun ViewfinderCorners(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val length = 24.dp.toPx(); val stroke = 2.dp.toPx(); val color = Color(0xFFE2EAD6)
        for ((x, y) in listOf(0f to 0f, size.width to 0f, 0f to size.height, size.width to size.height)) {
            val dx = if (x == 0f) 1 else -1; val dy = if (y == 0f) 1 else -1
            drawLine(color, Offset(x, y), Offset(x + dx * length, y), stroke, StrokeCap.Round)
            drawLine(color, Offset(x, y), Offset(x, y + dy * length), stroke, StrokeCap.Round)
        }
    }
}

@Composable
internal fun ScanIcon(kind: String, modifier: Modifier = Modifier.size(24.dp), color: Color = MaterialTheme.colorScheme.onSurface) {
    if (kind in listOf("camera", "mic", "plus")) { DesignGlyph(kind, modifier, color); return }
    Canvas(modifier) {
        val factor = size.width / 24f
        fun point(x: Float, y: Float) = Offset(x * factor, y * factor)
        fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(color, point(x1,y1), point(x2,y2), 1.6f * factor, StrokeCap.Round)
        when (kind) {
            "close" -> { line(6f,6f,18f,18f); line(18f,6f,6f,18f) }
            "back" -> { line(15f,4f,7f,12f); line(7f,12f,15f,20f) }
            "gallery" -> {
                drawRoundRect(color, point(3f,3f), androidx.compose.ui.geometry.Size(18f*factor,18f*factor), androidx.compose.ui.geometry.CornerRadius(3f*factor), style=Stroke(1.5f*factor))
                drawCircle(color, 1.6f*factor, point(9f,8f)); line(5f,18f,11f,12f); line(11f,12f,14f,15f); line(14f,15f,18f,11f)
            }
            "flip" -> {
                drawArc(color, -40f, 250f, false, point(4f,4f), androidx.compose.ui.geometry.Size(16f*factor,16f*factor), style=Stroke(1.6f*factor))
                line(20f,4f,20f,10f); line(20f,10f,14f,10f)
            }
            "flash", "flash-off" -> {
                val path=Path().apply { moveTo(13f*factor,2f*factor); lineTo(6f*factor,13f*factor); lineTo(11f*factor,13f*factor); lineTo(10f*factor,22f*factor); lineTo(18f*factor,10f*factor); lineTo(13f*factor,10f*factor); close() }
                drawPath(path,color,style=Stroke(1.4f*factor)); if(kind=="flash-off") line(3f,3f,21f,21f)
            }
        }
    }
}
