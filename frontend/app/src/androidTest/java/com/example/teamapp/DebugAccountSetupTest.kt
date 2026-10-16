package com.example.teamapp

import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.BuildConfig
import com.example.teamapp.data.InventoryStore
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/** Explicit handoff of the user-authorized debug account, via an app-private file. */
class DebugAccountSetupTest {
    @Test fun signInToExplicitlyProvidedDebugAccount() = runBlocking {
        assumeTrue(BuildConfig.DEBUG && InstrumentationRegistry.getArguments().getString("setupDebugAccount") == "yes")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val file = context.filesDir.resolve("magicvvu-debug-bootstrap.json")
        check(file.isFile) { "Missing app-private account handoff file" }
        try {
            val json = JSONObject(file.readText())
            val store = InventoryStore(context)
            check(store.cloud.account == null || store.cloud.account?.userId == json.getString("user_id")) { "An existing cloud account is signed in; refusing to overwrite it" }
            store.cloud.login(json.getString("server_url"), json.getString("phone"), json.getString("password"))
            assertEquals(json.getString("user_id"), store.cloud.account?.userId)
            assertEquals(json.getString("household_id"), store.cloud.account?.householdId)
            store.cloud.refresh()
            assertTrue(store.cloud.lastSync.isNotBlank())
        } finally { file.delete() }
    }
}
