package com.example.teamapp.data

import org.json.JSONObject
import com.example.teamapp.BuildConfig

/** Public user APIs only; never connects directly to the AI or database. */
open class AgentClient(address: String, token: String) {
    private val api = CloudApi(address, token)
    suspend fun capabilities(): JSONObject {
        val health = api.request("GET", "/api/v1/health")
        TargetPolicy.health(BuildConfig.DEBUG, health.optString("service"), health.optString("version"), health.getBoolean("isolated_test"))
        return api.request("GET", "/api/v1/agent/execution-capabilities").also {
            TargetPolicy.capabilities(it.optString("protocol_version"), it.optString("owner"))
        }
    }
    open suspend fun message(body: JSONObject) = api.request("POST", "/api/v1/agent/messages", body)
    suspend fun task(id: String) = api.request("GET", "/api/v1/agent/tasks/${uuid(id)}")
    suspend fun clarify(id: String, body: JSONObject) = api.request("POST", "/api/v1/agent/clarifications/${uuid(id)}", body)
    open suspend fun draft(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}")
    suspend fun execution(id: String) = api.request("GET", "/api/v1/drafts/${uuid(id)}/execution")
    open suspend fun commit(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/commit", body)
    suspend fun cancel(id: String, body: JSONObject) = api.request("POST", "/api/v1/drafts/${uuid(id)}/cancel", body)
    suspend fun operation(id: String) = api.request("GET", "/api/v1/operations/${uuid(id)}")
    private fun uuid(value: String) = java.util.UUID.fromString(value).toString()
}
