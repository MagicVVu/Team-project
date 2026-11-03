package com.example.teamapp.ui

import android.app.Activity
import android.content.Intent
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.MotionDurationScale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.input.key.*
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.ui.i18n.rememberUiStrings

private object ComposerMotion {
    const val Focus = 200
    const val Size = 210
    const val State = 180
    const val Press = 90
    const val Release = 140
}

/** Only the text-driven height animates here. The hosting screen owns system/IME insets. */
@Composable
internal fun AssistantComposer(
    value: TextFieldValue,
    onValueChange: (TextFieldValue) -> Unit,
    onSend: () -> Unit,
    onVoiceError: (String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    sending: Boolean = false
) {
    val strings = rememberUiStrings()
    val colors = MaterialTheme.colorScheme
    val interactions = remember { MutableInteractionSource() }
    val focused by interactions.collectIsFocusedAsState()
    val motionEnabled = rememberComposerMotionEnabled()
    var multiline by remember { mutableStateOf(false) }
    val canSend = enabled && !sending && value.text.isNotBlank() && value.composition == null
    val placeholder = strings.tr("输入消息…", "Message Mew…")
    val currentValue by rememberUpdatedState(value)
    val currentChange by rememberUpdatedState(onValueChange)
    val currentEnabled by rememberUpdatedState(enabled && !sending)
    var voiceDraft by remember { mutableStateOf<TextFieldValue?>(null) }
    // The system owns recording, waveform, stop and cancel. A launched intent is not
    // evidence of recording, so this composer never presents a recording animation.
    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val original = voiceDraft
        voiceDraft = null
        if (result.resultCode == Activity.RESULT_OK && original != null && currentEnabled && currentValue == original) {
            result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.takeIf { it.isNotBlank() }?.let {
                currentChange(TextFieldValue(it, selection = TextRange(it.length)))
            }
        }
    }
    val background by animateColorAsState(
        if (focused) lerp(colors.surfaceContainerLowest, colors.primaryContainer, .08f) else colors.surfaceContainerLowest,
        tween(ComposerMotion.Focus), label = "composer-background"
    )
    val border by animateColorAsState(
        if (focused) colors.primary.copy(alpha = .4f) else colors.outlineVariant.copy(alpha = .65f),
        tween(ComposerMotion.Focus), label = "composer-border"
    )
    val elevation by animateDpAsState(if (focused) 3.dp else 1.dp, tween(ComposerMotion.Focus), label = "composer-shadow")
    val radius by animateDpAsState(
        if (multiline) 22.dp else 28.dp, tween(if (motionEnabled) ComposerMotion.Size else 0), label = "composer-corners"
    )
    val sendColor by animateColorAsState(
        if (canSend || sending) colors.primary else colors.surfaceVariant,
        tween(ComposerMotion.State), label = "composer-send-color"
    )
    val arrowAlpha = animateFloatAsState(if (sending) 0f else if (canSend) 1f else .45f,
        tween(ComposerMotion.State), label = "composer-send-icon")
    val arrowTint by animateColorAsState(if (canSend || sending) colors.onPrimary else colors.onSurfaceVariant,
        tween(ComposerMotion.State), label = "composer-send-tint")

    Surface(
        modifier = modifier.fillMaxWidth().testTag("ai-composer"),
        shape = RoundedCornerShape(radius), color = background,
        border = BorderStroke(.75.dp, border), shadowElevation = elevation
    ) {
        Row(
            Modifier.fillMaxWidth()
                .animateContentSize(tween(if (motionEnabled) ComposerMotion.Size else 0, easing = AppMotion.easing),
                    alignment = Alignment.BottomStart)
                .heightIn(min = 56.dp).padding(4.dp),
            verticalAlignment = Alignment.Bottom
        ) {
            BasicTextField(
                value = value, onValueChange = onValueChange,
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).padding(start = 12.dp, end = 4.dp)
                    .testTag("ai-input").semantics { contentDescription = placeholder }
                    .onPreviewKeyEvent { event ->
                        // Plain Enter remains a newline; an IME's composing text is never submitted.
                        if (event.key == Key.Enter && event.isCtrlPressed && event.type == KeyEventType.KeyDown) {
                            if (canSend && event.nativeKeyEvent.repeatCount == 0) onSend()
                            true
                        } else false
                    },
                interactionSource = interactions,
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = colors.onSurface, lineHeight = 24.sp),
                cursorBrush = SolidColor(colors.primary),
                minLines = 1, maxLines = 4,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
                keyboardActions = KeyboardActions(onSend = { if (canSend) onSend() }),
                onTextLayout = { multiline = it.lineCount > 1 },
                decorationBox = { field ->
                    Box(Modifier.padding(vertical = 12.dp), contentAlignment = Alignment.CenterStart) {
                        if (value.text.isEmpty()) Text(placeholder, modifier = Modifier.clearAndSetSemantics {}, color = colors.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyLarge, maxLines = 1)
                        field()
                    }
                }
            )
            ComposerIconButton(
                onClick = {
                    if (voiceDraft == null) {
                        voiceDraft = currentValue
                        try {
                            voice.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, strings.language))
                        } catch (_: Exception) {
                            voiceDraft = null
                            onVoiceError(strings.tr("系统语音识别不可用，请手动输入。", "Speech recognition is unavailable. Type your message instead."))
                        }
                    }
                },
                enabled = enabled && !sending && voiceDraft == null && value.composition == null,
                motionEnabled = motionEnabled,
                modifier = Modifier.testTag("ai-voice")
            ) {
                Icon(ComposerMicrophone, strings.tr("系统语音输入", "System voice input"),
                    Modifier.size(22.dp), tint = colors.onSurfaceVariant.copy(alpha = if (enabled && !sending) 1f else .45f))
            }
            ComposerIconButton(
                onClick = { if (canSend) onSend() }, enabled = canSend, motionEnabled = motionEnabled,
                modifier = Modifier.testTag("ai-send").semantics {
                    contentDescription = strings.tr("发送消息", "Send message")
                    stateDescription = when {
                        sending -> strings.tr("正在发送", "Sending")
                        value.composition != null -> strings.tr("请先完成文字输入", "Finish composing first")
                        !enabled -> strings.tr("暂不可发送", "Sending unavailable")
                        value.text.isBlank() -> strings.tr("请输入消息", "Enter a message")
                        else -> strings.tr("可以发送", "Ready to send")
                    }
                }
            ) {
                Box(Modifier.size(40.dp).background(sendColor, CircleShape), contentAlignment = Alignment.Center) {
                    Icon(ComposerArrow, null, Modifier.size(22.dp).graphicsLayer { alpha = arrowAlpha.value },
                        tint = arrowTint)
                    if (sending) {
                        if (motionEnabled) CircularProgressIndicator(Modifier.size(18.dp), color = colors.onPrimary, strokeWidth = 1.75.dp)
                        else Text("···", color = colors.onPrimary, style = MaterialTheme.typography.labelLarge)
                    }
                }
            }
        }
    }
}

@Composable
private fun rememberComposerMotionEnabled(): Boolean {
    val resolver = LocalContext.current.contentResolver
    fun systemMotionEnabled() = Settings.Global.getFloat(resolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
    var systemEnabled by remember(resolver) { mutableStateOf(systemMotionEnabled()) }
    DisposableEffect(resolver) {
        val observer = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) { systemEnabled = systemMotionEnabled() }
        }
        resolver.registerContentObserver(Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE), false, observer)
        onDispose { resolver.unregisterContentObserver(observer) }
    }
    // Also honor a duration scale supplied by the host (for example an accessibility
    // or test environment), while observing live changes to the Android setting.
    val hostScale = rememberCoroutineScope().coroutineContext[MotionDurationScale]?.scaleFactor ?: 1f
    return systemEnabled && hostScale > 0f
}

@Composable
private fun ComposerIconButton(
    onClick: () -> Unit, enabled: Boolean, motionEnabled: Boolean, modifier: Modifier,
    content: @Composable () -> Unit
) {
    val interactions = remember { MutableInteractionSource() }
    val pressed by interactions.collectIsPressedAsState()
    val scale = animateFloatAsState(
        if (pressed && enabled && motionEnabled) .96f else 1f,
        tween(if (pressed) ComposerMotion.Press else ComposerMotion.Release, easing = AppMotion.easing),
        label = "composer-button-press"
    )
    IconButton(onClick = onClick, enabled = enabled, interactionSource = interactions, modifier = modifier.size(48.dp)) {
        // Keep the 48dp hit target stable; only the visual scales.
        Box(Modifier.graphicsLayer { scaleX = scale.value; scaleY = scale.value }, contentAlignment = Alignment.Center) { content() }
    }
}

private val ComposerArrow = ImageVector.Builder("ComposerArrow", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 1.75f,
        strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round) {
        moveTo(12f, 19f); lineTo(12f, 5f)
        moveTo(6.5f, 10.5f); lineTo(12f, 5f); lineTo(17.5f, 10.5f)
    }
}.build()

private val ComposerMicrophone = ImageVector.Builder("ComposerMicrophone", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 1.75f,
        strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round) {
        moveTo(9f, 6f); curveTo(9f, 2f, 15f, 2f, 15f, 6f)
        lineTo(15f, 11f); curveTo(15f, 15f, 9f, 15f, 9f, 11f); close()
        moveTo(6f, 10.5f); lineTo(6f, 11.5f); curveTo(6f, 19f, 18f, 19f, 18f, 11.5f); lineTo(18f, 10.5f)
        moveTo(12f, 17f); lineTo(12f, 21f)
        moveTo(9f, 21f); lineTo(15f, 21f)
    }
}.build()
