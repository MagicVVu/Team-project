package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.CloudMember
import com.example.teamapp.data.CloudStore
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.launch

@Composable
internal fun FamilyManagement(cloud: CloudStore, members: List<CloudMember>, changed: () -> Unit) {
    val s = rememberUiStrings()
    val scope = rememberCoroutineScope()
    var action by rememberSaveable(cloud.scopeKey) { mutableStateOf("") }
    var target by remember { mutableStateOf<CloudMember?>(null) }
    var confirmation by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    var working by remember { mutableStateOf(false) }
    val actor = cloud.household?.role
    fun label(role: String) = when(role) { "owner" -> s.tr("所有者", "Owner"); "admin" -> s.tr("管理员", "Admin"); else -> s.tr("成员", "Member") }
    fun actionLabel(key: String) = when(key) {
        "remove" -> s.tr("移除成员", "Remove member"); "admin" -> s.tr("设为管理员", "Make admin")
        "member" -> s.tr("取消管理员", "Remove admin role"); "transfer" -> s.tr("转让家庭", "Transfer ownership")
        "dissolve" -> s.tr("解散家庭", "Dissolve household"); else -> s.tr("退出家庭", "Leave household")
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (members.isEmpty()) Text(s.tr("成员列表尚未读取，请刷新后管理。", "Refresh the member list before managing roles."))
        OutlinedButton(onClick = changed, enabled = !working && !cloud.busy) { Text(s.tr("刷新成员与权限", "Refresh members & roles")) }
        members.forEach { member ->
            AlignmentCard(member.name) {
                Text(label(member.role) + if (member.userId == cloud.account?.userId) s.tr(" · 我", " · Me") else "")
                Text(s.tr("加入时间：", "Joined: ") + member.joinedAt, style = MaterialTheme.typography.bodySmall)
                if (member.userId != cloud.account?.userId && member.role != "owner") {
                    if (actor == "owner") {
                        TextButton(onClick = { target = member; action = if (member.role == "admin") "member" else "admin" }, enabled = !working && !cloud.busy) { Text(actionLabel(if (member.role == "admin") "member" else "admin")) }
                        TextButton(onClick = { target = member; action = "transfer" }, enabled = !working && !cloud.busy) { Text(actionLabel("transfer")) }
                    }
                    if (actor == "owner" || actor == "admin" && member.role == "member") TextButton(onClick = { target = member; action = "remove" }, enabled = !working && !cloud.busy) { Text(actionLabel("remove"), color = MaterialTheme.colorScheme.error) }
                }
            }
        }
        if (actor == "owner") {
            Text(s.tr("所有者退出前须先转让或解散家庭。", "Owners must transfer ownership or dissolve the household before leaving."), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { action = "dissolve"; target = null; confirmation = "" }, enabled = !working && !cloud.busy) { Text(actionLabel("dissolve"), color = MaterialTheme.colorScheme.error) }
        } else if (actor != null) TextButton(onClick = { action = "leave"; target = null }, enabled = !working && !cloud.busy) { Text(actionLabel("leave"), color = MaterialTheme.colorScheme.error) }
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
    }
    if (action.isNotBlank()) AlertDialog(onDismissRequest = { if (!working) action = "" },
        title = { Text(actionLabel(action)) }, text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(target?.name ?: cloud.household?.name.orEmpty())
                Text(when(action) {
                    "dissolve" -> s.tr("将删除当前家庭及其共享库存、采购、任务和事件记录。输入完整家庭名以确认。", "This deletes this household and its shared inventory, shopping, tasks and events. Enter the full household name to confirm.")
                    "transfer" -> s.tr("确认后你将成为普通成员，管理权限交给选中的现有成员。", "You will become a regular member and transfer ownership to the selected existing member.")
                    "leave", "remove" -> s.tr("确认后将失去此家庭的访问权限；家庭共享记录保留。", "Access to this household will be removed; shared records remain.")
                    else -> s.tr("权限最终由服务器核验，其他成员资料不会更改。", "The server verifies permissions; other members' facts remain unchanged.")
                })
                if (action == "dissolve") Field(s.tr("完整家庭名", "Full household name"), confirmation, { confirmation = it })
                if (working) LinearProgressIndicator(Modifier.fillMaxWidth())
            }
        }, dismissButton = { TextButton(onClick = { action = "" }, enabled = !working) { Text(s.tr("取消", "Cancel")) } },
        confirmButton = { TextButton(onClick = {
            val selectedAction = action; val memberId = target?.userId.orEmpty()
            working = true
            scope.launch {
                runCatching { cloud.manageFamily(selectedAction, memberId, confirmation) }
                    .onSuccess { action = ""; error = ""; changed() }
                    .onFailure { failure -> error = if (s.english) "Could not change the household. Refresh permissions and review again." else failure.message.orEmpty(); action = ""; runCatching { cloud.refresh() }; changed() }
                working = false
            }
        }, enabled = !working && !cloud.expired && (action != "dissolve" || confirmation == cloud.household?.name), modifier = Modifier.testTag("family-confirm-management")) { Text(s.tr("确认操作", "Confirm action")) } })
}
