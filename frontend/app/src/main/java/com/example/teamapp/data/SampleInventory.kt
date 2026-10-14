package com.example.teamapp.data

import java.time.LocalDate

/** Explicit preview inventory for the debug app, with stable IDs for repeat launches. */
internal fun sampleInventory(today: LocalDate = LocalDate.now()): List<StockItem> {
    fun item(key: String, name: String, quantity: Double, unit: String, category: String,
             location: String, minimum: Double, days: Long? = null) = StockItem(
        id = "sample-$key", name = name, quantity = quantity, unit = unit, category = category,
        location = location, minimum = minimum, expiry = days?.let { today.plusDays(it).toString() }.orEmpty(),
        history = listOf("页面展示示例 · ${quantity.display()} $unit")
    )
    return listOf(
        item("milk", "纯牛奶", 2.0, "盒", "食品", "冰箱", 3.0, 2),
        item("bread", "全麦面包", 1.0, "袋", "食品", "厨房", 2.0, -1),
        item("apple", "红苹果", 6.0, "个", "食品", "冰箱", 3.0, 10),
        item("banana", "香蕉", 3.0, "根", "食品", "厨房", 2.0, 1),
        item("egg", "鲜鸡蛋", 10.0, "个", "食品", "冰箱", 6.0, 14),
        item("tissue", "抽纸", 2.0, "包", "日用品", "储物柜", 4.0),
        item("laundry", "洗衣液", 1.0, "瓶", "日用品", "阳台", 2.0),
        item("shampoo", "洗发水", 2.0, "瓶", "日用品", "储物柜", 1.0, 180),
        item("toothpaste", "牙膏", 3.0, "支", "日用品", "储物柜", 2.0, 365),
        item("dish-soap", "洗洁精", 1.0, "瓶", "日用品", "厨房", 1.0, 120),
        item("battery", "五号电池", 2.0, "节", "其他", "储物柜", 4.0),
        item("tape", "透明胶带", 2.0, "卷", "其他", "储物柜", 1.0),
        item("notebook", "笔记本", 4.0, "本", "其他", "储物柜", 2.0),
        item("bulb", "LED 灯泡", 1.0, "个", "其他", "储物柜", 2.0),
        item("storage-box", "收纳盒", 3.0, "个", "其他", "储物柜", 1.0)
    )
}
