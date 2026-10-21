package com.remoteviewer.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import androidx.appcompat.app.AppCompatActivity

/** Ulanish ekrani: server IP + port kiritiladi va viewer ochiladi. */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val host = findViewById<EditText>(R.id.host)
        val port = findViewById<EditText>(R.id.port)

        findViewById<Button>(R.id.connect).setOnClickListener {
            val intent = Intent(this, ViewerActivity::class.java)
            intent.putExtra("host", host.text.toString().ifBlank { "127.0.0.1" })
            intent.putExtra("port", port.text.toString().toIntOrNull() ?: 8765)
            startActivity(intent)
        }
    }
}
