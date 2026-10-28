package com.example.teamapp

import com.example.teamapp.data.validateAuthForm
import org.junit.Assert.*
import org.junit.Test

class AuthFormTest {
    @Test fun registrationRequiresValidFieldsAndMatchingPasswords() {
        assertEquals(setOf("nickname", "phone", "password"), validateAuthForm(true, "", "", "", "").keys)
        assertEquals("两次输入的密码不一致", validateAuthForm(true, "猫又", "13800138000", "green123456", "green456")["confirmation"])
        assertTrue(validateAuthForm(true, " 猫又 ", " 13800138000 ", "green123456", "green123456").isEmpty())
        listOf("abc1234", "12345678", "abcdefgh", "Abcdef12345678901", "Abcd123!", "Abcd123 ", "中文abc123", "Abcd1234\n").forEach {
            assertTrue(validateAuthForm(true, "猫又", "13800138000", it, it).containsKey("password"))
        }
        listOf("Abcd1234", "abcd1234", "ABCD1234", "Abcdef1234567890").forEach {
            assertTrue(validateAuthForm(true, "猫又", "13800138000", it, it).isEmpty())
        }
    }

    @Test fun loginDoesNotApplyNewRegistrationPasswordRules() {
        assertTrue(validateAuthForm(false, "", "13800138000", "old", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "+8613800138000", "old", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "13800138000", "Legacy-password-longer-than-16!", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "cat@", "old", "").containsKey("phone"))
        assertTrue(validateAuthForm(false, "", "13800138000", "", "").containsKey("password"))
    }
}
