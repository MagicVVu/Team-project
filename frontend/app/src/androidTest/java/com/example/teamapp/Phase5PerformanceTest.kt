package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.util.UUID

class Phase5PerformanceTest {
    @Test fun androidRulesFlowLatencyHasTwentyRealSamples() = runBlocking {
        val args = InstrumentationRegistry.getArguments(); val url = args.getString("executionTestUrl").orEmpty()
        assumeTrue(url.isNotBlank())
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val prefix = "p5perf_${UUID.randomUUID()}_"
        val ctx = object : ContextWrapper(target) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
        val cloud = CloudStore(ctx)
        cloud.login(url, args.getString("fixturePhone")!!, args.getString("fixturePassword")!!)
        cloud.selectHousehold(args.getString("fixtureHousehold")!!)
        val values = mutableMapOf<String, MutableList<Double>>()
        fun record(name: String, started: Long) { values.getOrPut(name) { mutableListOf() }.add((SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0) }
        val a = AssistantStore(ctx, cloud, clientFactory = { account -> object : AgentClient(account.address, account.token) {
            override suspend fun message(body: JSONObject): JSONObject {
                val start = SystemClock.elapsedRealtimeNanos(); return super.message(body).also { record("message_http_including_preflight", start) }
            }
            override suspend fun draft(id: String): JSONObject {
                val start = SystemClock.elapsedRealtimeNanos(); return super.draft(id).also { record("draft_read_http", start) }
            }
            override suspend fun commit(id: String, body: JSONObject): JSONObject {
                val start = SystemClock.elapsedRealtimeNanos(); return super.commit(id, body).also { record("commit_http_including_preflight", start) }
            }
        } }, refreshHousehold = {
            val start = SystemClock.elapsedRealtimeNanos(); cloud.refresh(); record("inventory_and_shopping_refresh", start)
        })
        val before = cloud.items.single { it.name == "纸巾" }.quantity
        repeat(20) {
            val start = SystemClock.elapsedRealtimeNanos()
            a.send("纸巾消耗一包。")
            val draft = a.entries.last(); assertEquals(a.error, AssistantStatus.PENDING, draft.state)
            a.confirm(draft.requestId)
            assertEquals(a.error, AssistantStatus.COMMITTED, a.entries.last().state)
            record("android_message_to_receipt_and_refresh_no_human_delay", start)
        }
        assertEquals(before - 20, cloud.items.single { it.name == "纸巾" }.quantity, 0.0)
        val output = JSONObject().put("engine", "rules").put("samples", JSONObject().apply { values.forEach { (k, v) -> put(k, JSONArray(v)) } })
        val path = target.cacheDir.resolve("phase5/android-performance.json"); path.parentFile!!.mkdirs(); path.writeText(output.toString())
        cloud.logout()
    }
}
