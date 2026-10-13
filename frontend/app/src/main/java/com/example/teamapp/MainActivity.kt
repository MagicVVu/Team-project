package com.example.teamapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.remember
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.theme.TeamAppTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val store = remember { InventoryStore(applicationContext) }
            val dark = when (store.appearance) { "深色" -> true; "浅色" -> false; else -> isSystemInDarkTheme() }
            TeamAppTheme(darkTheme = dark, dynamicColor = false) { MagicApp(store) }
        }
    }
}
