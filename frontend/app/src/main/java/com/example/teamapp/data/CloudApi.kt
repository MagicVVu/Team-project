package com.example.teamapp.data

import com.example.teamapp.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.math.BigDecimal
import java.net.HttpURLConnection
import java.net.URI
import java.util.UUID
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.security.MessageDigest

data class CloudAccount(val address: String, val token: String, val userId: String, val displayName: String, val householdId: String = "") {
    override fun toString() = "CloudAccount(session=[REDACTED])"
}
data class CloudHousehold(val id: String, val name: String, val role: String)
data class CloudMember(val userId: String, val name: String, val role: String, val joinedAt: String)
data class CloudShoppingItem(val id: String, val sourceId: String, val name: String, val quantity: Double, val unit: String,
    val purchased: Boolean, val addedBy: String, val purchasedBy: String)
class CloudFailure(val status: Int, message: String, val errorCode: String = "", val taskIdHint: String = "") : IOException(message)

/** No automatic mutation retries: callers keep IDs stable when retrying a confirmed operation. */
open class CloudApi(val address: String, private val token: String = "") {
    companion object {
        private val targetChecks = TargetCheckCache()
        private val discovery = Mutex()
        fun validateAddress(value: String) {
            TargetPolicy.address(value, BuildConfig.CLOUD_EXPECT_ISOLATED, BuildConfig.CLOUD_API_URL)
        }
    }
    private val targetKey get() = address + ":" + MessageDigest.getInstance("SHA-256").digest(token.toByteArray()).joinToString("") { "%02x".format(it) }
    open suspend fun verifiedCapabilities(): JSONObject = discovery.withLock {
        val now = System.nanoTime() / 1_000_000
        targetChecks.get(targetKey, now)?.let { return@withLock JSONObject(it) }
        val health = request("GET", "/api/v1/health")
        TargetPolicy.health(BuildConfig.CLOUD_EXPECT_ISOLATED, health.optString("service"), health.optString("version"), health.getBoolean("isolated_test"))
        val caps = request("GET", "/api/v1/agent/execution-capabilities")
        TargetPolicy.capabilities(caps.optString("protocol_version"), caps.optString("owner"))
        targetChecks.put(targetKey, System.nanoTime() / 1_000_000, caps.toString())
        caps
    }

    open suspend fun request(method: String, path: String, body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        validateAddress(address)
        require(!token.contains('\r') && !token.contains('\n'))
        if (method !in setOf("GET", "HEAD")) {
            if (!path.startsWith("/api/v1/auth/")) verifiedCapabilities()
            else {
                val health = request("GET", "/api/v1/health")
                TargetPolicy.health(BuildConfig.CLOUD_EXPECT_ISOLATED, health.optString("service"), health.optString("version"), health.getBoolean("isolated_test"))
            }
        }
        val connection = URI(address.trim().trimEnd('/') + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 5000
            connection.readTimeout = 20000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty(TeamApiAccess.HEADER, TeamApiAccess.KEY)
            if (token.isNotEmpty()) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val text = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val message = when (status) {
                    401 -> "登录已失效或手机号、密码不正确，请重新登录"
                    403 -> "当前账号没有权限；若在注册，服务器尚未开放自助注册"
                    404 -> "家庭或物品已不存在，或你没有访问权限，请刷新"
                    409 -> "记录已被其他成员更新，请刷新并重新核对；购买记录请勿重复新建"
                    422 -> "请核对输入：库存最多六位小数，采购最多三位小数，名称、数量和单位不能为空"
                    503 -> "服务器暂时不可用，请稍后重试"
                    else -> "请求失败（$status），请刷新核对后重试"
                }
                val code = runCatching { JSONObject(text).optJSONObject("detail")?.optString("code").orEmpty() }.getOrDefault("")
                if (status in setOf(401, 403, 503)) targetChecks.invalidate(targetKey)
                val hint = runCatching { JSONObject(text).optJSONObject("detail")?.optString("task_id").orEmpty() }.getOrDefault("")
                throw CloudFailure(status, ChatMessages.reason(code, message), code, hint)
            }
            when {
                text.isBlank() -> JSONObject()
                text.trimStart().startsWith("[") -> JSONObject().put("items", JSONArray(text))
                else -> JSONObject(text)
            }
        } catch (failure: CloudFailure) { throw failure }
        catch (failure: IOException) { throw IOException("无法连接服务器。请检查网络、服务器地址、证书及服务器访问策略；如刚提交操作，请先刷新核对结果。", failure) }
        finally { connection.disconnect() }
    }

    suspend fun login(phone: String, password: String): CloudAccount {
        val result = request("POST", "/api/v1/auth/login", JSONObject().put("phone", phone).put("password", password))
        val secret = result.getString("access_token")
        val user = CloudApi(address, secret).request("GET", "/api/v1/users/me")
        return CloudAccount(address.trim().trimEnd('/'), secret, user.getString("id"), user.getString("display_name"))
    }
    suspend fun register(phone: String, password: String, name: String) {
        request("POST", "/api/v1/auth/register", JSONObject().put("phone", phone).put("password", password).put("display_name", name))
    }
    suspend fun households(): List<CloudHousehold> = request("GET", "/api/v1/households").getJSONArray("items").objects().map {
        CloudHousehold(it.getString("id"), it.getString("name"), it.getString("my_role"))
    }
    suspend fun pages(path: String): List<JSONObject> {
        val rows = mutableListOf<JSONObject>()
        var offset = 0
        do {
            val page = request("GET", path + (if ('?' in path) "&" else "?") + "limit=100&offset=$offset")
            val next = page.getJSONArray("items").objects()
            rows.addAll(next)
            offset += next.size
        } while (next.isNotEmpty() && offset < page.getInt("total"))
        return rows
    }
}

internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
internal fun JSONObject.stringOrEmpty(key: String): String = if (isNull(key)) "" else optString(key)
internal fun JSONObject.toStock(): StockItem = StockItem(
    id = getString("id"), name = getString("name"), quantity = getString("quantity").toDouble(), unit = getString("unit"),
    category = InventoryContract.categoryLabel(stringOrEmpty("category").ifBlank { "unknown" }), location = stringOrEmpty("storage_location").ifBlank { "待定位" },
    minimum = optString("minimum_quantity", "0").toDouble(), expiry = stringOrEmpty("expires_on"), purchasedAt = stringOrEmpty("purchased_on"),
    history = optJSONArray("history_json")?.objects()?.map { it.stringOrEmpty("created_at").take(16).replace('T', ' ') + " · " + it.stringOrEmpty("message").ifBlank { it.stringOrEmpty("kind") } }.orEmpty(),
    version = getInt("version"), openedAt = stringOrEmpty("opened_at"), lifecycleStatus = stringOrEmpty("status").ifBlank { "ACTIVE" },
    quantityExact = getString("quantity")
)
internal fun JSONObject.toShopping(): CloudShoppingItem = CloudShoppingItem(getString("id"), stringOrEmpty("source_inventory_item_id"),
    getString("name"), getString("quantity").toDouble(), getString("unit"), getBoolean("is_checked"), stringOrEmpty("added_by_user_id"), stringOrEmpty("purchased_by_user_id"))
internal fun StockItem.toCloudJson() = JSONObject().put("id", id).put("name", name).put("quantity", BigDecimal.valueOf(quantity).toPlainString())
    .put("unit", InventoryContract.unit(unit) ?: unit).put("category", InventoryContract.category(category)).put("storage_location", location).put("minimum_quantity", BigDecimal.valueOf(minimum).toPlainString())
    .put("expires_on", expiry.ifBlank { null } ?: JSONObject.NULL).put("purchased_on", purchasedAt.ifBlank { null } ?: JSONObject.NULL)
internal fun versionBody(item: StockItem, operationId: String = UUID.randomUUID().toString()) =
    JSONObject().put("expected_version", item.version).put("operation_id", operationId)
