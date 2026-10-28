package com.example.teamapp

import com.example.teamapp.data.PhotoDraftParser
import com.example.teamapp.data.PhotoTextLine
import org.junit.Assert.*
import org.junit.Test

class PhotoDraftParserTest {
    private fun parse(vararg lines: String) = PhotoDraftParser.parse(lines.map { PhotoTextLine(it) })

    @Test fun packageSizeIsNotStockQuantityOrContainerUnit() {
        val draft = parse("纯 牛 奶", "净含量 250mL", "生牛乳100%")
        assertEquals("纯牛奶", draft.name)
        assertEquals("250ml", draft.specification)
        assertEquals("", draft.unit)
        assertEquals("食品", draft.category)
    }
    @Test fun productionDateAndShelfLifeDoNotFabricateExpiry() {
        val draft = parse("纯牛奶", "生产日期 2026-10-25", "保质期180天")
        assertEquals("", draft.expiry)
        assertEquals(listOf("2026-10-25"), draft.dateCandidates)
    }
    @Test fun explicitlyLabelledExpiryAndCalendarValidation() {
        assertEquals("2026-10-28", parse("有效期至 2026年10月28日").expiry)
        assertEquals("2026-10-28", parse("EXP: 2026/10/28").expiry)
        assertEquals("2026-10-28", parse("有效期", "20261028").expiry)
        assertEquals("", parse("有效期至2026-02-30").expiry)
        assertEquals("", parse("2026-10-28").expiry)
    }
    @Test fun conflictingDatesAndProductionLabelStayUnresolved() {
        assertEquals("", parse("有效期至2026-10-28", "有效期至2026-10-30").expiry)
        assertEquals("", parse("有效期", "生产日期2026-10-25").expiry)
        assertEquals("", parse("生产日期2026-10-25 有效期至2026-11-25").expiry)
    }
    @Test fun unknownOrEmptyPhotoDoesNotInventAProduct() {
        assertEquals("", parse().name)
        assertEquals("", parse("营养成分表", "生产许可证123456", "净含量250ml").name)
        assertEquals("其他", parse().category)
    }
    @Test fun explicitContainerAndHouseholdClassification() {
        val draft = parse("洗手液", "净含量500毫升", "计量单位：瓶")
        assertEquals("日用品", draft.category)
        assertEquals("瓶", draft.unit)
        assertEquals("500ml", draft.specification)
    }
}
