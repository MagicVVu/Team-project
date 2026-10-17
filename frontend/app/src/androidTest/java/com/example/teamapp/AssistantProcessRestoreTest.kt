package com.example.teamapp

import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.Process
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.SocketTimeoutException

/** Run prepare, adb force-stop, then restore in a separate instrumentation process. */
class AssistantProcessRestoreTest {
    private val args get() = InstrumentationRegistry.getArguments()
    private fun context(): ContextWrapper {
        val prefix = args.getString("processNamespace").orEmpty()
        assumeTrue(prefix.matches(Regex("p4process_[a-f0-9]{32}_")))
        return object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = super.getSharedPreferences(prefix + name, mode)
        }
    }
    @Test fun prepareUncertainConfirmedOperation() = runBlocking {
        val ctx = context(); val url = args.getString("executionTestUrl")!!
        val health = CloudApi(url).request("GET", "/api/v1/health")
        assertEquals("0.9.0", health.getString("version")); assertTrue(health.getBoolean("isolated_test"))
        val cloud = CloudStore(ctx)
        cloud.login(url, args.getString("fixturePhone")!!, args.getString("fixturePassword")!!)
        cloud.selectHousehold(args.getString("fixtureHousehold")!!)
        val a = AssistantStore(ctx, cloud, clientFactory = { acc -> object : AgentClient(acc.address, acc.token) {
            override suspend fun commit(id: String, body: JSONObject): JSONObject = throw SocketTimeoutException("Synthetic timeout before transport")
        } })
        a.bind(); a.send("纸巾消耗1包"); val draft = a.entries.last(); assertEquals(AssistantStatus.PENDING, draft.state)
        val before = cloud.items.single { it.name == "纸巾" }.quantity
        a.confirm(draft.requestId); val uncertain = a.entries.last(); assertEquals(AssistantStatus.UNKNOWN, uncertain.state)
        check(ctx.getSharedPreferences("restart_marker", 0).edit().putString("request_id", draft.requestId)
            .putString("body", uncertain.commitBody).putInt("pid", Process.myPid()).putString("before", before.toString()).commit())
    }
    @Test fun restoreAfterActualProcessDeath() = runBlocking {
        val ctx = context(); val marker = ctx.getSharedPreferences("restart_marker", 0)
        assertNotEquals("Runner must really kill the previous process", marker.getInt("pid", 0), Process.myPid())
        val cloud = CloudStore(ctx); assertTrue(cloud.signedIn)
        val a = cloud.assistant; a.connectAndRecover()
        val id = marker.getString("request_id", null)!!
        val pending = a.entries.single { it.requestId == id }
        assertEquals(AssistantStatus.UNKNOWN, pending.state); assertEquals(marker.getString("body", null), pending.commitBody)
        a.retryCommit(id)
        val done = a.entries.single { it.requestId == id }
        assertEquals(AssistantStatus.COMMITTED, done.state); assertEquals(marker.getString("body", null), done.commitBody)
        assertEquals(marker.getString("before", null)!!.toDouble() - 1, cloud.items.single { it.name == "纸巾" }.quantity, 0.0)
        a.retryCommit(id); assertEquals(done.receipt, a.entries.single { it.requestId == id }.receipt)
        cloud.logout()
    }
}
