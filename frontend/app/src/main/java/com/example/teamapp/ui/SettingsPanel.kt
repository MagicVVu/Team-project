package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.R
import com.example.teamapp.BuildConfig
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.i18n.LanguageSettings
import kotlinx.coroutines.launch

@Composable
internal fun SettingsPanel(store: InventoryStore, page: String, notify: (String) -> Unit, close: () -> Unit) {
    val strings = rememberUiStrings()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var clear by remember { mutableStateOf(false) }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) runCatching { val output = context.contentResolver.openOutputStream(uri) ?: error("无法打开文件"); output.bufferedWriter().use { it.write(store.export()) } }.onSuccess { notify(strings.get(R.string.ui_data_exported)) }.onFailure { notify(strings.get(R.string.ui_export_failed__try_again)) }
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        when (page) {
            "账号设置" -> {
                var name by rememberSaveable { mutableStateOf(store.nickname) }
                Text(if (store.cloud.signedIn) strings.get(R.string.ui_cloud_profile) else strings.get(R.string.ui_local_profile), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                ModeNotice(if (store.cloud.signedIn) strings.get(R.string.ui_connected_as___household____logging, store.cloud.account?.address, store.family) else strings.get(R.string.ui_guest_records_stay_on_this_device))
                Field(strings.get(R.string.ui_nickname), name, { name = it })
                Button(enabled = !store.cloud.busy, onClick = { if (name.isBlank()) notify(strings.get(R.string.ui_enter_a_nickname)) else scope.launch {
                    runCatching { store.profileSynced(name, store.family) }.onSuccess { notify(strings.get(R.string.ui_profile_saved)); close() }.onFailure { notify(it.message ?: strings.get(R.string.ui_could_not_save)) }
                } }) { Text(strings.get(R.string.ui_save_profile)) }
                if (store.cloud.signedIn) OutlinedButton(onClick = { scope.launch { store.cloud.logout(); notify(strings.get(R.string.ui_logged_out__back_in_local_space)); close() } }, enabled = !store.cloud.busy) { Text(strings.get(R.string.ui_log_out_2)) }
            }
            "我的家庭" -> {
                if (store.cloud.signedIn) CloudFamilyPanel(store, notify) else {
                var family by rememberSaveable { mutableStateOf(store.family) }
                Field(strings.get(R.string.ui_household_name), family, { family = it })
                Button(onClick = { if (family.isBlank()) notify(strings.get(R.string.ui_enter_a_household_name)) else { store.profile(store.nickname, family); notify(strings.get(R.string.ui_household_name_saved)) } }) { Text(strings.get(R.string.ui_save_household_name)) }
                Text(strings.get(R.string.ui_household_members), fontWeight = FontWeight.Bold)
                ModeNotice(strings.get(R.string.ui___local_administrator_invites_and_live, store.nickname))
                }
                var location by rememberSaveable { mutableStateOf("") }
                val initialLocations = remember { store.locations.toSet() }
                Text(strings.get(R.string.ui_storage_location), fontWeight = FontWeight.Bold)
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    store.locations.forEach { place ->
                        key(place) {
                            val visible = remember {
                                MutableTransitionState(place in initialLocations).apply { targetState = true }
                            }
                            AnimatedVisibility(
                                visibleState = visible,
                                enter = fadeIn(tween(AppMotion.Quick)) + expandVertically(tween(AppMotion.Duration, easing = AppMotion.easing))
                            ) { Text("◇  $place") }
                        }
                    }
                }
                Field(strings.get(R.string.ui_new_storage_location), location, { location = it })
                OutlinedButton(onClick = { if (location.isBlank()) notify(strings.get(R.string.ui_enter_a_location_name)) else { store.addLocation(location); location = ""; notify(strings.get(R.string.ui_location_saved)) } }) { Text(strings.get(R.string.ui_add_location)) }
            }
            "库存检测规则" -> {
                var days by rememberSaveable { mutableStateOf(store.reminderDays.toString()) }
                val minimums = remember { mutableStateMapOf<String, String>().apply { store.items.forEach { put(it.id, it.minimum.display()) } } }
                var error by remember { mutableStateOf("") }
                ModeNotice(strings.get(R.string.ui_stock_is_low_when_the_quantity))
                Field(strings.get(R.string.ui_days_before_expiry_to_alert__0_365), days, { days = it }, numeric = true)
                store.items.forEach { item -> key(item.id) { Field(strings.get(R.string.ui_minimum_for, item.name, item.unit), minimums[item.id].orEmpty(), { minimums[item.id] = it }, numeric = true) } }
                if (store.items.isEmpty()) Text(strings.get(R.string.ui_add_items_first_to_set_their))
                MotionErrorText(error)
                Button(onClick = {
                    val d = days.toIntOrNull()
                    val values = minimums.mapValues { nonNegativeNumber(it.value) }
                    if (d == null || d !in 0..365 || values.values.any { it == null }) error = "请核对天数与最低库存，不能填写负数或无效数字。" else scope.launch {
                        runCatching { store.rulesSynced(d, values.mapValues { it.value!! }) }.onSuccess { notify(strings.get(R.string.ui_rules_saved_and_stock_status_updated)); close() }.onFailure { error = it.message ?: "保存失败，请刷新核对" }
                    }
                }, enabled = !store.cloud.busy) { Text(strings.get(R.string.ui_save_rules)) }
            }
            "通用设置" -> {
                if (!LocalLightDesign.current) DarkGeneralSettings(store, notify) else {
                LanguageSettings(store)
                Choice(strings.get(R.string.ui_appearance), listOf("跟随系统", "浅色", "深色"), store.appearance, translateOptions = true) { store.updateAppearance(it); notify(strings.get(R.string.ui_appearance_saved)) }
                Text(strings.get(R.string.ui_units_are_set_per_item_and_2))
                }
            }
            "消息通知" -> {
                ModeNotice(strings.get(R.string.ui_these_are_in_app_alerts__turning_them))
                listOf("库存不足提醒", "有效期临期提醒", "过期物品提醒").forEachIndexed { i, label -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Text(strings.label(label), modifier = Modifier.weight(1f)); Switch(store.notifications[i], { store.setNotification(i, it) }) } }
            }
            "隐私与安全" -> {
                Text(strings.get(R.string.ui_data_and_permissions), fontWeight = FontWeight.Bold)
                ModeNotice(strings.get(R.string.ui_guest_records_stay_on_this_device_2))
                ModeNotice(strings.get(R.string.ui_camera__opened_only_when_you_choose))
                ModeNotice(strings.get(R.string.ui_export_inventory_and_shopping_as_json))
                Button(onClick = { export.launch("Mewstow-backup.json") }) { Text(strings.get(R.string.ui_export_current_data)) }
                if (!store.cloud.signedIn) {
                    TextButton(onClick = { clear = true }) { Text(strings.get(R.string.ui_clear_stock_and_shopping_records), color = Red) }
                    Text(strings.get(R.string.ui_your_profile__household_and_settings_are), style = MaterialTheme.typography.bodySmall)
                } else Text(strings.get(R.string.ui_cloud_households_do_not_support_clearing), style = MaterialTheme.typography.bodySmall)
            }
            "帮助与反馈" -> {
                Text(strings.get(R.string.ui_getting_started), fontWeight = FontWeight.Bold)
                ModeNotice(strings.get(R.string.ui_1__add_items_by_photo__voice))
                Text(strings.get(R.string.ui_common_questions), fontWeight = FontWeight.Bold)
                ModeNotice(strings.get(R.string.ui_why_are_photos_not_recognized__image))
                var feedback by rememberSaveable { mutableStateOf("") }
                OutlinedTextField(feedback, { feedback = it }, label = { Text(strings.get(R.string.ui_question_or_suggestion)) }, minLines = 3, modifier = Modifier.fillMaxWidth())
                OutlinedButton(onClick = { if (feedback.isBlank()) notify(strings.get(R.string.ui_enter_your_feedback_first)) else runCatching { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, strings.get(R.string.ui_mewstow_feedback, BuildConfig.VERSION_NAME, feedback)), strings.get(R.string.ui_share_feedback_with))) }.onFailure { notify(strings.get(R.string.ui_no_sharing_app_is_available)) } }) { Text(strings.get(R.string.ui_share_feedback)) }
                Text(strings.get(R.string.ui_opens_the_system_share_sheet__online), style = MaterialTheme.typography.bodySmall)
            }
            "关于 Mewstow" -> {
                MewMascot(MewPose.Overview, Modifier.fillMaxWidth().height(145.dp), strings.get(R.string.ui_mew___nekomata))
                MewstowWordmark(Modifier.widthIn(max = 280.dp).fillMaxWidth().height(64.dp))
                Text(strings.get(R.string.ui_your_household_inventory_companion), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(R.string.brand_slogan), style = MaterialTheme.typography.bodyMedium)
                Text(strings.get(R.string.ui_cat_companion___nickname, stringResource(R.string.mascot_formal_name), stringResource(R.string.mascot_nickname)),
                    style = MaterialTheme.typography.titleSmall)
                Text(strings.get(R.string.ui_version___android_keep_track_of, BuildConfig.VERSION_NAME))
                Text(strings.get(R.string.ui_supports_local_guest_records__household_cloud))
            }
        }
        Spacer(Modifier.height(20.dp))
    }
    if (clear) Confirm(strings.get(R.string.ui_clear_stock_and_shopping_records_2), strings.get(R.string.ui_this_cannot_be_undone__export_a), { clear = false }) { store.clear(); clear = false; notify(strings.get(R.string.ui_stock_and_shopping_records_cleared)); close() }
}
