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
    // Sampled from ui/dark_ui: neutral gray surfaces and muted green controls.
    primary = Color(0xFF9BA78B), onPrimary = Color(0xFF20251C),
    primaryContainer = Color(0xFF373E32), onPrimaryContainer = Color(0xFFC6CEBA),
    secondary = Color(0xFFBEC6B2), onSecondary = Color(0xFF20251C),
    secondaryContainer = Color(0xFF292A2D), onSecondaryContainer = Color(0xFFE6E7E1),
    tertiary = Color(0xFFD8BD87), onTertiary = Color(0xFF302A20),
    tertiaryContainer = Color(0xFF3C3932), onTertiaryContainer = Color(0xFFE2C38B),
    background = Color(0xFF18191B), onBackground = Color(0xFFE6E7E1),
    surface = Color(0xFF242528), onSurface = Color(0xFFE6E7E1),
    surfaceVariant = Color(0xFF303135), onSurfaceVariant = Color(0xFFB8B9B3),
    surfaceContainerLowest = Color(0xFF18191B), surfaceContainerLow = Color(0xFF202124),
    surfaceContainer = Color(0xFF242528), surfaceContainerHigh = Color(0xFF292A2D),
    surfaceContainerHighest = Color(0xFF303135),
    outline = Color(0xFF565E4E), outlineVariant = Color(0xFF3D3F42),
    error = Color(0xFFDAAEA6), onError = Color(0xFF331B18),
    errorContainer = Color(0xFF473636), onErrorContainer = Color(0xFFDAAEA6)
)

@Composable
fun TeamAppTheme(darkTheme: Boolean = isSystemInDarkTheme(), dynamicColor: Boolean = false, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLightDesign provides !darkTheme) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
            shapes = if (darkTheme) Shapes(
                extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp),
                medium = RoundedCornerShape(18.dp), large = RoundedCornerShape(24.dp),
                extraLarge = RoundedCornerShape(32.dp)
            ) else Shapes(
                extraSmall = RoundedCornerShape(6.dp), small = RoundedCornerShape(9.dp),
                medium = RoundedCornerShape(14.dp), large = RoundedCornerShape(18.dp),
                extraLarge = RoundedCornerShape(24.dp)
            ),
            typography = Typography, content = content
        )
    }
}
