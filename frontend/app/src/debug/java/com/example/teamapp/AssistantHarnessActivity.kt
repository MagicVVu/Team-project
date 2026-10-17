package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.MagicApp
import com.example.teamapp.ui.AppEntry
import com.example.teamapp.ui.theme.TeamAppTheme

/** Non-exported debug host for real Activity recreation with isolated test preferences. */
class AssistantHarnessActivity : ComponentActivity() {
    lateinit var store: InventoryStore; private set
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefix = requireNotNull(intent.getStringExtra("test_namespace"))
        require(prefix.matches(Regex("p4ui_[a-f0-9]{32}_")))
        val isolated = object : ContextWrapper(applicationContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
        store = InventoryStore(isolated)
        setContent { TeamAppTheme(darkTheme = intent.getBooleanExtra("dark", false)) {
            if (intent.getBooleanExtra("auth_entry", false)) AppEntry(store) else MagicApp(store)
        } }
    }
}
