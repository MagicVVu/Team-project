package com.example.teamapp.data

/** Request identities and the 20s server budget belong to a single durable turn. */
internal object ConversationProtocol {
    fun readTimeoutMillis(path: String): Int {
        val route = path.substringBefore('?')
        return if (route == "/api/v1/agent/conversation" ||
            route == "/api/v1/agent/conversation/reset" ||
            route == "/api/v1/agent/conversation-messages" ||
            route == "/api/v1/agent/conversation-turns" ||
            route.startsWith("/api/v1/agent/conversation-turns/")) 30_000 else 20_000
    }
}
