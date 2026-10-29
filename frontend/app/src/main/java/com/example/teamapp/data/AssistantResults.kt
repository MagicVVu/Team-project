package com.example.teamapp.data

import org.json.JSONArray
import org.json.JSONObject

/** Render only structured server results; never extract business facts from prose. */
internal object AssistantResults {
    fun collect(taskResult: JSONObject, response: String): List<JSONObject> {
        val public = if (response.isBlank()) JSONObject() else JSONObject(response)
        val results = mutableListOf<JSONObject>()
        if (taskResult.length() > 0) results += taskResult
        public.optJSONObject("task")?.optJSONObject("result")?.let { results += it }
        public.optJSONArray("evidence")?.objects()?.filter { it.optString("kind") == "verified_calculation" }
            ?.mapNotNullTo(results) { it.optJSONObject("result") }
        return results.filter { it.length() > 0 }.distinctBy(::canonical)
    }

    private fun canonical(value: Any?): String = when (value) {
        is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(prefix = "{", postfix = "}") {
            JSONObject.quote(it) + ":" + canonical(value.get(it))
        }
        is JSONArray -> (0 until value.length()).joinToString(prefix = "[", postfix = "]") { canonical(value.get(it)) }
        null, JSONObject.NULL -> "null"
        is String -> JSONObject.quote(value)
        is Number, is Boolean -> value.toString()
        else -> JSONObject.quote(value.toString())
    }
}
