package com.example.teamapp.data

import java.time.LocalDate

/** Observed package text, never a fabricated vision response or an inventory write. */
internal data class PhotoTextLine(val text: String, val height: Int = 0)

internal data class PhotoDraft(
    val name: String = "",
    val specification: String = "",
    val unit: String = "",
    val category: String = "其他",
    val expiry: String = "",
    val dateCandidates: List<String> = emptyList()
)

internal object PhotoDraftParser {
    private val datePattern = Regex("(?<![0-9])((?:19|20)[0-9]{2})[年./-]\\s*([0-9]{1,2})[月./-]\\s*([0-9]{1,2})日?(?![0-9])")
    private val compactDate = Regex("(?<![0-9])((?:19|20)[0-9]{2})([01][0-9])([0-3][0-9])(?![0-9])")
    private val expiryLabel = Regex("有效期(?:至)?|有效日期至|保质期至|到期日期|到期日|失效日期|失效期|限用日期|使用期限至|EXP(?:IRY)?(?:\\s*DATE)?(?![A-Za-z])", RegexOption.IGNORE_CASE)
    private val productionLabel = Regex("生产日期|制造日期|包装日期|灌装日期|MFG|MFD", RegexOption.IGNORE_CASE)
    private val specification = Regex("(?<![0-9])([0-9]+(?:\\.[0-9]+)?)\\s*(m[lL]|ML|[lL]|kg|KG|g|G|毫升|千克|公斤|升|克)(?![A-Za-z])")
    private val products = listOf("全脂纯牛奶", "脱脂纯牛奶", "低脂纯牛奶", "纯牛奶", "鲜牛奶", "酸奶", "牛奶", "全麦面包", "吐司面包", "面包", "燕麦片", "燕麦", "鸡蛋", "洗衣液", "洗洁精", "洗手液", "沐浴露", "洗发水", "抽纸", "纸巾", "牙膏", "矿泉水", "饮用水", "酱油", "食用油", "饼干", "大米")
    private val household = setOf("洗衣液", "洗洁精", "洗手液", "沐浴露", "洗发水", "抽纸", "纸巾", "牙膏")

    fun parse(lines: List<PhotoTextLine>): PhotoDraft {
        val clean = lines.map { it.copy(text = it.text.trim()) }.filter { it.text.isNotBlank() }
        val fullText = clean.joinToString("\n") { it.text }
        val normalized = fullText.replace(Regex("\\s+"), "")
        val known = products.firstOrNull { normalized.contains(it) }
        // For an unfamiliar package, offer a prominent observed line, not a guessed product.
        val name = known ?: clean.sortedByDescending { it.height }.firstOrNull {
            val value = it.text
            value.length in 2..40 && value.any { ch -> ch in '\u4e00'..'\u9fff' } &&
                !Regex("日期|保质期|有效期|生产|配料|营养|净含量|执行标准|贮存|储存|许可证|电话|地址|公司|有限公司|蛋白质|脂肪|碳水|能量|含量|生牛乳|百分|100%|[0-9]{3,}").containsMatchIn(value)
        }?.text.orEmpty()
        val specs = specification.findAll(fullText).map { match ->
            val unit = InventoryContract.unit(match.groupValues[2]) ?: when (match.groupValues[2].lowercase()) {
                "ml" -> "ml"; "kg" -> "kg"; "g" -> "g"; "l" -> "L"; else -> match.groupValues[2]
            }
            match.groupValues[1] + unit
        }.distinct().toList()
        // A package's 250ml is its specification, NOT an inventory amount or container unit.
        val container = Regex("(?:单位|计量单位)\\s*[:：]?\\s*(盒|瓶|包|袋|个|卷|片)").find(fullText)?.groupValues?.get(1).orEmpty()
        val explicit = clean.mapIndexedNotNull { index, line ->
            if (!expiryLabel.containsMatchIn(line.text) || productionLabel.containsMatchIn(line.text)) null
            else dates(line.text).singleOrNull() ?: clean.getOrNull(index + 1)?.text?.takeIf {
                !productionLabel.containsMatchIn(it) && !expiryLabel.containsMatchIn(it)
            }?.let(::dates)?.singleOrNull()
        }.distinct()
        return PhotoDraft(
            name = name,
            specification = specs.singleOrNull().orEmpty(),
            unit = container,
            category = when { known in household -> "日用品"; known != null -> "食品"; else -> "其他" },
            expiry = explicit.singleOrNull().orEmpty(),
            dateCandidates = dates(fullText)
        )
    }

    fun dates(text: String): List<String> = (datePattern.findAll(text) + compactDate.findAll(text)).mapNotNull {
        runCatching { LocalDate.of(it.groupValues[1].toInt(), it.groupValues[2].toInt(), it.groupValues[3].toInt()).toString() }.getOrNull()
    }.distinct().toList()
}
