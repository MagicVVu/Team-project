package com.example.teamapp

import com.example.teamapp.data.TargetPolicy
import com.example.teamapp.data.CloudAccount
import org.junit.Assert.*
import org.junit.Test

class TargetPolicyTest {
    @Test fun generatedBuildUsesItsSelectedEnvironmentAndRejectsTheOpposite() {
        val selected = BuildConfig.CLOUD_EXPECT_ISOLATED
        TargetPolicy.address(BuildConfig.CLOUD_API_URL, selected, BuildConfig.CLOUD_API_URL)
        TargetPolicy.health(selected, "magicvvu-backend", "0.9.0", selected)
        assertTrue(runCatching { TargetPolicy.health(selected, "magicvvu-backend", "0.9.0", !selected) }.isFailure)
        if (!selected) assertTrue(BuildConfig.CLOUD_API_URL.startsWith("https://"))
    }
    @Test fun dailyTestBuildPinsSharedServerAndRequiresTls() {
        val origin = "https://8.134.172.165:8000"
        assertEquals(origin, TargetPolicy.address(origin, false, origin))
        TargetPolicy.health(false, "magicvvu-backend", "0.9.0", false)
        for (url in listOf("http://8.134.172.165:8000", "https://8.134.172.165:8443", "https://other.example.com"))
            assertTrue(runCatching { TargetPolicy.address(url, false, origin) }.isFailure)
        assertTrue(runCatching { TargetPolicy.health(false, "magicvvu-backend", "0.9.0", true) }.isFailure)
    }
    @Test fun explicitIsolationRejectsSharedAndOldBackends() {
        TargetPolicy.address("http://10.0.2.2:18083", true, "")
        TargetPolicy.health(true, "magicvvu-backend", "0.9.0", true)
        assertTrue(runCatching { TargetPolicy.health(true, "magicvvu-backend", "0.8.0", true) }.isFailure)
        assertTrue(runCatching { TargetPolicy.health(true, "magicvvu-backend", "0.9.0", false) }.isFailure)
        assertTrue(runCatching { TargetPolicy.address("http://public.example.com", true, "") }.isFailure)
    }
    @Test fun releaseRequiresExplicitHttpsOriginAndProductionContract() {
        val origin = "https://api.example.com"
        TargetPolicy.address(origin, false, origin)
        TargetPolicy.health(false, "magicvvu-backend", "0.9.0", false)
        TargetPolicy.capabilities("draft-execution-1", "business_backend")
        for (url in listOf("http://api.example.com", "http://10.0.2.2:18083", "https://other.example.com", "https://api.example.com/path", "https://user@api.example.com"))
            assertTrue(runCatching { TargetPolicy.address(url, false, origin) }.isFailure)
        assertTrue(runCatching { TargetPolicy.address(origin, false, "") }.isFailure)
        assertTrue(runCatching { TargetPolicy.health(false, "magicvvu-backend", "0.8.0", false) }.isFailure)
        assertTrue(runCatching { TargetPolicy.health(false, "magicvvu-backend", "0.9.0", true) }.isFailure)
        assertTrue(runCatching { TargetPolicy.capabilities("unknown", "business_backend") }.isFailure)
    }
    @Test fun accountStringCannotAccidentallyLogCredentials() {
        val a = CloudAccount("https://api.example.com", "synthetic-sensitive", "user", "name")
        assertFalse(a.toString().contains(a.token)); assertFalse(a.toString().contains(a.userId))
    }
}
