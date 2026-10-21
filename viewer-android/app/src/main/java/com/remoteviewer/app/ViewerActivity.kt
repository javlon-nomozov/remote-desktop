package com.remoteviewer.app

import android.graphics.BitmapFactory
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject

class ViewerActivity : AppCompatActivity(), StreamClient.Listener {

    private lateinit var view: RemoteView
    private lateinit var client: StreamClient
    private lateinit var hiddenInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_viewer)

        view = findViewById(R.id.remoteView)
        hiddenInput = findViewById(R.id.hiddenInput)

        val host = intent.getStringExtra("host") ?: "127.0.0.1"
        val port = intent.getIntExtra("port", 8765)

        view.onInput = { json -> client.send(json) }

        findViewById<Button>(R.id.btnMode).setOnClickListener {
            view.touchpadMode = !view.touchpadMode
            (it as Button).text = if (view.touchpadMode) "Touchpad" else "Touch"
        }
        findViewById<Button>(R.id.btnKeyboard).setOnClickListener {
            hiddenInput.requestFocus()
            val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
            imm.showSoftInput(hiddenInput, InputMethodManager.SHOW_IMPLICIT)
        }
        findViewById<Button>(R.id.btnDisconnect).setOnClickListener { finish() }

        setupKeyboardCapture()

        client = StreamClient(host, port, this)
        client.connect()
    }

    /** Yozilgan matnni `text`, maxsus tugmalarni (Backspace/Enter) `key` sifatida yuboradi. */
    private fun setupKeyboardCapture() {
        hiddenInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (s != null && count > before) {
                    val added = s.subSequence(start + before, start + count).toString()
                    client.send(JSONObject().put("t", "text").put("value", added).toString())
                }
            }
            override fun afterTextChanged(s: Editable?) {
                if ((s?.length ?: 0) > 32) s?.clear()
            }
        })
        hiddenInput.setOnKeyListener { _, keyCode, event ->
            if (event.action == KeyEvent.ACTION_DOWN) {
                when (keyCode) {
                    KeyEvent.KEYCODE_DEL -> { sendKey("Backspace"); return@setOnKeyListener true }
                    KeyEvent.KEYCODE_ENTER -> { sendKey("Enter"); return@setOnKeyListener true }
                }
            }
            false
        }
    }

    private fun sendKey(code: String) {
        client.send(JSONObject().put("t", "key").put("code", code).put("down", true).toString())
        client.send(JSONObject().put("t", "key").put("code", code).put("down", false).toString())
    }

    // --- StreamClient.Listener ---
    override fun onHello(w: Int, h: Int, fps: Int) {
        runOnUiThread { title = "Remote ${w}x$h @${fps}fps" }
    }

    override fun onFrame(data: ByteArray) {
        val bmp = BitmapFactory.decodeByteArray(data, 0, data.size) ?: return
        view.setFrame(bmp)
    }

    override fun onClosed(reason: String) {
        runOnUiThread { finish() }
    }

    override fun onDestroy() {
        super.onDestroy()
        client.close()
    }
}
