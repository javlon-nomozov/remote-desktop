package com.remoteviewer.app

import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.util.UUID

/**
 * Kirish ekrani: "Telegram orqali kirish" tugmasi. Tugmaча Telegram bot ochiladi, foydalanuvchi
 * telefon raqamini ulashib tasdiqlaydi, so'ng ilovaga qaytadi. Ilova backenddan tokenni oladi.
 */
class LoginActivity : AppCompatActivity() {
    private val http = OkHttpClient()
    private var nonce: String? = null
    private lateinit var prefs: SharedPreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        if (!prefs.getString("token", "").isNullOrEmpty()) {
            goConnect()
            return
        }
        setContentView(R.layout.activity_login)
        findViewById<Button>(R.id.btnLogin).setOnClickListener { startLogin() }
        findViewById<Button>(R.id.btnCheck).setOnClickListener { poll(true) }
    }

    private fun startLogin() {
        val n = UUID.randomUUID().toString().replace("-", "")
        nonce = n
        prefs.edit().putString("nonce", n).apply()
        val url = "https://t.me/${Config.BOT_USERNAME}?start=login_$n"
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: Exception) {
            Toast.makeText(this, "Telegram ilovasi topilmadi", Toast.LENGTH_SHORT).show()
        }
        findViewById<View>(R.id.afterLogin).visibility = View.VISIBLE
    }

    override fun onResume() {
        super.onResume()
        if (nonce == null) nonce = prefs.getString("nonce", null)
        if (nonce != null) poll(false)  // Telegramдan qaytganда avtomatik tekshiramiz
    }

    private fun poll(manual: Boolean) {
        val n = nonce ?: prefs.getString("nonce", null) ?: return
        val req = Request.Builder().url("${Config.BACKEND_HTTP}/auth/poll?nonce=$n").build()
        http.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (manual) runOnUiThread {
                    Toast.makeText(this@LoginActivity, "Serverga ulanib bo'lmadi", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string() ?: return
                try {
                    val token = JSONObject(body).optString("token", "")
                    if (token.isNotEmpty()) {
                        prefs.edit().putString("token", token).remove("nonce").apply()
                        runOnUiThread { goConnect() }
                    } else if (manual) {
                        runOnUiThread {
                            Toast.makeText(this@LoginActivity, "Hali tasdiqlanmagan", Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (_: Exception) {
                }
            }
        })
    }

    private fun goConnect() {
        startActivity(Intent(this, ConnectActivity::class.java))
        finish()
    }
}
