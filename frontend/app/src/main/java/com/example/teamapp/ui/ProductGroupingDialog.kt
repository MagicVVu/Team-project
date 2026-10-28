package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** A form snapshot is bound to the family in which the user confirmed it. */
internal data class ProductGroupingInput(val item: StockItem, val scope: String)

/** Shared by manual, voice and photo entry; a dismissed match prompt never creates stock. */
@Composable
internal fun ProductGroupingFlow(cloud: CloudStore, input: ProductGroupingInput?, clear: () -> Unit,
    busy: (Boolean) -> Unit, error: (String) -> Unit, saved: (String) -> Unit) {
    val s = rememberUiStrings()
    val coroutineScope = rememberCoroutineScope()
    val clearCallback by rememberUpdatedState(clear)
    val errorCallback by rememberUpdatedState(error)
    val savedCallback by rememberUpdatedState(saved)
    val busyCallback by rememberUpdatedState(busy)
    var review by remember { mutableStateOf<ProductGroupingReview?>(null) }
    var recovery by remember { mutableStateOf<ProductGroupingWrite?>(null) }
    var selected by remember { mutableStateOf<String?>(null) }
    var working by remember { mutableStateOf(false) }
    val blocked = working || review != null || recovery != null
    LaunchedEffect(blocked) { busyCallback(blocked) }
    DisposableEffect(Unit) { onDispose { busyCallback(false) } }

    fun failureMessage(failure: Exception): String = when ((failure as? CloudFailure)?.errorCode) {
        "GROUPING_CANDIDATE_CHANGED", "GROUPING_PRODUCT_CHANGED", "GROUPING_NAME_NO_LONGER_MATCHES" ->
            s.tr("库存或归类已被修改，请重新点击确认添加，核对最新的相似物品。", "Inventory or grouping changed. Confirm again to review the latest matching items.")
        else -> failure.message ?: s.tr("无法保存，信息已保留，请重试。", "Could not save. Your details are preserved; try again.")
    }

    suspend fun send(snapshot: ProductGroupingReview?, candidate: ProductGroupingMatch?, replay: ProductGroupingWrite? = null) {
        if (working) return
        working = true
        try {
            if (replay != null) cloud.replayGroupedInventory(replay)
            else cloud.createGroupedInventory(requireNotNull(snapshot), candidate)
            review = null; recovery = null
            clearCallback()
            savedCallback(replay?.itemId ?: requireNotNull(snapshot).item.id)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            review = null
            errorCallback(failureMessage(failure))
            recovery = runCatching { cloud.pendingProductGrouping() }.getOrNull()
            if (recovery == null) clearCallback()
        } finally { working = false }
    }

    LaunchedEffect(input) {
        val current = input ?: return@LaunchedEffect
        working = true
        try {
            require(current.scope == cloud.scopeKey && cloud.signedIn && !cloud.expired) {
                s.tr("账号或家庭已切换，请重新核对本次物品。", "The account or household changed. Review this item again.")
            }
            val outstanding = cloud.pendingProductGrouping()
            if (outstanding != null) {
                recovery = outstanding
            } else {
                val result = cloud.reviewProductGrouping(current.item)
                if (result.candidates.isEmpty()) {
                    working = false
                    send(result, null)
                } else {
                    review = result
                    selected = result.candidates.first().inventoryItemId
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            errorCallback(failureMessage(failure)); clearCallback()
        } finally { working = false }
    }
    LaunchedEffect(cloud.scopeKey) {
        if (review?.scope?.let { it != cloud.scopeKey } == true || recovery?.scope?.let { it != cloud.scopeKey } == true) {
            review = null; recovery = null; clearCallback()
            errorCallback(s.tr("账号或家庭已切换，请重新核对本次物品。", "The account or household changed. Review this item again."))
        }
    }

    review?.let { snapshot ->
        val selectedMatch = snapshot.candidates.firstOrNull { it.inventoryItemId == selected }
        AlertDialog(
            onDismissRequest = { if (!working) { review = null; clearCallback() } },
            modifier = Modifier.testTag("product-grouping-dialog"),
            title = { Text(s.tr("检测到相似物品", "Similar inventory found")) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(s.tr("检测到您库存中已经存在“${selectedMatch?.name.orEmpty()}”物品，是否归为同一类物品？",
                        "Your inventory already contains “${selectedMatch?.name.orEmpty()}”. Group these as the same product?"))
                    if (snapshot.candidates.size > 1) {
                        Text(s.tr("请选择要归入的物品类：", "Choose the item to group with:"), style = MaterialTheme.typography.labelLarge)
                        snapshot.candidates.forEach { candidate ->
                            Row(Modifier.fillMaxWidth().selectable(selected = selected == candidate.inventoryItemId, enabled = !working,
                                role = Role.RadioButton, onClick = { selected = candidate.inventoryItemId })
                                .testTag("product-grouping-candidate-${candidate.inventoryItemId}").padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = selected == candidate.inventoryItemId, onClick = null, enabled = !working)
                                Column(Modifier.weight(1f)) {
                                    Text(candidate.name)
                                    if (candidate.productName.isNotBlank()) Text(s.tr("所属商品：", "Product: ") + candidate.productName,
                                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                    Text(s.tr("是：归入所选物品类；否：为本次物品单独建立一个商品。各库存批次会分别保留。",
                        "Yes groups with the selected item. No creates a separate product. Inventory batches remain separate."),
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
            confirmButton = { TextButton(onClick = { coroutineScope.launch { send(snapshot, selectedMatch) } },
                enabled = !working && selectedMatch != null, modifier = Modifier.testTag("product-grouping-yes")) { Text(s.tr("是", "Yes")) } },
            dismissButton = {
                Row {
                    TextButton(onClick = { review = null; clearCallback() }, enabled = !working,
                        modifier = Modifier.testTag("product-grouping-cancel")) { Text(s.tr("取消", "Cancel")) }
                    TextButton(onClick = { coroutineScope.launch { send(snapshot, null) } }, enabled = !working,
                        modifier = Modifier.testTag("product-grouping-no")) { Text(s.tr("否", "No")) }
                }
            })
    }
    recovery?.let { original ->
        AlertDialog(onDismissRequest = { if (!working) { recovery = null; clearCallback() } },
            modifier = Modifier.testTag("product-grouping-recovery"),
            title = { Text(s.tr("核实上次保存结果", "Verify the previous save")) },
            text = { Text(s.tr("“${original.name}”的保存结果尚未核实。请使用原请求重试；不会再次添加相同批次。",
                "The save of “${original.name}” is not yet verified. Retry the original request; it will not add the same batch twice.")) },
            confirmButton = { TextButton(onClick = { coroutineScope.launch { send(null, null, original) } }, enabled = !working,
                modifier = Modifier.testTag("product-grouping-retry")) { Text(s.tr("按原请求重试", "Retry original request")) } },
            dismissButton = { TextButton(onClick = { recovery = null; clearCallback() }, enabled = !working) { Text(s.tr("稍后核实", "Verify later")) } })
    }
}
