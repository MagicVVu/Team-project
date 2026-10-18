package com.example.teamapp.ui

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
import com.example.teamapp.ui.theme.LocalLightDesign
import kotlinx.coroutines.launch

@Composable
internal fun SettingsPanel(store: InventoryStore, page: String, notify: (String) -> Unit, close: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var clear by remember { mutableStateOf(false) }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) runCatching { val output = context.contentResolver.openOutputStream(uri) ?: error("无法打开文件"); output.bufferedWriter().use { it.write(store.export()) } }.onSuccess { notify("数据已导出") }.onFailure { notify("导出失败，请重试") }
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        when (page) {
            "账号设置" -> {
                var name by rememberSaveable { mutableStateOf(store.nickname) }
                Text(if (store.cloud.signedIn) "云端个人资料" else "本机个人资料", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                ModeNotice(if (store.cloud.signedIn) "已连接 ${store.cloud.account?.address}。当前家庭：${store.family}。退出后返回独立的本机游客空间。" else "游客记录独立保存在本机；登录后可以使用家庭云端库存。")
                Field("昵称", name, { name = it })
                Button(enabled = !store.cloud.busy, onClick = { if (name.isBlank()) notify("请填写昵称") else scope.launch {
                    runCatching { store.profileSynced(name, store.family) }.onSuccess { notify("个人资料已保存"); close() }.onFailure { notify(it.message ?: "保存失败") }
                } }) { Text("保存资料") }
                if (store.cloud.signedIn) OutlinedButton(onClick = { scope.launch { store.cloud.logout(); notify("已退出账号，返回本机空间"); close() } }, enabled = !store.cloud.busy) { Text("退出登录") }
            }
            "我的家庭" -> {
                if (store.cloud.signedIn) CloudFamilyPanel(store, notify) else {
                var family by rememberSaveable { mutableStateOf(store.family) }
                Field("家庭名称", family, { family = it })
                Button(onClick = { if (family.isBlank()) notify("请填写家庭名称") else { store.profile(store.nickname, family); notify("家庭名称已保存") } }) { Text("保存家庭名称") }
                Text("家庭成员", fontWeight = FontWeight.Bold)
                ModeNotice("${store.nickname} · 本机管理员\n成员邀请与实时协作暂未开放。")
                }
                var location by rememberSaveable { mutableStateOf("") }
                val initialLocations = remember { store.locations.toSet() }
                Text("存放位置", fontWeight = FontWeight.Bold)
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
                Field("新增存放位置", location, { location = it })
                OutlinedButton(onClick = { if (location.isBlank()) notify("请填写位置名称") else { store.addLocation(location); location = ""; notify("位置已保存") } }) { Text("添加位置") }
            }
            "库存检测规则" -> {
                var days by rememberSaveable { mutableStateOf(store.reminderDays.toString()) }
                val minimums = remember { mutableStateMapOf<String, String>().apply { store.items.forEach { put(it.id, it.minimum.display()) } } }
                var error by remember { mutableStateOf("") }
                ModeNotice("当数量少于物品最低库存时提示不足。有效期当天仍为临期，次日起标记过期；未设置有效期不判断临期。")
                Field("提前提醒天数（0–365）", days, { days = it }, numeric = true)
                store.items.forEach { item -> key(item.id) { Field("${item.name}最低库存（${item.unit}）", minimums[item.id].orEmpty(), { minimums[item.id] = it }, numeric = true) } }
                if (store.items.isEmpty()) Text("添加物品后，可在这里分别设置最低库存。")
                MotionErrorText(error)
                Button(onClick = {
                    val d = days.toIntOrNull()
                    val values = minimums.mapValues { nonNegativeNumber(it.value) }
                    if (d == null || d !in 0..365 || values.values.any { it == null }) error = "请核对天数与最低库存，不能填写负数或无效数字。" else scope.launch {
                        runCatching { store.rulesSynced(d, values.mapValues { it.value!! }) }.onSuccess { notify("规则已保存，库存状态已更新"); close() }.onFailure { error = it.message ?: "保存失败，请刷新核对" }
                    }
                }, enabled = !store.cloud.busy) { Text("保存规则") }
            }
            "通用设置" -> {
                if (!LocalLightDesign.current) DarkGeneralSettings(store, notify) else {
                Text("界面语言：简体中文\n其他语言暂未开放。")
                Choice("外观模式", listOf("跟随系统", "浅色", "深色"), store.appearance) { store.updateAppearance(it); notify("外观已保存") }
                Text("计量单位按物品分别填写；不同单位不会自动换算。\n本机数据随每次确认保存，无需额外保存。")
                }
            }
            "消息通知" -> {
                ModeNotice("以下为 App 内提醒设置。关闭提醒后，库存页仍显示真实库存状态。初版尚未提供系统推送。")
                listOf("库存不足提醒", "有效期临期提醒", "过期物品提醒").forEachIndexed { i, label -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Text(label, modifier = Modifier.weight(1f)); Switch(store.notifications[i], { store.setNotification(i, it) }) } }
            }
            "隐私与安全" -> {
                Text("数据与权限说明", fontWeight = FontWeight.Bold)
                ModeNotice("游客记录保存在本机，不会自动上传。登录后库存、采购、昵称和家庭名称保存到所连接的服务器，并与家庭成员共享；设备保留按账号和家庭隔离的缓存。登录令牌加密保存，密码不落盘。系统语音服务可能联网，其数据处理由设备服务决定。")
                ModeNotice("相机：主动拍照时由系统相机拍摄。\n图库：仅访问你选择的照片。\n语音：主动启动系统识别服务时使用麦克风。\n通知：目前只有 App 内提醒，无系统推送权限。")
                ModeNotice("导出当前空间的库存和采购 JSON，不包含密码或登录令牌。照片不上传至服务器，也不嵌入导出文件。外观、提醒天数和位置快捷项属于当前设备设置。")
                Button(onClick = { export.launch("Mewstow-backup.json") }) { Text("导出当前数据") }
                if (!store.cloud.signedIn) {
                    TextButton(onClick = { clear = true }) { Text("清空库存与采购记录", color = Red) }
                    Text("清空后保留昵称、家庭空间与设置；选取的原始照片不会从系统图库删除。", style = MaterialTheme.typography.bodySmall)
                } else Text("云端家庭不提供批量清空，请逐项核对后删除。", style = MaterialTheme.typography.bodySmall)
            }
            "帮助与反馈" -> {
                Text("第一次使用", fontWeight = FontWeight.Bold)
                ModeNotice("1. 在首页拍照、语音或库存页手动添加物品。\n2. 核对名称、数量、单位与存放位置，确认保存。\n3. 设置最低库存及有效期，查看需关注物品。\n4. 加入采购清单，已购买后输入实际数量并确认入库。")
                Text("常见问题", fontWeight = FontWeight.Bold)
                ModeNotice("照片为什么没有自动识别？初版暂未连接图像识别服务，请根据照片填写信息。\n语音不可用？设备需要可处理中文语音的系统服务，也可手动输入原文。\n数据会丢失吗？重启仍保留；卸载或清除应用数据会删除本机记录，请先导出。\nAI 能做什么？本地助手根据已确认库存回答名称、过期和补货问题，不会自动修改记录。")
                var feedback by rememberSaveable { mutableStateOf("") }
                OutlinedTextField(feedback, { feedback = it }, label = { Text("问题或建议") }, minLines = 3, modifier = Modifier.fillMaxWidth())
                OutlinedButton(onClick = { if (feedback.isBlank()) notify("请先填写反馈") else runCatching { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, "Mewstow v1.0 反馈\n$feedback"), "选择反馈分享方式")) }.onFailure { notify("没有可用的分享应用") } }) { Text("分享反馈内容") }
                Text("分享仅打开系统分享面板，初版无在线反馈提交服务。", style = MaterialTheme.typography.bodySmall)
            }
            "关于 Mewstow" -> {
                if (!LocalLightDesign.current) DarkMaoYou(modifier = Modifier.fillMaxWidth().height(145.dp), description = "Mew · Nekomata 猫又")
                MewstowWordmark(Modifier.widthIn(max = 280.dp).fillMaxWidth().height(64.dp))
                Text("你的智能家庭物品管家", style = MaterialTheme.typography.titleMedium)
                Text(stringResource(R.string.brand_slogan), style = MaterialTheme.typography.bodyMedium)
                Text("猫又 ${stringResource(R.string.mascot_formal_name)} · 昵称 ${stringResource(R.string.mascot_nickname)}",
                    style = MaterialTheme.typography.titleSmall)
                Text("版本 1.0 · Android 初版\n围绕家里有什么、还有多少、放在哪里、什么时候补充，让家庭生活更有条理。")
                Text("支持游客本机空间、家庭云端库存及共享采购。本候选支持库存问答，以及用户确认后的添加、移动、消耗和手动采购草稿；实际可用动作以后端能力为准。图像识别、照片云端备份、开封、丢弃及自动规划确认暂未开放。数据说明见「隐私与安全」。")
            }
        }
        Spacer(Modifier.height(20.dp))
    }
    if (clear) Confirm("清空库存与采购记录？", "该操作不可撤销。建议先导出备份。个人资料与家庭设置保留。", { clear = false }) { store.clear(); clear = false; notify("库存与采购记录已清空"); close() }
}
