package com.example.teamapp

import com.example.teamapp.data.AssistantLanguage
import com.example.teamapp.data.AssistantUnitAliases
import com.example.teamapp.data.AgentExecutionPolicy
import org.junit.Assert.*
import org.junit.Test

class AssistantLanguageTest {
    @org.junit.Test fun englishRelativeDateUsesExistingTrustedBackendContract() {
        val edits = mapOf("opened_at" to "yesterday")
        AgentExecutionPolicy.validate("OPEN", edits, listOf("opened_at"))
        org.junit.Assert.assertEquals("昨天", AgentExecutionPolicy.wireEdits(edits)["opened_at"])
        org.junit.Assert.assertEquals("今天", AssistantLanguage.dateToken("Today"))
    }
    @Test fun displayUnitsDoNotAlterWireUnits() {
        assertEquals("bottles", AssistantLanguage.unit("瓶", true))
        assertEquals("bottle", AssistantLanguage.unit("瓶", true, "1"))
        assertEquals("瓶", AssistantLanguage.unit("瓶", false))
        assertEquals("瓶", AgentExecutionPolicy.wireEdits(mapOf("unit" to "bottles"))["unit"])
        assertEquals("kg", AssistantUnitAliases.canonical("kilograms"))
    }
    @Test fun localizedNoticesKeepTransportDetailsPrivate() {
        assertEquals("Checking inventory…", AssistantLanguage.system("正在核对库存", true))
        val fallback = AssistantLanguage.system("未知内部错误", true)
        assertFalse(fallback.contains("未知内部错误"))
        assertEquals("正在核对库存", AssistantLanguage.system("正在核对库存", false))
    }
}
