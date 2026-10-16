package com.example.teamapp

import com.example.teamapp.data.validateAuthForm
import org.junit.Assert.*
import org.junit.Test

class AuthFormTest {
    @Test fun registrationRequiresValidFieldsAndMatchingPasswords() {
        assertEquals(setOf("nickname", "phone", "password"), validateAuthForm(true, "", "", "", "").keys)
        assertEquals("两次输入的密码不一致", validateAuthForm(true, "猫又", "13800138000", "green123456", "green456")["confirmation"])
        assertTrue(validateAuthForm(true, " 猫又 ", " 13800138000 ", "green123456", "green123456").isEmpty())
        listOf("short1", "12345678", "abcdefgh", "a1".repeat(65)).forEach {
            assertTrue(validateAuthForm(true, "猫又", "13800138000", it, it).containsKey("password"))
        }
    }

    @Test fun loginDoesNotApplyNewRegistrationPasswordRules() {
        assertTrue(validateAuthForm(false, "", "13800138000", "old", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "+8613800138000", "old", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "cat@", "old", "").containsKey("phone"))
        assertTrue(validateAuthForm(false, "", "13800138000", "", "").containsKey("password"))
    }
}
