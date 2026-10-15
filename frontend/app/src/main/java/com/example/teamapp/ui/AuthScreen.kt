package com.example.teamapp.ui

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
import com.example.teamapp.data.validateAuthForm
import com.example.teamapp.ui.theme.LocalLightDesign
import com.example.teamapp.ui.theme.appearanceFade

/** Guest navigation is separate from authentication; no credentials are stored on this device. */
@Composable
fun AppEntry(store: InventoryStore) {
    var showAuth by rememberSaveable { mutableStateOf(true) }
    var entryVersion by rememberSaveable { mutableIntStateOf(0) }
    AppMotionContent(showAuth to entryVersion, Modifier.fillMaxSize(), label = "authentication") { entry ->
        if (entry.first) AuthScreen { entryVersion++; showAuth = false }
        else MagicApp(store, onOpenAuth = { entryVersion++; showAuth = true })
    }
}

@Composable
internal fun AuthScreen(onContinue: () -> Unit) {
    var registering by rememberSaveable { mutableStateOf(false) }
    var formVersion by rememberSaveable { mutableIntStateOf(0) }
    var information by remember { mutableStateOf<String?>(null) }
    val focus = LocalFocusManager.current
    val continueAsGuest = { focus.clearFocus(); onContinue() }
    val light = LocalLightDesign.current
    val colors = MaterialTheme.colorScheme
    BackHandler(registering) { focus.clearFocus(); formVersion++; registering = false }

    Surface(color = colors.background, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().imePadding()
                .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                DesignGlyph("leaf", Modifier.size(25.dp), colors.primary)
                Text("拾物", fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 8.dp))
                Spacer(Modifier.weight(1f))
                TextButton(onClick = continueAsGuest) { Text("先逛逛 ›") }
            }
            Spacer(Modifier.height(18.dp))
            Box(
                Modifier.size(112.dp).background(colors.primaryContainer, RoundedCornerShape(36.dp)),
                contentAlignment = Alignment.Center
            ) {
                if (light) AppMotionContent(registering, label = "auth-mascot") { creatingAccount ->
                    MaoYou(if (creatingAccount) 8 else 3, Modifier.size(100.dp), "猫又陪你记录生活")
                }
                else DarkMaoYou(modifier = Modifier.size(100.dp, 86.dp), description = "猫又陪你记录生活")
            }
            AppMotionContent(registering, label = "auth-heading") { creatingAccount ->
                Text(if (creatingAccount) "一起，把家照顾好" else "你好，欢迎回家", fontSize = 27.sp,
                    fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 18.dp))
            }
            Text("家的小物，慢慢记好。", color = colors.onSurfaceVariant, fontSize = 13.sp,
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
                            Text(if (creatingAccount) "创建账号" else "登录拾物", style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            Text("${if (creatingAccount) "新的开始" else "好久不见"} 🌿", fontSize = 11.sp, color = colors.onSurfaceVariant)
                        }
                        Text(if (creatingAccount) "给生活中的每一件小物，留一个位置。" else "让猫又陪你，记好家里的每一件小物。",
                            fontSize = 12.sp, color = colors.onSurfaceVariant)
                        // Changing modes discards passwords; process recreation never restores them.
                        key(creatingAccount) {
                            AuthForm(creatingAccount, onInformation = { information = it })
                        }
                        HorizontalDivider(color = colors.outlineVariant)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                            Text(if (creatingAccount) "已经有账号？" else "还没有账号？", fontSize = 13.sp, color = colors.onSurfaceVariant)
                            TextButton(onClick = { focus.clearFocus(); formVersion++; registering = !creatingAccount }) {
                                Text(if (creatingAccount) "去登录" else "去注册", fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }
            }
            TextButton(onClick = continueAsGuest, modifier = Modifier.padding(top = 12.dp)) { Text("以游客身份体验", fontSize = 13.sp) }
            Text("账号服务准备中 · 当前可使用本机库存空间", fontSize = 11.sp, color = colors.onSurfaceVariant,
                textAlign = TextAlign.Center, modifier = Modifier.padding(top = 4.dp))
            TextButton(onClick = { information = "库存、采购和个人资料保存在本机应用私有空间。当前登录与注册表单不会上传或保存邮箱、密码；卸载或清除应用数据会删除本机记录。账号服务接入后，将提供对应的服务条款与隐私政策。" }) {
                Text("数据与隐私说明", fontSize = 11.sp)
            }
        }
    }
    information?.let { message ->
        AlertDialog(onDismissRequest = { information = null }, modifier = Modifier.appearanceFade(), title = { Text(if (message.startsWith("密码找回")) "找回密码" else "数据与隐私说明") },
            text = { Text(message) }, confirmButton = { TextButton(onClick = { information = null }) { Text("知道了") } })
    }
}

@Composable
private fun AuthForm(registering: Boolean, onInformation: (String) -> Unit) {
    var nickname by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf(emptyMap<String, String>()) }
    var serviceNotice by remember { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    fun changed(field: String) { errors = errors - field; serviceNotice = false }
    val submit = {
        focus.clearFocus()
        errors = validateAuthForm(registering, nickname, email, password, confirmation)
        serviceNotice = errors.isEmpty()
    }
    if (registering) AuthField("nickname", "昵称", nickname, { nickname = it; changed("nickname") }, errors["nickname"])
    AuthField("email", "邮箱", email, { email = it; changed("email") }, errors["email"], keyboardType = KeyboardType.Email)
    AuthField("password", "密码", password, { password = it; changed("password"); errors = errors - "confirmation" }, errors["password"],
        password = true, hint = if (registering) "8–64 位，包含字母和数字" else null,
        done = !registering, onDone = submit)
    if (registering) AuthField("confirmation", "确认密码", confirmation, { confirmation = it; changed("confirmation") }, errors["confirmation"],
        password = true, done = true, onDone = submit)
    else Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        TextButton(onClick = { onInformation("密码找回将在账号服务接入后开放。当前可以使用游客入口管理本机库存，无需填写账号或密码。") }) { Text("忘记密码？", fontSize = 12.sp) }
    }
    AnimatedVisibility(
        serviceNotice,
        enter = fadeIn(tween(AppMotion.Quick)) + expandVertically(tween(AppMotion.Duration, easing = AppMotion.easing)),
        exit = fadeOut(tween(AppMotion.Quick)) + shrinkVertically(tween(AppMotion.Duration, easing = AppMotion.easing))
    ) {
        Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = RoundedCornerShape(12.dp)) {
            Text("账号服务尚未接入，暂时无法${if (registering) "创建账号" else "登录"}。请使用下方游客入口体验，表单信息不会被保存。",
                fontSize = 12.sp, modifier = Modifier.padding(14.dp).testTag("auth-service-notice"))
        }
    }
    Button(onClick = submit, modifier = Modifier.fillMaxWidth().height(50.dp).testTag("auth-submit"), shape = RoundedCornerShape(14.dp)) {
        Text(if (registering) "注册" else "登录", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
    }
}

@Composable
private fun AuthField(
    tag: String, label: String, value: String, onChange: (String) -> Unit, error: String?,
    password: Boolean = false, hint: String? = null, keyboardType: KeyboardType = KeyboardType.Text,
    done: Boolean = false, onDone: () -> Unit = {}
) {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value, onChange, modifier = Modifier.fillMaxWidth()
            .animateContentSize(tween(AppMotion.Duration, easing = AppMotion.easing)).testTag("auth-$tag"),
        label = { Text(label) }, singleLine = true, shape = RoundedCornerShape(12.dp), isError = error != null,
        supportingText = if (error != null || hint != null) ({ Text(error ?: hint.orEmpty()) }) else null,
        visualTransformation = if (password && !visible) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType,
            imeAction = if (done) ImeAction.Done else ImeAction.Next),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        trailingIcon = if (password) ({ TextButton(onClick = { visible = !visible }) { Text(if (visible) "隐藏" else "显示", fontSize = 11.sp) } }) else null
    )
}
