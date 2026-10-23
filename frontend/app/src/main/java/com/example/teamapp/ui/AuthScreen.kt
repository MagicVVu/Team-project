package com.example.teamapp.ui

import com.example.teamapp.ui.i18n.rememberUiStrings
import com.example.teamapp.R
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.BuildConfig
import com.example.teamapp.data.CloudApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.example.teamapp.data.validateAuthForm
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.theme.appearanceFade
import com.example.teamapp.ui.i18n.AppLanguageProvider

/** Guest navigation is separate from authentication; no credentials are stored on this device. */
@Composable
fun AppEntry(store: InventoryStore) {
    AppLanguageProvider(store.language) { AppEntryContent(store) }
}

@Composable
private fun AppEntryContent(store: InventoryStore) {
    var showAuth by rememberSaveable { mutableStateOf(!store.cloud.signedIn) }
    var entryVersion by rememberSaveable { mutableIntStateOf(0) }
    val owner = LocalContext.current as? LifecycleOwner
    LaunchedEffect(store.cloud.scopeKey, store.cloud.expired) {
        if (store.cloud.expired) showAuth = true
        if (store.cloud.signedIn && !store.cloud.expired && owner != null) {
            owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    runCatching { store.cloud.refresh() }
                    delay(30_000)
                }
            }
        }
    }
    AppMotionContent(Triple(showAuth, entryVersion, store.cloud.scopeKey), Modifier.fillMaxSize(), label = "authentication") { entry ->
        if (entry.first) AuthScreen(store) { entryVersion++; showAuth = false }
        else if (store.cloud.signedIn && store.cloud.account?.householdId.isNullOrBlank()) {
            CloudFamilySetup(store) { entryVersion++; showAuth = true }
        } else MagicApp(store, onOpenAuth = { entryVersion++; showAuth = true })
    }
}

@Composable
internal fun AuthScreen(store: InventoryStore? = null, onContinue: () -> Unit) {
    val strings = rememberUiStrings()
    var registering by rememberSaveable { mutableStateOf(false) }
    var formVersion by rememberSaveable { mutableIntStateOf(0) }
    var information by remember { mutableStateOf<String?>(null) }
    val focus = LocalFocusManager.current
    val scope = rememberCoroutineScope()
    val continueAsGuest = { focus.clearFocus(); scope.launch { store?.cloud?.logout(); onContinue() }; Unit }
    val colors = MaterialTheme.colorScheme
    BackHandler(registering) { focus.clearFocus(); formVersion++; registering = false }

    Surface(color = colors.background, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().imePadding()
                .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                MewstowWordmark(Modifier.width(176.dp).height(40.dp))
                Spacer(Modifier.weight(1f))
                TextButton(onClick = continueAsGuest) { Text(strings.get(R.string.ui_explore)) }
            }
            Spacer(Modifier.height(18.dp))
            Box(
                Modifier.size(112.dp).background(colors.primaryContainer, RoundedCornerShape(36.dp)),
                contentAlignment = Alignment.Center
            ) {
                MewMascot(MewPose.Welcome, Modifier.size(100.dp), "Mew 陪你记录生活")
            }
            AppMotionContent(registering, label = "auth-heading") { creatingAccount ->
                Text(if (creatingAccount) strings.get(R.string.ui_make_yourself_at_home) else strings.get(R.string.ui_welcome_home), fontSize = 27.sp,
                    fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 18.dp))
            }
            Text(strings.get(R.string.ui_every_little_thing__remembered), color = colors.onSurfaceVariant, fontSize = 13.sp,
                modifier = Modifier.padding(top = 8.dp, bottom = 24.dp))

            Card(
                modifier = Modifier.widthIn(max = 460.dp).fillMaxWidth(),
                shape = RoundedCornerShape(22.dp), border = BorderStroke(1.dp, colors.outlineVariant),
                colors = CardDefaults.cardColors(containerColor = colors.surface)
            ) {
                // A fresh key also clears credentials when a mode transition is quickly reversed.
                AppMotionContent(registering to formVersion, Modifier.fillMaxWidth(), label = "auth-form") { mode ->
                    val creatingAccount = mode.first
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(if (creatingAccount) strings.get(R.string.ui_create_account) else strings.get(R.string.ui_log_in_to_mewstow), style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            Text(if (creatingAccount) strings.get(R.string.ui_new_start) else strings.get(R.string.ui_welcome_back), fontSize = 11.sp, color = colors.onSurfaceVariant)
                        }
                        Text(if (creatingAccount) strings.get(R.string.ui_a_place_for_every_little_thing) else strings.get(R.string.ui_let_mew_help_you_remember_what),
                            fontSize = 12.sp, color = colors.onSurfaceVariant)
                        // Changing modes discards passwords; process recreation never restores them.
                        key(creatingAccount) {
                            AuthForm(creatingAccount, store, onContinue, onInformation = { information = it })
                        }
                        HorizontalDivider(color = colors.outlineVariant)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                            Text(if (creatingAccount) strings.get(R.string.ui_already_have_an_account) else strings.get(R.string.ui_new_to_mewstow), fontSize = 13.sp, color = colors.onSurfaceVariant)
                            TextButton(onClick = { focus.clearFocus(); formVersion++; registering = !creatingAccount }) {
                                Text(if (creatingAccount) strings.get(R.string.ui_log_in) else strings.get(R.string.ui_sign_up), fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }
            }
            TextButton(onClick = continueAsGuest, modifier = Modifier.padding(top = 12.dp)) { Text(strings.get(R.string.ui_continue_as_guest), fontSize = 13.sp) }
            Text(strings.get(R.string.ui_log_in_for_household_cloud_data), fontSize = 11.sp, color = colors.onSurfaceVariant,
                textAlign = TextAlign.Center, modifier = Modifier.padding(top = 4.dp))
            TextButton(onClick = { information = "登录时手机号与密码发送至应用配置的服务器，密码不会保存在设备上；登录令牌由 Android Keystore 加密保存。登录后库存、采购和家庭资料由服务器保存，并在家庭成员间共享；游客记录独立保留，不会自动上传。照片仍保留在当前设备。" }) {
                Text(strings.get(R.string.ui_data_and_privacy), fontSize = 11.sp)
            }
        }
    }
    information?.let { message ->
        AlertDialog(onDismissRequest = { information = null }, modifier = Modifier.appearanceFade(), title = { Text(if (message.startsWith("密码找回")) strings.get(R.string.ui_reset_password) else strings.get(R.string.ui_data_and_privacy)) },
            text = { Text(strings.label(message)) }, confirmButton = { TextButton(onClick = { information = null }) { Text(strings.get(R.string.ui_got_it)) } })
    }
}

@Composable
private fun AuthForm(registering: Boolean, store: InventoryStore?, onAuthenticated: () -> Unit, onInformation: (String) -> Unit) {
    val strings = rememberUiStrings()
    var nickname by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    val address = BuildConfig.CLOUD_API_URL
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf(emptyMap<String, String>()) }
    var serviceNotice by remember { mutableStateOf<String?>(null) }
    var submitting by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    fun changed(field: String) { errors = errors - field; serviceNotice = null }
    val submit = {
        focus.clearFocus()
        errors = validateAuthForm(registering, nickname, phone, password, confirmation)
        if (errors.isEmpty() && !submitting) {
            scope.launch {
                submitting = true
                try {
                    CloudApi.validateAddress(address)
                    checkNotNull(store) { "当前预览未连接账号服务，请从应用入口登录" }
                    store.cloud.login(address, phone, password, if (registering) nickname else null)
                    password = ""; confirmation = ""
                    onAuthenticated()
                } catch (failure: Exception) { serviceNotice = failure.message ?: "连接失败，请重试" }
                finally { submitting = false }
            }
        }
    }
    if (registering) AuthField("nickname", "昵称", nickname, { nickname = it; changed("nickname") }, errors["nickname"])
    AuthField("phone", "手机号", phone, { phone = it; changed("phone") }, errors["phone"], keyboardType = KeyboardType.Phone)
    if (address.isBlank()) Text(strings.get(R.string.ui_account_service_is_not_configured__please), color = MaterialTheme.colorScheme.error)
    AuthField("password", "密码", password, { password = it; changed("password"); errors = errors - "confirmation" }, errors["password"],
        password = true, hint = if (registering) "8–16 位英文字母和数字的组合，需同时包含两者" else null,
        done = !registering, onDone = submit)
    if (registering) AuthField("confirmation", "确认密码", confirmation, { confirmation = it; changed("confirmation") }, errors["confirmation"],
        password = true, done = true, onDone = submit)
    else Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        TextButton(onClick = { onInformation("密码找回暂未开放。请联系服务器管理员处理；手机号当前仅作为登录标识，尚未验证号码所有权。") }) { Text(strings.get(R.string.ui_forgot_password), fontSize = 12.sp) }
    }
    AnimatedVisibility(
        serviceNotice != null,
        enter = fadeIn(tween(AppMotion.Quick)) + expandVertically(tween(AppMotion.Duration, easing = AppMotion.easing)),
        exit = fadeOut(tween(AppMotion.Quick)) + shrinkVertically(tween(AppMotion.Duration, easing = AppMotion.easing))
    ) {
        Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = RoundedCornerShape(12.dp)) {
            Text(strings.label(serviceNotice.orEmpty()),
                fontSize = 12.sp, modifier = Modifier.padding(14.dp).testTag("auth-service-notice"))
        }
    }
    Button(onClick = submit, enabled = !submitting, modifier = Modifier.fillMaxWidth().height(50.dp).testTag("auth-submit"), shape = RoundedCornerShape(14.dp)) {
        Text(if (submitting) strings.get(R.string.ui_connecting) else if (registering) strings.get(R.string.ui_sign_up_and_log_in) else strings.get(R.string.ui_log_in_2), fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
    }
}

@Composable
private fun AuthField(
    tag: String, label: String, value: String, onChange: (String) -> Unit, error: String?,
    password: Boolean = false, hint: String? = null, keyboardType: KeyboardType = KeyboardType.Text,
    done: Boolean = false, onDone: () -> Unit = {}
) {
    val strings = rememberUiStrings()
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value, onChange, modifier = Modifier.fillMaxWidth()
            .animateContentSize(tween(AppMotion.Duration, easing = AppMotion.easing)).testTag("auth-$tag"),
        label = { Text(strings.label(label)) }, singleLine = true, shape = RoundedCornerShape(12.dp), isError = error != null,
        supportingText = if (error != null || hint != null) ({ Text(strings.label(error ?: hint.orEmpty())) }) else null,
        visualTransformation = if (password && !visible) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType,
            imeAction = if (done) ImeAction.Done else ImeAction.Next),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        trailingIcon = if (password) ({ TextButton(onClick = { visible = !visible }) { Text(if (visible) strings.get(R.string.ui_hide) else strings.get(R.string.ui_show), fontSize = 11.sp) } }) else null
    )
}
