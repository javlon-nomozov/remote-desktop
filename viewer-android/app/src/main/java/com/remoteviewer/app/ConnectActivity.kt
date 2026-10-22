package com.remoteviewer.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Asosiy ekran (login'dan keyin): faqat unique KOD so'raladi. Server manzili Config'da.
 */
class ConnectActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_connect)
        val prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        val code = findViewById<EditText>(R.id.code)

        findViewById<Button>(R.id.btnConnect).setOnClickListener {
            val c = code.text.toString().trim()
            if (c.isEmpty()) {
                Toast.makeText(this, "Ulanish kodini kiriting", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            val token = prefs.getString("token", "") ?: ""
            val i = Intent(this, ViewerActivity::class.java)
            i.putExtra("mode", "relay")
            i.putExtra("relay", Config.backendWs)
            i.putExtra("code", c)
            i.putExtra("token", token)
            startActivity(i)
        }

        findViewById<Button>(R.id.btnLogout).setOnClickListener {
            prefs.edit().remove("token").apply()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }
}
