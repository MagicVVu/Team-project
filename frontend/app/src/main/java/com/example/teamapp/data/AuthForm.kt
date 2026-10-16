package com.example.teamapp.data

/** Client-side form checks only. Account creation and authentication require a server. */
internal fun validateAuthForm(
    registering: Boolean,
    nickname: String,
    phone: String,
    password: String,
    confirmation: String
): Map<String, String> = buildMap {
    if (registering && nickname.trim().length !in 1..20) put("nickname", "请输入 1–20 个字符的昵称")
    if (!Regex("^(1[3-9][0-9]{9}|\\+[1-9][0-9]{7,14})$").matches(phone.trim())) put("phone", "请输入大陆 11 位手机号或带国家码的号码")
    if (password.isBlank()) put("password", "请输入密码")
    else if (registering && password.length !in 10..128) {
        put("password", "密码需为 10–128 位")
    }
    if (registering && confirmation != password) put("confirmation", "两次输入的密码不一致")
}
