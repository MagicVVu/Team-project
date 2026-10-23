package com.example.teamapp.data

/** Short-lived discovery only. Every business request is still authorized by the server. */
class TargetCheckCache(private val ttlMillis: Long = 15_000, private val capacity: Int = 16) {
    private val values = linkedMapOf<String, Pair<Long, String>>()
    @Synchronized fun get(key: String, now: Long): String? = values[key]?.takeIf { now >= it.first && now - it.first < ttlMillis }?.second
    @Synchronized fun put(key: String, now: Long, value: String) {
        values.remove(key)
        values[key] = now to value
        while (values.size > capacity) values.remove(values.keys.first())
    }
    @Synchronized fun invalidate(key: String) { values.remove(key) }
}
