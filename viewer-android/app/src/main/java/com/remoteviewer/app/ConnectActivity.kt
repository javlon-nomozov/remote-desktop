package com.remoteviewer.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Asosiy ekran (login'dan keyin). Ikki yo'l:
 *  - Internet: kompyuterdagi doimiy KODni kiritish (oxirgisi eslab qolinadi). Server manzili Config'da.
 *  - Lokal tarmoq (Wi-Fi / USB modem): ekran ochiq ekan, telefon o'zini e'lon qiladi; kompyuterdagi
 *    "Tarmoqdagi telefonlar" ro'yxatidan tanlansa (yoki telefon ishonchli bo'lsa) avtomatik ulanadi.
 */
class ConnectActivity : AppCompatActivity() {
    private var presence: LanPresence? = null
    private var launching = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_connect)
        val prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        val code = findViewById<EditText>(R.id.code)
        code.setText(prefs.getString("last_code", ""))
        findViewById<TextView>(R.id.lanStatus).text =
            "Kompyuterdagi «Tarmoqdagi telefonlar» ro'yxatidan «${Device.name()}» ni tanlang"

        findViewById<Button>(R.id.btnConnect).setOnClickListener {
            val c = code.text.toString().replace(" ", "").trim()
            if (c.isEmpty()) {
                Toast.makeText(this, "Ulanish kodini kiriting", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString("last_code", c).apply()
            val i = Intent(this, ViewerActivity::class.java)
            i.putExtra("mode", "relay")
            i.putExtra("relay", Config.backendWs)
            i.putExtra("code", c)
            i.putExtra("token", prefs.getString("token", "") ?: "")
            launch(i)
        }

        findViewById<Button>(R.id.btnLogout).setOnClickListener {
            prefs.edit().remove("token").apply()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }

    override fun onResume() {
        super.onResume()
        launching = false
        presence = LanPresence(this, Device.autoConnectAllowed(this)) { host, port, _ ->
            runOnUiThread {
                if (launching || isFinishing) return@runOnUiThread
                val i = Intent(this, ViewerActivity::class.java)
                i.putExtra("mode", "lan")
                i.putExtra("host", host)
                i.putExtra("port", port)
                launch(i)
            }
        }.also { it.start() }
    }

    override fun onPause() {
        super.onPause()
        presence?.stop()
        presence = null
    }

    private fun launch(i: Intent) {
        if (launching) return
        launching = true
        startActivity(i)
    }
}
