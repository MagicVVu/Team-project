package com.example.teamapp.data

import org.json.JSONObject

/** Public user APIs only; never connects directly to the AI or database. */
open class AgentClient(address: String, token: String) {
    private val api = CloudApi(address, token)
    open suspend fun capabilities(): JSONObject {
        return api.verifiedCapabilities()
    }
    open suspend fun conversation(body: JSONObject) = api.request("POST", "/api/v1/agent/conversation-messages", body)
    open suspend fun currentConversation(householdId: String, cursor: String? = null): JSONObject {
        val suffix = cursor?.let { "&cursor=${uuid(it)}" }.orEmpty()
        return api.request("GET", "/api/v1/agent/conversation?household_id=${uuid(householdId)}&limit=20$suffix")
    }
    open suspend fun resetConversation(body: JSONObject) = api.request("POST", "/api/v1/agent/conversation/reset", body)
    open suspend fun conversationTurn(body: JSONObject) = api.request("POST", "/api/v1/agent/conversation-turns", body)
    open suspend fun recoverConversation(requestId: String, householdId: String): JSONObject {
        require(requestId.matches(Regex("[A-Za-z0-9._:-]{1,100}")))
        return api.request("GET", "/api/v1/agent/conversation-turns/$requestId?household_id=${uuid(householdId)}")
    }
    open suspend fun referenceMessage(body: JSONObject) = api.request("POST", "/api/v1/agent/reference-messages", body)
    open suspend fun control(id: String, body: JSONObject) = api.request("POST", "/api/v1/agent/tasks/${uuid(id)}/chat-control", body)
    open suspend fun preview(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/execution-preview", body)
    open suspend fun message(body: JSONObject) = api.request("POST", "/api/v1/agent/messages", body)
    open suspend fun task(id: String) = api.request("GET", "/api/v1/agent/tasks/${uuid(id)}")
    suspend fun clarify(id: String, body: JSONObject) = api.request("POST", "/api/v1/agent/clarifications/${uuid(id)}", body)
    open suspend fun draft(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}")
    open suspend fun execution(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}/execution")
    open suspend fun planningRevalidation(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/planning-revalidation", body)
    open suspend fun commit(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/commit", body)
    open suspend fun cancel(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/cancel", body)
    open suspend fun operation(id: String) = api.request("GET", "/api/v1/operations/${uuid(id)}")
    private fun uuid(value: String) = java.util.UUID.fromString(value).toString()
}
