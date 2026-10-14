package com.example.teamapp.data

/** Client-side form checks only. Account creation and authentication require a server. */
internal fun validateAuthForm(
    registering: Boolean,
    nickname: String,
    email: String,
    password: String,
    confirmation: String
): Map<String, String> = buildMap {
    if (registering && nickname.trim().length !in 1..20) put("nickname", "请输入 1–20 个字符的昵称")
    if (!Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$").matches(email.trim())) put("email", "请输入有效的邮箱地址")
    if (password.isBlank()) put("password", "请输入密码")
    else if (registering && (password.length !in 8..64 || password.none { it.isLetter() } || password.none { it.isDigit() })) {
        put("password", "密码需为 8–64 位，包含字母和数字")
    }
    if (registering && confirmation != password) put("confirmation", "两次输入的密码不一致")
}
