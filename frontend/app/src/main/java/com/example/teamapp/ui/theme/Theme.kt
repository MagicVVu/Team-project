package com.example.teamapp.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColorScheme = lightColorScheme(
    primary = Color(0xFF247D67), onPrimary = Color.White,
    primaryContainer = Color(0xFFDCF1E6), onPrimaryContainer = Color(0xFF163D32),
    secondary = Color(0xFF647A6C), secondaryContainer = Color(0xFFEEF1DF),
    background = Color(0xFFF5F7F2), surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF263D33), onSurfaceVariant = Color(0xFF64766C),
    surfaceVariant = Color(0xFFEDF2EB), outline = Color(0xFFB2C3B7)
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
    MaterialTheme(colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme, typography = Typography, content = content)
}
