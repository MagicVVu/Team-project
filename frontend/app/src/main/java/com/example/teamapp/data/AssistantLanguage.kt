package com.example.teamapp.data

/** Presentation only. Never use this lookup for names, locations or history. */
object AssistantLanguage {
    const val PROTOCOL = "assistant-language-1"
    fun dateToken(value: String): String = when (value.lowercase(java.util.Locale.ROOT)) {
        "today" -> "今天"
        "yesterday" -> "昨天"
        else -> value
    }
    val units = mapOf("瓶" to "bottle(s)", "盒" to "box(es)", "包" to "pack(s)", "袋" to "bag(s)",
        "个" to "item(s)", "件" to "item(s)", "份" to "portion(s)", "卷" to "roll(s)",
        "片" to "sheet(s)", "台" to "unit(s)", "吨" to "tonne(s)")
    fun supported(capabilities: org.json.JSONObject, locale: String): Boolean = locale == "zh-CN" ||
        (capabilities.optString("assistant_language_protocol") == PROTOCOL &&
            capabilities.optJSONArray("assistant_languages")?.let { values -> (0 until values.length()).any { values.optString(it) == locale } } == true)
    fun unit(value: String, english: Boolean, quantity: String? = null): String {
        if (!english) return value
        val label = units[value] ?: return value
        return if (quantity?.toBigDecimalOrNull()?.compareTo(java.math.BigDecimal.ONE) == 0)
            label.replace("(s)", "").replace("(es)", "")
        else label.replace("(s)", "s").replace("(es)", "es")
    }
    fun system(value: String, english: Boolean): String {
        if (!english || value.isBlank()) return value
        return messages[value] ?: if (value.any { it in '\u4e00'..'\u9fff' })
            "Review the current task or recover the original request before continuing." else value
    }
    private val messages = mapOf(
        "当前版本暂不支持自动执行此动作" to "Automatic execution of this action is unavailable.",
        "字段不允许编辑" to "This field cannot be edited in the current draft.",
        "数量必须为正数，库存最多六位、采购最多三位小数" to "Use a positive quantity, with at most six decimal places for inventory and three for shopping.",
        "位置必填且最多 100 字，不会自动截断" to "A location is required and may contain at most 100 characters; it will not be truncated.",
        "物品名称必填且最多 80 字，不会自动截断" to "An item name is required and may contain at most 80 characters; it will not be truncated.",
        "请核对 AI 支持的计量单位，不会猜测容器容量" to "Use a supported unit. Container capacities will not be guessed.",
        "有效期不能早于购入日期" to "The expiry date cannot be earlier than the purchase date.",
        "正在恢复已保存的任务" to "Recovering saved tasks…",
        "正在理解并核对库存" to "Understanding your message and checking inventory…",
        "正在核对库存" to "Checking inventory…",
        "处理中" to "Processing…",
        "暂时无法恢复，请联网核实；不会自动重交操作" to "Recovery is temporarily unavailable. Connect and check the original request; operations will not be resubmitted automatically.",
        "请先查询上一条消息的原请求结果" to "Recover the previous message before sending another request.",
        "家庭已切换，请在当前家庭重新核对原文" to "The household changed. Review the original input in the current household.",
        "消息须为 1–1000 字" to "Enter 1–1000 characters.",
        "消息最多 1000 字，不会自动截断" to "Messages are limited to 1000 characters and will not be truncated.",
        "任务缓存无法读取，原始记录已保留。请核对服务器回执，勿重复执行。" to "Saved tasks could not be read. The original records are retained; check server receipts before retrying.",
        "无法持久保存操作请求，已停止发送。请检查设备空间" to "The request could not be saved. Sending stopped; check device storage.",
        "无法连接服务器。请检查网络、服务器地址、证书及服务器访问策略；如刚提交操作，请先刷新核对结果。" to "Cannot connect. Check the network, server address, certificate and access policy. If you submitted an operation, recover its result first.",
        "当前服务尚未启用连续引用，请写明物品名称或使用候选按钮" to "This server does not support continuous references. Specify the registered name or use a candidate button.",
        "请核对任务后重试" to "Review the current task before retrying."
    )
}
