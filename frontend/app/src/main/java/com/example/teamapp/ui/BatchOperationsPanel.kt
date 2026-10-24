package com.example.teamapp.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.example.teamapp.data.*
import com.example.teamapp.ui.i18n.rememberUiStrings
import java.time.LocalDate

@Composable
internal fun BatchOperationsPanel(cloud: CloudStore, item: StockItem, initialAction: String = "CONSUME") {
    val s = rememberUiStrings()
    var action by rememberSaveable(cloud.scopeKey, item.id) { mutableStateOf(initialAction) }
    var quantity by rememberSaveable { mutableStateOf("") }
    var date by rememberSaveable { mutableStateOf("") }
    var question by rememberSaveable { mutableStateOf("") }
    var reviewing by rememberSaveable(cloud.scopeKey, item.id) { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val assistant = cloud.assistant
    if (reviewing) {
        Column(Modifier.fillMaxSize()) {
            Text("${item.name} · ${item.location} · ${item.quantityText} ${item.unit}", Modifier.padding(horizontal = 18.dp), style = MaterialTheme.typography.labelLarge)
            Text(s.tr("正在核对指定批次；只有最终确认后的业务回执表示执行成功。", "This exact batch is being reviewed. Only a final server receipt confirms execution."), Modifier.padding(horizontal = 18.dp), style = MaterialTheme.typography.bodySmall)
            CloudAssistant(cloud, showIntro = false)
        }
        return
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp).testTag("batch-operations"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        AlignmentCard(item.name) {
            Text("${item.quantityText} ${item.unit} · ${item.location}")
            Text(s.tr("批次：", "Batch: ") + item.id, style = MaterialTheme.typography.bodySmall)
            Text(s.tr("开封日期：", "Opened: ") + item.openedAt.ifBlank { s.tr("未登记", "Not recorded") })
            Text(s.tr("生命周期：", "Lifecycle: ") + item.lifecycleStatus, style = MaterialTheme.typography.bodySmall)
        }
        if (!InventoryContract.compatible(item)) {
            Text(s.tr("此旧记录的名称或单位与 AI 契约不兼容。请先编辑核对；不会自动改写。", "This legacy name or unit needs review before AI can use it. Edit it explicitly; no automatic conversion."), color = MaterialTheme.colorScheme.error)
        }
        ContractChoice(s.tr("本次操作", "Action"), listOf(
            Triple("CONSUME", "正式消耗", "Record consumption"), Triple("FINISH", "全部用完", "Use all remaining"),
            Triple("OPEN", "开封", "Open batch"), Triple("DISCARD", "部分丢弃", "Discard an amount"), Triple("DISCARD_ALL", "全部丢弃", "Discard all remaining"),
            Triple("ASK", "询问这批", "Ask about this batch"), Triple("STATS", "消费统计", "Consumption statistics"),
            Triple("FORECAST", "还能用多久", "How long will it last?"), Triple("RISK", "风险与缺失资料", "Risk & missing facts"), Triple("RESTOCK", "本次 AI 补货建议", "AI restock suggestion")), action) { action = it }
        val mutation = action in setOf("CONSUME", "FINISH", "OPEN", "DISCARD", "DISCARD_ALL")
        if (!item.activeBatch) Text(s.tr("该批次已结束，不能再绑定活动批次引用或执行业务操作；可在详情查看记录。", "This terminal batch cannot be bound as an active reference or mutated. Its records remain available in details."), color = MaterialTheme.colorScheme.error)
        if (action == "OPEN" && item.openedAt.isNotBlank()) Text(s.tr("此批次已有开封日期，不能重复开封。", "An opening date is already recorded; this batch cannot be opened twice."))
        when(action) {
            "CONSUME", "DISCARD" -> Field(s.tr("数量（${item.unit}）", "Quantity (${item.unit})"), quantity, { quantity = it }, numeric = true)
            "OPEN" -> Field(s.tr("实际开封日期 YYYY-MM-DD", "Actual opening date YYYY-MM-DD"), date, { date = it })
            "FINISH", "DISCARD_ALL" -> Text(s.tr("将以服务器核对的当前全部余量生成草稿，数量、单位及模式不可编辑。", "The server will use the current remaining amount. Quantity, unit and mode are protected."))
            "ASK" -> Field(s.tr("想问什么", "Your question"), question, { question = it })
        }
        Text(s.tr("正式消耗进入消费账本；丢弃与盘点差额不计入消费。先查询核对真实来源，再绑定这批并准备草稿，最终仍需你确认。", "Consumption enters the consumption ledger. Discards and count corrections do not. The app first verifies a real source, binds this batch, then asks you to review and confirm."), style = MaterialTheme.typography.bodySmall)
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
        Button(onClick = {
            try {
                val text = when(action) {
                    "CONSUME", "DISCARD" -> {
                        val amount = InventoryContract.amount(quantity, positive = true)
                        require(amount != null && amount <= item.quantityText.toBigDecimal()) { s.tr("数量须有效且不能超过当前余量，最多六位小数", "Use a positive amount within remaining stock, with up to six decimals") }
                        "${if (action == "CONSUME") "消耗" else "丢弃"}它 ${amount.toPlainString()} ${item.unit}"
                    }
                    "FINISH" -> "这批已经全部用完"
                    "OPEN" -> { LocalDate.parse(date); "这批在 $date 开封了" }
                    "DISCARD_ALL" -> "把这批全部余量丢弃"
                    "STATS" -> "查看它最近28天的消费统计"
                    "FORECAST" -> "这批还能用多久？"
                    "RISK" -> "评估这批的风险和缺少的标签储存资料"
                    "RESTOCK" -> "根据记录计算这批的补货建议，只展示建议，不提交采购"
                    else -> { require(question.isNotBlank() && question.length <= 800) { s.tr("请填写问题，最多 800 字", "Enter a question, up to 800 characters") }; question }
                }
                reviewing = true; assistant.launch { sendForBatch(item, text) }
            } catch (failure: Exception) { error = failure.message ?: s.tr("请核对输入", "Review your entries") }
        }, enabled = !assistant.busy && !cloud.expired && InventoryContract.compatible(item) && item.activeBatch && !(action == "OPEN" && item.openedAt.isNotBlank()),
            modifier = Modifier.fillMaxWidth().testTag("batch-prepare")) {
            Text(if (mutation) s.tr("核对批次并准备草稿", "Verify batch & prepare draft") else s.tr("核对批次并询问", "Verify batch & ask"))
        }
    }
}
