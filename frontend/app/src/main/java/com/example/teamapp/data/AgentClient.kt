package com.example.teamapp.data

import com.example.teamapp.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.util.UUID

data class AgentReply(val status: String, val reply: String, val traceId: String, val revision: Int, val engine: String, val command: AgentCommand?, val candidates: List<String>, val errorCode: String)

fun AgentCommand.toJson() = JSONObject().apply {
    put("action", action); put("name", name); put("quantity", quantity); put("unit", unit)
    put("batch_id", batchId ?: JSONObject.NULL); put("expected_version", expectedVersion ?: JSONObject.NULL)
    put("location", location.ifBlank { null } ?: JSONObject.NULL)
    put("purchased_at", purchasedAt.ifBlank { null } ?: JSONObject.NULL)
    put("label_expiry", labelExpiry.ifBlank { null } ?: JSONObject.NULL)
}

private fun JSONObject.command() = AgentCommand(getString("action"), getString("name"), getString("quantity"), getString("unit"),
    optString("batch_id").takeUnless { it.isBlank() || it == "null" }, if (isNull("expected_version")) null else getInt("expected_version"),
    optString("location").takeUnless { it == "null" }.orEmpty(), optString("purchased_at").takeUnless { it == "null" }.orEmpty(), optString("label_expiry").takeUnless { it == "null" }.orEmpty())

class AgentClient(private val baseUrl: String, private val token: String) {
    companion object {
        fun validateAddress(value: String) {
            val uri = URI(value.trim())
            require(uri.host != null && uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty() in setOf("", "/")) { "请输入服务根地址，例如 http://10.0.2.2:8080" }
            require(uri.scheme == "https" || (BuildConfig.DEBUG && uri.scheme == "http")) { "正式版本需要 HTTPS；本地 HTTP 仅限调试版本" }
        }
    }
    private fun snapshot(items: List<StockItem>, revision: Int) = JSONObject().apply {
        put("inventory_revision", revision)
        put("items", JSONArray().apply { items.forEach { item -> put(JSONObject().apply {
            put("id", item.id); put("name", item.name); put("quantity", item.quantity.toString()); put("unit", item.unit)
            put("location", item.location.ifBlank { null } ?: JSONObject.NULL); put("expiry", item.expiry.ifBlank { null } ?: JSONObject.NULL)
        }) } })
    }
    private suspend fun post(path: String, body: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        validateAddress(baseUrl)
        require(token.isNotBlank() && !token.contains('\n') && !token.contains('\r')) { "请填写正确的连接口令" }
        val connection = URI(baseUrl.trim().trimEnd('/') + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"; connection.connectTimeout = 3000; connection.readTimeout = 12000
            connection.instanceFollowRedirects = false; connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val content = (if (code in 200..299) connection.inputStream else connection.errorStream)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(content) }.getOrElse { error("服务返回格式错误，请重试或手动填写") }
            if (code !in 200..299) error(json.optJSONObject("error")?.optString("message")?.takeIf { it.isNotBlank() } ?: "服务请求失败（$code），请核对地址、口令或输入字段")
            require(json.optBoolean("success")) { "服务未成功处理，请重试" }
            json
        } finally { connection.disconnect() }
    }
    suspend fun message(text: String, items: List<StockItem>, revision: Int): AgentReply {
        val json = post("/api/v1/agent/messages", snapshot(items, revision).put("text", text).put("request_id", UUID.randomUUID().toString()))
        val data = json.getJSONObject("data")
        val candidates = data.optJSONArray("candidates") ?: JSONArray()
        return AgentReply(data.getString("status"), data.getString("reply"), data.getString("trace_id"), json.getInt("expected_revision"), json.getString("engine"),
            data.optJSONObject("draft")?.command(), (0 until candidates.length()).map { candidates.getJSONObject(it).getString("id") }, data.optString("error_code").takeUnless { it == "null" }.orEmpty())
    }
    suspend fun validate(command: AgentCommand, items: List<StockItem>, revision: Int): AgentCommand =
        post("/api/v1/agent/drafts/validate", snapshot(items, revision).put("command", command.toJson())).getJSONObject("command").command()
}
