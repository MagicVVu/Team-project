package com.example.teamapp.data

import java.net.URI

/** Fail-closed target policy, shared by login, business writes and AI discovery. */
object TargetPolicy {
    private val loopback = setOf("localhost", "127.0.0.1", "10.0.2.2", "::1")
    fun address(value: String, isolatedTest: Boolean, configuredOrigin: String): String {
        val uri = runCatching { URI(value.trim()) }.getOrElse { error("请输入正确的服务器地址") }
        require(uri.host != null && uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty() in setOf("", "/")) { "请输入服务器根地址" }
        require(uri.scheme == "https" || (isolatedTest && uri.scheme == "http" && uri.host in loopback)) { "服务器需要 HTTPS；HTTP 仅限显式隔离测试的回环通道" }
        val normalized = uri.toASCIIString().trimEnd('/')
        if (!isolatedTest) {
            require(configuredOrigin.isNotBlank()) { "此构建尚未配置 HTTPS 服务，网络功能保持关闭" }
            val configured = URI(configuredOrigin.trim().trimEnd('/'))
            require(configured.scheme == "https" && configured.host !in loopback && configured.host != null &&
                configured.userInfo == null && configured.query == null && configured.fragment == null && configured.path.orEmpty() in setOf("", "/")) { "HTTPS 服务配置无效" }
            require(normalized == configured.toASCIIString().trimEnd('/')) { "当前构建只能连接已配置的 HTTPS 服务" }
        }
        return normalized
    }
    fun health(expectedIsolated: Boolean, service: String, version: String, isolated: Boolean) {
        require(service == "magicvvu-backend" && version == "0.9.0") { "后端版本尚不支持本候选执行协议，写入已停用" }
        require(isolated == expectedIsolated) { if (expectedIsolated) "显式隔离测试只能连接已验证的隔离服务" else "当前构建配置为共享云端，请勿连接隔离测试服务" }
    }
    fun capabilities(protocol: String, owner: String) {
        require(protocol == "draft-execution-1" && owner == "business_backend") { "后端执行协议不匹配，写入已停用" }
    }
}
