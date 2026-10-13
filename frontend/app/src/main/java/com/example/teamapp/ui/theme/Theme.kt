package com.example.teamapp.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

internal val LocalLightDesign = staticCompositionLocalOf { false }

private val LightColorScheme = lightColorScheme(
    primary = Color(0xFF476339), onPrimary = Color(0xFFFFFEF7),
    primaryContainer = Color(0xFFE4EACF), onPrimaryContainer = Color(0xFF30412E),
    secondary = Color(0xFF687954), secondaryContainer = Color(0xFFF1E8CB),
    onSecondaryContainer = Color(0xFF51472D),
    background = Color(0xFFFAF7E8), onBackground = Color(0xFF30412E),
    surface = Color(0xFFF7F5E8), onSurface = Color(0xFF30412E),
    onSurfaceVariant = Color(0xFF68745C), surfaceVariant = Color(0xFFE4EACF),
    surfaceContainerLowest = Color(0xFFFFFEF7), surfaceContainerLow = Color(0xFFFAF7E8),
    surfaceContainer = Color(0xFFF7F5E8), surfaceContainerHigh = Color(0xFFF0EFD9),
    surfaceContainerHighest = Color(0xFFE4EACF),
    outline = Color(0xFFAFC098), outlineVariant = Color(0xFFD5DCBE)
)
private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF9FD6BB), onPrimary = Color(0xFF123D2D),
    primaryContainer = Color(0xFF204B3C), onPrimaryContainer = Color(0xFFD4F2E0),
    secondaryContainer = Color(0xFF3C4835),
    background = Color(0xFF121B17), surface = Color(0xFF1B2721),
    surfaceVariant = Color(0xFF2B3931), onSurface = Color(0xFFE0EAE2)
)

@Composable
fun TeamAppTheme(darkTheme: Boolean = isSystemInDarkTheme(), dynamicColor: Boolean = false, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLightDesign provides !darkTheme) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
            shapes = if (darkTheme) Shapes() else Shapes(
                extraSmall = RoundedCornerShape(6.dp), small = RoundedCornerShape(9.dp),
                medium = RoundedCornerShape(14.dp), large = RoundedCornerShape(18.dp),
                extraLarge = RoundedCornerShape(24.dp)
            ),
            typography = Typography, content = content
        )
    }
}
