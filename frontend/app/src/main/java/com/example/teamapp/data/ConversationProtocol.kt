package com.example.teamapp.data

/** Long conversation requests allow the server to return a durable outcome. */
internal object ConversationProtocol {
    fun readTimeoutMillis(path: String): Int {
        val route = path.substringBefore('?')
        return if (route == "/api/v1/agent/conversation" ||
            route == "/api/v1/agent/conversation/reset" ||
            route == "/api/v1/agent/conversation-messages" ||
            route == "/api/v1/agent/conversation-turns" ||
            route.startsWith("/api/v1/agent/conversation-turns/")) 90_000 else 20_000
    }
}
