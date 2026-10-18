package com.example.teamapp.ui.ring

import androidx.activity.compose.BackHandler
import androidx.activity.compose.LocalActivity
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import com.example.teamapp.data.*
import com.example.teamapp.ui.DarkNavigation
import com.example.teamapp.ui.DesignNavigation
import com.example.teamapp.ui.DesignGlyph
import com.example.teamapp.ui.AppMotion
import com.example.teamapp.ui.AppMotionContent
import com.example.teamapp.ui.theme.TeamAppTheme
import com.example.teamapp.ui.theme.appearanceFade
import kotlinx.coroutines.launch
import java.time.LocalDate

internal fun mockRingInventory(count: Int): List<StockItem> = (0 until count).map { i ->
    val category = listOf("食品", "日用品", "其他")[i % 3]
    val names = when (category) {
        "食品" -> listOf("纯牛奶", "全麦面包", "苹果", "酸奶", "鸡蛋", "番茄", "香蕉", "燕麦")
        "日用品" -> listOf("洗衣液", "纸巾", "洗发水", "牙膏", "洗洁精", "面霜", "垃圾袋")
        else -> listOf("电池", "胶带", "笔记本", "文件袋", "灯泡", "收纳盒")
    }
    val quantity = (i % 5 + 1).toDouble()
    val name = names[(i / 3) % names.size]
    val unit = when {
        name.contains("纸") -> "包"
        name.contains("面包") || name.contains("燕麦") -> "袋"
        name.contains("香蕉") -> "根"
        name.contains("蛋") || name.contains("苹果") || name.contains("番茄") -> "个"
        name.contains("电池") -> "节"
        category == "食品" -> "盒"
        category == "日用品" -> "瓶"
        else -> "个"
    }
    StockItem(id = "ring-mock-$i", name = "$name ${String.format(java.util.Locale.ROOT, "%03d", i + 1)}", quantity = quantity,
        unit = unit, category = category,
        location = listOf("冰箱", "阳台", "储物柜")[i % 3], minimum = if (i % 4 == 2) quantity + 2 else 0.0,
        expiry = when (i % 4) { 0 -> LocalDate.now().minusDays(4).toString(); 1 -> LocalDate.now().plusDays(2).toString(); else -> "" },
        history = listOf("模拟录入 ${quantity.display()} $unit"))
}

/** This test host owns only in-memory fixtures and never receives a real InventoryStore. */
@OptIn(ExperimentalMaterial3Api::class)
@Suppress("DEPRECATION")
@Composable
internal fun RingInventoryTestPage(initialLight: Boolean, onClose: () -> Unit, onNavigate: (Int) -> Unit) {
    var light by rememberSaveable { mutableStateOf(initialLight) }
    var scenario by rememberSaveable { mutableIntStateOf(3) }
    var items by remember { mutableStateOf(mockRingInventory(scenario)) }
    var nextId by remember { mutableIntStateOf(1000) }
    var selected by remember { mutableStateOf<StockItem?>(null) }
    var detailId by rememberSaveable { mutableStateOf<String?>(null) }
    var purchaseIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    var closingDetail by remember { mutableStateOf(false) }
    val detail = items.firstOrNull { it.id == detailId }
    val activity = LocalActivity.current
    val originalBars = remember(activity) { activity?.window?.let { it.statusBarColor to it.navigationBarColor } }
    SideEffect {
        activity?.window?.let { window ->
            window.statusBarColor = if (light) android.graphics.Color.rgb(250, 247, 232) else android.graphics.Color.rgb(24, 25, 27)
            window.navigationBarColor = window.statusBarColor
            WindowCompat.getInsetsController(window, window.decorView).apply {
                isAppearanceLightStatusBars = light; isAppearanceLightNavigationBars = light
            }
        }
    }
    DisposableEffect(activity) { onDispose {
        activity?.window?.let { window ->
            originalBars?.let { (status, navigation) -> window.statusBarColor = status; window.navigationBarColor = navigation }
            WindowCompat.getInsetsController(window, window.decorView).apply {
                isAppearanceLightStatusBars = initialLight; isAppearanceLightNavigationBars = initialLight
            }
        }
    } }
    fun closeDetail(afterClose: () -> Unit = {}) {
        if (closingDetail) return
        closingDetail = true
        scope.launch {
            try {
                sheetState.hide()
                detailId = null
                afterClose()
            } finally {
                closingDetail = false
            }
        }
    }
    BackHandler { if (detailId != null) closeDetail() else onClose() }

    fun add() {
        val mock = mockRingInventory(nextId % 12 + 1).last().copy(id = "ring-added-${nextId}", name = "新增小物 $nextId", expiry = "", minimum = 0.0)
        nextId++
        items = items + mock
    }
    fun delete(id: String) {
        val remove = { items = items.filterNot { it.id == id }; purchaseIds = purchaseIds - id }
        if (detailId == id) closeDetail(remove) else remove()
    }
    fun quantity(id: String, delta: Double) {
        items = items.map { if (it.id == id) it.copy(quantity = (it.quantity + delta).coerceAtLeast(0.0), history = listOf("模拟数量调整 ${delta.display()}") + it.history) else it }
    }

    TeamAppTheme(darkTheme = !light) {
        val headerColor by animateColorAsState(if (light) Color(0xFFB2C57D) else Color(0xFF202124),
            tween(AppMotion.Duration, easing = AppMotion.easing), label = "ring-header-theme")
        Scaffold(bottomBar = {
            if (light) DesignNavigation(1, onNavigate) else DarkNavigation(1, onNavigate)
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).testTag("ring-test-page")) {
                Row(Modifier.fillMaxWidth().background(headerColor)
                    .padding(horizontal = 18.dp, vertical = 13.dp).testTag("ring-showcase-header"), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("我的库存", fontSize = 25.sp, lineHeight = 31.sp, fontWeight = FontWeight.Bold)
                        Text("${items.size} 种物品 · ${items.count { it.status(3).attention }} 项需关注", fontSize = 10.sp, lineHeight = 15.sp, modifier = Modifier.padding(top = 3.dp))
                    }
                    CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides 0.dp) {
                        IconButton(onClick = { add() }, modifier = Modifier.size(30.dp).background(MaterialTheme.colorScheme.primary, CircleShape)) {
                            DesignGlyph("plus", Modifier.size(20.dp), MaterialTheme.colorScheme.onPrimary)
                        }
                    }
                    TextButton(onClick = { light = !light }, modifier = Modifier.padding(start = 7.dp).size(34.dp).testTag("ring-test-theme"), contentPadding = PaddingValues(0.dp)) {
                        Text(if (light) "深" else "浅", fontSize = 12.sp)
                    }
                    TextButton(onClick = onClose, contentPadding = PaddingValues(0.dp), modifier = Modifier.width(30.dp)) { Text("退出", fontSize = 10.sp) }
                }
                Spacer(Modifier.height(10.dp))
                StockRingBrowser(items, 3, onOpenItem = { detailId = it.id }, onAdd = { add() }, onSelectedItem = { selected = it })
                HorizontalDivider(Modifier.padding(top = 10.dp), color = MaterialTheme.colorScheme.outlineVariant)
                Column(Modifier.padding(horizontal = 18.dp, vertical = 10.dp)) {
                    Text("圆环测试设置", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text("${items.size} 条模拟记录 · 不写入真实库存", fontSize = 10.sp, lineHeight = 15.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("ring-mock-total").padding(top = 3.dp))
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    listOf(0, 1, 3, 12, 30, 100).forEach { count ->
                        val scenarioColor by animateColorAsState(if (scenario == count) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.background,
                            tween(AppMotion.Quick, easing = AppMotion.easing), label = "ring-scenario-selection")
                        OutlinedButton(onClick = { scenario = count; items = mockRingInventory(count); purchaseIds = emptySet(); detailId = null },
                            modifier = Modifier.weight(1f).height(28.dp).testTag("ring-scenario-$count"), contentPadding = PaddingValues(0.dp),
                            colors = ButtonDefaults.outlinedButtonColors(containerColor = scenarioColor),
                            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) { Text(count.toString(), fontSize = 11.sp) }
                    }
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 5.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(onClick = { add() }, modifier = Modifier.testTag("ring-mock-add"), contentPadding = PaddingValues(horizontal = 10.dp)) { Text("模拟新增", fontSize = 11.sp) }
                    OutlinedButton(onClick = { selected?.let { delete(it.id) } }, enabled = selected != null, modifier = Modifier.testTag("ring-mock-delete"), contentPadding = PaddingValues(horizontal = 10.dp)) { Text("删除选中", fontSize = 11.sp) }
                    OutlinedButton(onClick = { selected?.let { quantity(it.id, 1.0) } }, enabled = selected != null, modifier = Modifier.testTag("ring-mock-update"), contentPadding = PaddingValues(horizontal = 10.dp)) { Text("更新数量", fontSize = 11.sp) }
                }
            }
        }
        if (detail != null) ModalBottomSheet(onDismissRequest = { detailId = null }, sheetState = sheetState, modifier = Modifier.appearanceFade()) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .animateContentSize(tween(AppMotion.Duration, easing = AppMotion.easing)).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("模拟物品详情", fontSize = 20.sp, modifier = Modifier.weight(1f))
                    TextButton(onClick = { closeDetail() }, enabled = !closingDetail) { Text("关闭详情") }
                }
                Text(detail.name, fontSize = 22.sp, modifier = Modifier.testTag("ring-detail-name"))
                AppMotionContent("${detail.quantity.display()} ${detail.unit} · ${detail.category} · ${detail.location}", label = "ring-detail-quantity") { Text(it) }
                Text("${detail.status(3).label}\n最低库存 ${detail.minimum.display()} ${detail.unit}\n有效期 ${detail.expiry.ifBlank { "未设置" }}")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { quantity(detail.id, 1.0) }, enabled = !closingDetail) { Text("模拟入库 +1") }
                    OutlinedButton(onClick = { quantity(detail.id, -1.0) }, enabled = detail.quantity > 0 && !closingDetail) { Text("模拟消耗 −1") }
                }
                Button(onClick = { purchaseIds = purchaseIds + detail.id }, enabled = !closingDetail) {
                    AppMotionContent(detail.id in purchaseIds, label = "ring-detail-purchase") { added -> Text(if (added) "已加入模拟清单" else "加入模拟采购清单") }
                }
                TextButton(onClick = { delete(detail.id) }, enabled = !closingDetail) { Text("删除该模拟物品", color = MaterialTheme.colorScheme.error) }
                detail.history.take(5).forEach { Text(it, fontSize = 12.sp) }
                Text("这里的所有操作只影响本次测试数据。", fontSize = 11.sp)
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}
