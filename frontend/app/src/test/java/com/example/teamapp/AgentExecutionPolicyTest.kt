package com.example.teamapp

import com.example.teamapp.data.AgentExecutionPolicy
import org.junit.Assert.*
import org.junit.Test

class AgentExecutionPolicyTest {
    private fun validate(action: String, values: Map<String, String>) = AgentExecutionPolicy.validate(action, values, AgentExecutionPolicy.editable[action].orEmpty())
    @Test fun exactPrecisionIsPreserved() {
        validate("CONSUME", mapOf("quantity" to "0.000001", "unit" to "包"))
        assertTrue(runCatching { validate("CONSUME", mapOf("quantity" to "0.0000001")) }.isFailure)
        validate("PLAN_ADD", mapOf("quantity" to "1.001"))
        assertTrue(runCatching { validate("PLAN_ADD", mapOf("quantity" to "1.0001")) }.isFailure)
    }
    @Test fun noClampingOrTruncation() {
        for (n in listOf("0", "-1", "NaN", "1000000001")) assertTrue(runCatching { validate("ADD", mapOf("quantity" to n)) }.isFailure)
        validate("MOVE", mapOf("to_location" to "库".repeat(100)))
        assertTrue(runCatching { validate("MOVE", mapOf("to_location" to "库".repeat(101))) }.isFailure)
        assertTrue(runCatching { validate("ADD", mapOf("location" to " ")) }.isFailure)
    }
    @Test fun protectedFieldsAndUnsupportedActionsNeverPass() {
        for (key in listOf("batch_id", "expected_version", "action", "household_id", "planning_basis", "quantity"))
            assertTrue(runCatching { validate("MOVE", mapOf(key to "1")) }.isFailure)
        for (action in listOf("SUGGEST_PURCHASE", "UNSUPPORTED")) assertTrue(runCatching { validate(action, emptyMap()) }.isFailure)
        assertTrue(runCatching { AgentExecutionPolicy.validate("ADD", mapOf("location" to "冰箱"), emptyList()) }.isFailure)
    }
    @Test fun datesMustBeValidAndOrdered() {
        validate("ADD", mapOf("purchased_at" to "2026-10-17", "label_expiry" to "2027-01-01"))
        assertTrue(runCatching { validate("ADD", mapOf("purchased_at" to "2026-10-17", "label_expiry" to "2026-01-01")) }.isFailure)
        assertTrue(runCatching { validate("ADD", mapOf("label_expiry" to "2026-02-30")) }.isFailure)
    }
}
