package com.example.teamapp.ui.i18n

import android.content.Context
import android.content.res.Configuration
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.data.InventoryStore
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

internal val LocalAppLanguage = staticCompositionLocalOf { "zh-CN" }

/** UI locale only: navigation keys, server requests and user records keep their original values. */
@Composable
internal fun AppLanguageProvider(language: String, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalAppLanguage provides language, content = content)
}

internal class UiStrings(context: Context, val language: String) {
    val english = language == "en"
    val locale: Locale = if (english) Locale.ENGLISH else Locale.SIMPLIFIED_CHINESE
    private val localized = context.createConfigurationContext(Configuration(context.resources.configuration).apply { setLocale(this@UiStrings.locale) })

    fun get(@StringRes id: Int, vararg args: Any?): String =
        if (args.isEmpty()) localized.getString(id) else localized.getString(id, *args)

    /** For built-in labels only. Never pass user-entered names, locations, units or conversation text. */
    fun label(value: String): String = UiTextIds.labels[value]?.let { get(it) } ?: value

    fun itemCount(count: Int): String = localized.resources.getQuantityString(R.plurals.ui_item_count, count, count)
    fun stockCount(count: Int): String = localized.resources.getQuantityString(R.plurals.ui_stock_count, count, count)
    fun days(count: Long): String = localized.resources.getQuantityString(R.plurals.ui_day_count, if (count == 1L) 1 else 2, count)

    fun today(): String = LocalDate.now().format(if (english)
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale)
        else DateTimeFormatter.ofPattern("M月d日", locale))
}

@Composable
internal fun rememberUiStrings(): UiStrings {
    val context = LocalContext.current
    val language = LocalAppLanguage.current
    return remember(context, language) { UiStrings(context, language) }
}

@Composable
internal fun LanguageSettings(store: InventoryStore) {
    val strings = rememberUiStrings()
    var saveFailed by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(strings.get(R.string.ui_language))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("zh-CN" to "简体中文", "en" to "English").forEach { (code, label) ->
                FilterChip(selected = store.language == code, onClick = { saveFailed = !store.updateLanguage(code) },
                    label = { Text(label) }, modifier = Modifier.testTag("language-$code"))
            }
        }
        if (saveFailed) Text(strings.get(R.string.ui_language_save_error), color = MaterialTheme.colorScheme.error)
    }
}
