package com.example.teamapp.ui

import androidx.compose.material3.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** A form snapshot is bound to the family in which the user confirmed it. */
internal data class ProductGroupingInput(val item: StockItem, val scope: String)

/** Review matching products before submitting an explicitly chosen request. */
@Composable
internal fun ProductGroupingFlow(cloud: CloudStore, input: ProductGroupingInput?, clear: () -> Unit,
    busy: (Boolean) -> Unit, error: (String) -> Unit, saved: (String) -> Unit) {
    val s = rememberUiStrings()
    val coroutineScope = rememberCoroutineScope()
    val clearCallback by rememberUpdatedState(clear)
    val errorCallback by rememberUpdatedState(error)
    val savedCallback by rememberUpdatedState(saved)
    val busyCallback by rememberUpdatedState(busy)
    var recovery by remember { mutableStateOf<ProductGroupingWrite?>(null) }
    var working by remember { mutableStateOf(false) }
    var review by remember { mutableStateOf<ProductGroupingReview?>(null) }
    var selected by remember { mutableStateOf<ProductGroupingMatch?>(null) }
    LaunchedEffect(working, recovery, review) { busyCallback(working || recovery != null || review != null) }
    DisposableEffect(Unit) { onDispose { busyCallback(false) } }

    suspend fun send(current: ProductGroupingInput? = null, original: ProductGroupingWrite? = null,
                     reviewed: ProductGroupingReview? = null, match: ProductGroupingMatch? = null) {
        if (working) return
        working = true
        try {
            if (original != null) cloud.replayGroupedInventory(original)
            else {
                val snapshot = requireNotNull(current)
                require(snapshot.scope == cloud.scopeKey && cloud.signedIn && !cloud.expired) {
                    s.tr("账号或家庭已切换，请重新核对本次物品。", "The account or household changed. Review this item again.")
                }
                cloud.createGroupedInventory(requireNotNull(reviewed), match)
            }
            recovery = null
            review = null
            clearCallback()
            savedCallback(original?.itemId ?: requireNotNull(current).item.id)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            review = null
            errorCallback(failure.message ?: s.tr("无法保存，信息已保留，请重试。", "Could not save. Your details are preserved; try again."))
            recovery = runCatching { cloud.pendingProductGrouping() }.getOrNull()
            if (recovery == null) clearCallback()
        } finally { working = false }
    }

    LaunchedEffect(input) {
        val current = input ?: return@LaunchedEffect
        try {
            require(current.scope == cloud.scopeKey && cloud.signedIn && !cloud.expired) {
                s.tr("账号或家庭已切换，请重新核对本次物品。", "The account or household changed. Review this item again.")
            }
            val outstanding = cloud.pendingProductGrouping()
            if (outstanding != null) recovery = outstanding else {
                working = true
                val found = try { cloud.reviewProductGrouping(current.item) } finally { working = false }
                if (found.candidates.isEmpty()) send(current, reviewed = found)
                else {
                    review = found.copy(candidates = found.candidates.distinctBy { it.productId ?: it.inventoryItemId })
                    selected = review!!.candidates.first()
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { errorCallback(failure.message.orEmpty()); clearCallback() }
    }
    LaunchedEffect(cloud.scopeKey) {
        if (review?.scope?.let { it != cloud.scopeKey } == true) {
            review = null; clearCallback()
            errorCallback(s.tr("账号或家庭已切换，请重新核对物品归类。", "Review grouping again after switching households."))
        }
        if (recovery?.scope?.let { it != cloud.scopeKey } == true) {
            recovery = null; clearCallback()
            errorCallback(s.tr("账号或家庭已切换，请回到原家庭核实保存结果。", "Return to the original household to verify the save."))
        }
    }
    review?.let { current ->
        AlertDialog(onDismissRequest = { if (!working) { review = null; clearCallback() } },
            modifier = Modifier.testTag("product-grouping-dialog"),
            title = { Text(s.tr("是否归为一类物品？", "Group these items together?")) },
            text = { Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                Text(s.tr("发现名称相同或连续至少两个字相同的物品。请选择是否将“${current.item.name}”归入已有类别；每件仍独立保存。",
                    "A matching name was found. Choose a product for “${current.item.name}”, or keep it separate. Each item keeps its own record."))
                current.candidates.forEach { candidate ->
                    Row {
                        RadioButton(selected = selected == candidate, onClick = { selected = candidate }, enabled = !working,
                            modifier = Modifier.testTag("grouping-candidate-${candidate.inventoryItemId}"))
                        Text(candidate.productName.ifBlank { candidate.name })
                    }
                }
                TextButton(onClick = { review = null; clearCallback() }, enabled = !working) { Text(s.tr("取消添加", "Cancel")) }
            } },
            confirmButton = { TextButton(onClick = { coroutineScope.launch {
                send(ProductGroupingInput(current.item, current.scope), reviewed = current, match = selected)
            } }, enabled = !working && selected != null, modifier = Modifier.testTag("product-grouping-merge")) {
                Text(s.tr("归为一类", "Group together"))
            } },
            dismissButton = { TextButton(onClick = { coroutineScope.launch {
                send(ProductGroupingInput(current.item, current.scope), reviewed = current)
            } }, enabled = !working, modifier = Modifier.testTag("product-grouping-separate")) {
                Text(s.tr("单独归类", "Keep separate"))
            } })
    }
    recovery?.let { original ->
        AlertDialog(onDismissRequest = { if (!working) { recovery = null; clearCallback() } },
            modifier = Modifier.testTag("product-grouping-recovery"),
            title = { Text(s.tr("核实上次保存结果", "Verify the previous save")) },
            text = { Text(s.tr("“${original.name}”的保存结果尚未核实。请使用原请求重试，已创建的物品不会重复添加。",
                "The save of “${original.name}” is not yet verified. Retry the original request; existing items will not be added twice.")) },
            confirmButton = { TextButton(onClick = { coroutineScope.launch { send(original = original) } }, enabled = !working,
                modifier = Modifier.testTag("product-grouping-retry")) { Text(s.tr("按原请求重试", "Retry original request")) } },
            dismissButton = { TextButton(onClick = { recovery = null; clearCallback() }, enabled = !working) { Text(s.tr("稍后核实", "Verify later")) } })
    }
}
