package com.example.teamapp

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.teamapp.data.CloudApi
import com.example.teamapp.data.CloudFailure
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** No account, login, writes, or test fixture creation on the shared server. */
@RunWith(AndroidJUnit4::class)
class DirectTlsConnectivityTest {
    @Test fun appTlsPolicyAcceptsConfiguredServerAndParsesHealth() = runBlocking {
        assertEquals("internal", BuildConfig.BUILD_TYPE)
        assertFalse(BuildConfig.CLOUD_EXPECT_ISOLATED)
        assertTrue(BuildConfig.CLOUD_API_URL.startsWith("https://"))
        val health = CloudApi(BuildConfig.CLOUD_API_URL).request("GET", "/api/v1/health")
        assertEquals("magicvvu-backend", health.getString("service"))
        assertEquals("0.9.0", health.getString("version"))
        assertFalse(health.getBoolean("isolated_test"))
    }

    @Test fun appReachesAuthenticationGateWithoutCredentials() = runBlocking {
        val failure = runCatching {
            CloudApi(BuildConfig.CLOUD_API_URL).request("GET", "/api/v1/users/me")
        }.exceptionOrNull()
        assertTrue("Expected an authenticated server response, got ${failure?.javaClass?.simpleName}", failure is CloudFailure)
        assertEquals(401, (failure as CloudFailure).status)
    }
}
