package com.example.teamapp.ui

import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** A form snapshot is bound to the family in which the user confirmed it. */
internal data class ProductGroupingInput(val item: StockItem, val scope: String)

/** The server automatically groups names and creates one durable row per object. */
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
    LaunchedEffect(working, recovery) { busyCallback(working || recovery != null) }
    DisposableEffect(Unit) { onDispose { busyCallback(false) } }

    suspend fun send(current: ProductGroupingInput? = null, original: ProductGroupingWrite? = null) {
        if (working) return
        working = true
        try {
            if (original != null) cloud.replayGroupedInventory(original)
            else {
                val snapshot = requireNotNull(current)
                require(snapshot.scope == cloud.scopeKey && cloud.signedIn && !cloud.expired) {
                    s.tr("账号或家庭已切换，请重新核对本次物品。", "The account or household changed. Review this item again.")
                }
                cloud.createGroupedInventory(ProductGroupingReview(snapshot.scope, snapshot.item, emptyList()), null)
            }
            recovery = null
            clearCallback()
            savedCallback(original?.itemId ?: requireNotNull(current).item.id)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
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
            if (outstanding != null) recovery = outstanding else send(current)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { errorCallback(failure.message.orEmpty()); clearCallback() }
    }
    LaunchedEffect(cloud.scopeKey) {
        if (recovery?.scope?.let { it != cloud.scopeKey } == true) {
            recovery = null; clearCallback()
            errorCallback(s.tr("账号或家庭已切换，请回到原家庭核实保存结果。", "Return to the original household to verify the save."))
        }
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
