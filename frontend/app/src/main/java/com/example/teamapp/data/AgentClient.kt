package com.example.teamapp.data

import org.json.JSONObject

/** Public user APIs only; never connects directly to the AI or database. */
open class AgentClient(address: String, token: String) {
    private val api = CloudApi(address, token)
    suspend fun capabilities(): JSONObject {
        val health = api.request("GET", "/api/v1/health")
        check(health.optString("version") == "0.9.0" && health.optBoolean("isolated_test")) {
            "当前地址不是已验证的隔离后端 0.9.0，已停止 AI 联调"
        }
        return api.request("GET", "/api/v1/agent/execution-capabilities").also {
            check(it.optString("protocol_version") == "draft-execution-1" && it.optString("owner") == "business_backend") { "后端执行协议不匹配" }
        }
    }
    suspend fun message(body: JSONObject) = api.request("POST", "/api/v1/agent/messages", body)
    suspend fun task(id: String) = api.request("GET", "/api/v1/agent/tasks/${uuid(id)}")
    suspend fun clarify(id: String, body: JSONObject) = api.request("POST", "/api/v1/agent/clarifications/${uuid(id)}", body)
    suspend fun draft(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}")
    suspend fun execution(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}/execution")
    open suspend fun commit(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/commit", body)
    suspend fun cancel(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/cancel", body)
    suspend fun operation(id: String) = api.request("GET", "/api/v1/operations/${uuid(id)}")
    private fun uuid(value: String) = java.util.UUID.fromString(value).toString()
}
