package com.example.teamapp

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.example.teamapp.data.InventoryStore
import com.example.teamapp.ui.AppEntry
import com.example.teamapp.ui.AuthScreen
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class AuthScreenTest {
    @get:Rule val compose = createComposeRule()

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val folder = context.cacheDir.resolve("auth-verification").apply { mkdirs() }
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        folder.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun lightFormsValidateAndDoNotReportAuthenticationSuccess() {
        var guestCount = 0
        compose.setContent { TeamAppTheme(darkTheme = false) { AuthScreen { guestCount++ } } }
        screenshot("light-login")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithText("请输入有效的邮箱地址").assertExists()
        compose.onNodeWithText("请输入密码").assertExists()
        compose.onNodeWithTag("auth-email").performScrollTo().performTextInput("cat@example.com")
        compose.onNodeWithTag("auth-password").performScrollTo().performTextInput("green123")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithTag("auth-service-notice").assertExists()
        compose.onNodeWithText("去注册").performScrollTo().performClick()
        compose.onNodeWithTag("auth-password").assertTextContains("")
        screenshot("light-register")
        compose.onNodeWithTag("auth-nickname").performScrollTo().performTextInput("猫又")
        compose.onNodeWithTag("auth-email").performScrollTo().performTextInput("cat@example.com")
        compose.onNodeWithTag("auth-password").performScrollTo().performTextInput("green123")
        compose.onNodeWithTag("auth-confirmation").performScrollTo().performTextInput("green456")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithText("两次输入的密码不一致").assertExists()
        compose.onNodeWithTag("auth-confirmation").performScrollTo().performTextClearance()
        compose.onNodeWithTag("auth-confirmation").performTextInput("green123")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.onNodeWithTag("auth-service-notice").assertExists()
        compose.onNodeWithText("以游客身份体验").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(1, guestCount) }
    }

    @Test fun darkFormsAndGuestCanNavigateBackFromProfile() {
        val context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
                super.getSharedPreferences("auth_test_$name", mode)
        }
        val preferences = context.getSharedPreferences("magicvvu_v1", Context.MODE_PRIVATE)
        preferences.edit().clear().commit()
        try {
            val store = InventoryStore(context)
            compose.setContent { TeamAppTheme(darkTheme = true) { AppEntry(store) } }
            screenshot("dark-login")
            compose.onNodeWithText("去注册").performScrollTo().performClick()
            screenshot("dark-register")
            compose.onNodeWithText("先逛逛 ›").performScrollTo().performClick()
            compose.onNodeWithText("我的", useUnmergedTree = true).performClick()
            compose.onNodeWithText("登录 / 注册").performScrollTo().performClick()
            compose.onNodeWithText("登录拾物").assertExists()
            compose.onNodeWithText("以游客身份体验").performScrollTo().performClick()
            compose.onNodeWithText("首页", useUnmergedTree = true).assertExists()
        } finally {
            preferences.edit().clear().commit()
        }
    }
}
