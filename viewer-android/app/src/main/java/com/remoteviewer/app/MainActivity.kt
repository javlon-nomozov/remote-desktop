package com.remoteviewer.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Ulanish ekrani:
 *  - Kod orqali (relay): server manzili + kod + kirish tokeni.
 *  - LAN orqali (IP): host + port.
 * Oxirgi kiritilgan server manzili va token eslab qolinadi.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        val relayUrl = findViewById<EditText>(R.id.relayUrl)
        val code = findViewById<EditText>(R.id.code)
        val token = findViewById<EditText>(R.id.token)
        val host = findViewById<EditText>(R.id.host)
        val port = findViewById<EditText>(R.id.port)

        relayUrl.setText(prefs.getString("relay", ""))
        token.setText(prefs.getString("token", ""))
        host.setText(prefs.getString("host", ""))

        findViewById<Button>(R.id.btnCode).setOnClickListener {
            val relay = relayUrl.text.toString().trim()
            val c = code.text.toString().trim()
            if (relay.isEmpty() || c.isEmpty()) {
                Toast.makeText(this, "Server manzili va kodni kiriting", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit()
                .putString("relay", relay)
                .putString("token", token.text.toString().trim())
                .apply()
            val i = Intent(this, ViewerActivity::class.java)
            i.putExtra("mode", "relay")
            i.putExtra("relay", relay)
            i.putExtra("code", c)
            i.putExtra("token", token.text.toString().trim())
            startActivity(i)
        }

        findViewById<Button>(R.id.btnLan).setOnClickListener {
            val h = host.text.toString().trim()
            if (h.isEmpty()) {
                Toast.makeText(this, "Server IP ni kiriting", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString("host", h).apply()
            val i = Intent(this, ViewerActivity::class.java)
            i.putExtra("mode", "lan")
            i.putExtra("host", h)
            i.putExtra("port", port.text.toString().toIntOrNull() ?: 8765)
            startActivity(i)
        }
    }
}
