package com.example.teamapp.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.ui.theme.LocalLightDesign

private const val LaunchDuration = 1850

@Composable
internal fun MewstowLaunch(showIntro: Boolean, content: @Composable () -> Unit) {
    val timeline = remember { Animatable(if (showIntro) 0f else LaunchDuration.toFloat()) }
    LaunchedEffect(showIntro) {
        if (showIntro) timeline.animateTo(LaunchDuration.toFloat(), tween(LaunchDuration, easing = LinearEasing))
    }
    val showing = timeline.targetValue != LaunchDuration.toFloat() || timeline.isRunning
    val inkAccent = if (LocalLightDesign.current) Color(0xFF248A69) else Color(0xFF75CDA8)
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().motionInput(!showing)) { content() }
        if (showing) {
            Box(
                Modifier.fillMaxSize().testTag("mewstow-launch")
                    .graphicsLayer {
                        alpha = 1f - AppMotion.easing.transform(((timeline.value - 1540f) / 310f).coerceIn(0f, 1f))
                    }
                    .background(MaterialTheme.colorScheme.background),
                contentAlignment = Alignment.Center
            ) {
                Box(Modifier.size(96.dp).graphicsLayer {
                    val settle = AppMotion.easing.transform((timeline.value / 460f).coerceIn(0f, 1f))
                    translationY = -38.dp.toPx() * settle
                    scaleX = 1.2f - .2f * settle
                    scaleY = scaleX
                }.background(Color(0xFFA4BF5A), RoundedCornerShape(20.dp)), contentAlignment = Alignment.Center) {
                    MewstowMark(Modifier.fillMaxSize().padding(12.dp))
                }
                MewstowWordmark(
                    Modifier.padding(horizontal = 24.dp).width(252.dp).height(58.dp)
                        .graphicsLayer { translationY = 51.dp.toPx() }
                        .assembleMewstowWordmark(accent = inkAccent) { timeline.value }
                )
            }
        }
    }
}
