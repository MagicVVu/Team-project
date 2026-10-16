package com.example.teamapp.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Only an encrypted session envelope is persisted; passwords are never stored. */
internal class CloudCredentials(context: Context) {
    private val preferences = context.getSharedPreferences("magicvvu_cloud_credentials", Context.MODE_PRIVATE)
    private val alias = "magicvvu_cloud_session_v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun save(account: CloudAccount?) {
        if (account == null) { check(preferences.edit().remove("session").commit()); return }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val json = JSONObject().put("address", account.address).put("token", account.token).put("userId", account.userId)
            .put("displayName", account.displayName).put("householdId", account.householdId)
        val encrypted = cipher.doFinal(json.toString().toByteArray(Charsets.UTF_8))
        val envelope = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(encrypted, Base64.NO_WRAP)
        check(preferences.edit().putString("session", envelope).commit()) { "无法安全保存登录状态，请检查设备存储" }
    }
    fun load(): CloudAccount? {
        val envelope = preferences.getString("session", null) ?: return null
        return runCatching {
            val parts = envelope.split(':')
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)))
            }
            val json = JSONObject(String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), Charsets.UTF_8))
            CloudAccount(json.getString("address"), json.getString("token"), json.getString("userId"), json.getString("displayName"), json.optString("householdId"))
        }.getOrElse { preferences.edit().remove("session").commit(); null }
    }
}
