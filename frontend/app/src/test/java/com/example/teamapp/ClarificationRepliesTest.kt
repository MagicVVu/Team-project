package com.example.teamapp

import com.example.teamapp.data.ClarificationReplies
import org.junit.Assert.*
import org.junit.Test

class ClarificationRepliesTest {
    @Test fun ordinalsBindOnlyToSuppliedCandidates() {
        for (text in listOf("选择第二批", "第二个", "选择第二个吧")) assertEquals(mapOf("batch_id" to "b"), ClarificationReplies.resolve(text, setOf("batch_id"), listOf("a", "b")))
        assertNull(ClarificationReplies.resolve("第二个", setOf("batch_id"), listOf("a")))
        assertNull(ClarificationReplies.resolve("第二个", setOf("batch_id"), listOf("a", "a")))
        assertNull(ClarificationReplies.resolve("这一批", setOf("batch_id"), listOf("a")))
        assertEquals(mapOf("batch_id" to "a"), ClarificationReplies.resolve("这一批", setOf("batch_id"), listOf("a"), "a"))
    }
    @Test fun supplementsRequireUnambiguousAllowedFields() {
        for (text in listOf("两盒", "2盒", "2 盒")) assertEquals(mapOf("quantity" to "2", "unit" to "盒"), ClarificationReplies.resolve(text, setOf("quantity", "unit"), emptyList()))
        assertNull(ClarificationReplies.resolve("2盒", setOf("quantity"), emptyList()))
        for (text in listOf("今天", "昨天")) assertEquals(mapOf("opened_at" to text), ClarificationReplies.resolve(text, setOf("opened_at"), emptyList()))
        assertNull(ClarificationReplies.resolve("昨天", setOf("opened_at", "purchased_at"), emptyList()))
        assertNull(ClarificationReplies.resolve("2026-02-30", setOf("opened_at"), emptyList()))
        assertNull(ClarificationReplies.resolve("0盒", setOf("quantity", "unit"), emptyList()))
        assertNull(ClarificationReplies.resolve("删除全部", setOf("batch_id"), listOf("a")))
    }
}
