package com.example.teamapp

import com.example.teamapp.data.TargetCheckCache
import com.example.teamapp.data.ChatMessages
import com.example.teamapp.data.AgentExecutionPolicy
import org.junit.Assert.*
import org.junit.Test

class ChatOptimizationTest {
    @Test fun optionalDatesCanBeClearedWithoutInventingOtherFields() {
        val values = mapOf("purchased_at" to "", "label_expiry" to " ", "opened_at" to "", "quantity" to "3")
        val wire = AgentExecutionPolicy.wireEdits(values)
        assertNull(wire["purchased_at"]); assertNull(wire["label_expiry"])
        assertEquals("", wire["opened_at"]); assertEquals("3", wire["quantity"])
        assertEquals("", values["purchased_at"])
    }
    @Test fun discoveryCacheIsBoundedAndExpiresAcrossIdentities() {
        val cache = TargetCheckCache(ttlMillis = 15, capacity = 2)
        cache.put("a", 100, "first")
        assertEquals("first", cache.get("a", 114))
        assertNull(cache.get("a", 115)); assertNull(cache.get("a", 99)); assertNull(cache.get("b", 100))
        cache.put("b", 100, "second"); cache.put("c", 100, "third")
        assertNull(cache.get("a", 101))
        cache.invalidate("b"); assertNull(cache.get("b", 101))
    }
    @Test fun unknownResultsNeverClaimCompletion() {
        val text = ChatMessages.reason("AI_OUTCOME_UNKNOWN")
        assertTrue(text.contains("待核实")); assertTrue(text.contains("不会自动")); assertFalse(text.contains("已执行"))
        assertTrue(ChatMessages.reason("REFERENCE_EXPIRED").contains("重新"))
        assertTrue(ChatMessages.reason("PLANNING_CONTEXT_UNAVAILABLE").contains("无法"))
    }
    @Test fun newlySupportedEditsStillProtectTargets() {
        AgentExecutionPolicy.validate("OPEN", mapOf("opened_at" to "昨天"), listOf("opened_at"))
        AgentExecutionPolicy.validate("DISCARD", emptyMap(), emptyList())
        assertTrue(runCatching { AgentExecutionPolicy.validate("DISCARD", mapOf("quantity" to "1"), emptyList()) }.isFailure)
        assertTrue(runCatching { AgentExecutionPolicy.validate("OPEN", mapOf("batch_id" to "a"), listOf("opened_at")) }.isFailure)
    }
}
