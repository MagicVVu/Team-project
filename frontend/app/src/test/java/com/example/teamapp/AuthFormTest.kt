package com.example.teamapp

import com.example.teamapp.data.validateAuthForm
import org.junit.Assert.*
import org.junit.Test

class AuthFormTest {
    @Test fun registrationRequiresValidFieldsAndMatchingPasswords() {
        assertEquals(setOf("nickname", "email", "password"), validateAuthForm(true, "", "", "", "").keys)
        assertEquals("两次输入的密码不一致", validateAuthForm(true, "猫又", "cat@example.com", "green123", "green456")["confirmation"])
        assertTrue(validateAuthForm(true, " 猫又 ", " cat@example.com ", "green123", "green123").isEmpty())
        listOf("short1", "12345678", "abcdefgh", "a1".repeat(33)).forEach {
            assertTrue(validateAuthForm(true, "猫又", "cat@example.com", it, it).containsKey("password"))
        }
    }

    @Test fun loginDoesNotApplyNewRegistrationPasswordRules() {
        assertTrue(validateAuthForm(false, "", "cat@example.com", "old", "").isEmpty())
        assertTrue(validateAuthForm(false, "", "cat@", "old", "").containsKey("email"))
        assertTrue(validateAuthForm(false, "", "cat@example.com", "", "").containsKey("password"))
    }
}
