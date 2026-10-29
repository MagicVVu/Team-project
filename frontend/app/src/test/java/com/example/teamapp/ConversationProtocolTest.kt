package com.example.teamapp

import com.example.teamapp.data.ConversationProtocol
import org.junit.Assert.assertEquals
import org.junit.Test

class ConversationProtocolTest {
    @Test fun conversationAndRecoveryHaveThirtySecondReadBudget() {
        listOf("/api/v1/agent/conversation?household_id=one&limit=20", "/api/v1/agent/conversation/reset",
            "/api/v1/agent/conversation-turns", "/api/v1/agent/conversation-turns/original-id?household_id=one",
            "/api/v1/agent/conversation-messages").forEach { assertEquals(30_000, ConversationProtocol.readTimeoutMillis(it)) }
    }
    @Test fun ordinaryBusinessRequestsKeepExistingReadBudget() {
        listOf("/api/v1/agent/tasks/one", "/api/v1/drafts/one/commit", "/api/v1/auth/login",
            "/api/v1/agent/execution-capabilities").forEach { assertEquals(20_000, ConversationProtocol.readTimeoutMillis(it)) }
    }
}
