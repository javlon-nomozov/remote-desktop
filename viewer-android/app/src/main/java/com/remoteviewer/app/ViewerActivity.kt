package com.remoteviewer.app

import android.annotation.SuppressLint
import android.graphics.BitmapFactory
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject

class ViewerActivity : AppCompatActivity(), StreamClient.Listener, SensorEventListener {

    private lateinit var view: RemoteView
    private lateinit var client: StreamClient
    private lateinit var hiddenInput: EditText
    private lateinit var touchpadBar: LinearLayout

    // Gyroskop (air-mouse)
    private lateinit var sensorManager: SensorManager
    private var gyroSensor: Sensor? = null
    private var gyroActive = false
    private var lastTs = 0L
    private var relButtons = 0  // touchpad tugmalari holati (1=chap, 2=o'ng)

    // Sezgirlik: burchak tezligini (rad/s) ekran ulushiga aylantiradi. Kerak bo'lsa sozlang.
    private val gyroGain = 2.6f

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_viewer)

        view = findViewById(R.id.remoteView)
        hiddenInput = findViewById(R.id.hiddenInput)
        touchpadBar = findViewById(R.id.touchpadBar)

        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        gyroSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        val url: String
        val handshake: String?
        if ((intent.getStringExtra("mode") ?: "relay") == "relay") {
            val relay = (intent.getStringExtra("relay") ?: "").trimEnd('/')
            url = "$relay/relay/viewer"
            handshake = JSONObject()
                .put("code", (intent.getStringExtra("code") ?: "").replace(" ", ""))
                .put("token", intent.getStringExtra("token") ?: "")
                .toString()
        } else {
            val host = intent.getStringExtra("host") ?: "127.0.0.1"
            val port = intent.getIntExtra("port", 8765)
            url = "ws://$host:$port"
            handshake = null
        }

        view.onInput = { json -> client.send(json) }

        findViewById<Button>(R.id.btnMode).setOnClickListener {
            view.touchpadMode = !view.touchpadMode
            (it as Button).text = if (view.touchpadMode) "Touchpad" else "Touch"
            touchpadBar.visibility = if (view.touchpadMode) View.VISIBLE else View.GONE
            if (!view.touchpadMode) stopGyro()  // touch rejimiga qaytganda gyroni o'chiramiz
        }
        findViewById<Button>(R.id.btnKeyboard).setOnClickListener {
            hiddenInput.requestFocus()
            val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
            imm.showSoftInput(hiddenInput, InputMethodManager.SHOW_IMPLICIT)
        }
        findViewById<Button>(R.id.btnDisconnect).setOnClickListener { finish() }

        setupTouchpadButtons()
        setupKeyboardCapture()

        client = StreamClient(url, handshake, this)
        client.connect()
    }

    // --- Touchpad tugmalari: Chap · GYRO · O'ng -----------------------
    @SuppressLint("ClickableViewAccessibility")
    private fun setupTouchpadButtons() {
        findViewById<Button>(R.id.btnLeft).setOnTouchListener { _, e -> onButton(e, 1); true }
        findViewById<Button>(R.id.btnRight).setOnTouchListener { _, e -> onButton(e, 2); true }
        findViewById<Button>(R.id.btnGyro).setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> startGyro()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> stopGyro()
            }
            true
        }
    }

    private fun onButton(e: MotionEvent, bit: Int) {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> relButtons = relButtons or bit
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> relButtons = relButtons and bit.inv()
            else -> return
        }
        sendRel(0.0, 0.0)  // tugma holatini yuboramiz (bosib turib surish = drag)
    }

    private fun startGyro() {
        val s = gyroSensor
        if (s == null) {
            Toast.makeText(this, "Bu qurilmada gyroskop yo'q", Toast.LENGTH_SHORT).show()
            return
        }
        gyroActive = true
        lastTs = 0L
        sensorManager.registerListener(this, s, SensorManager.SENSOR_DELAY_GAME)
    }

    private fun stopGyro() {
        if (gyroActive) {
            gyroActive = false
            sensorManager.unregisterListener(this)
        }
    }

    override fun onSensorChanged(e: SensorEvent) {
        if (!gyroActive) return
        if (lastTs == 0L) {
            lastTs = e.timestamp
            return
        }
        val dt = (e.timestamp - lastTs) / 1_000_000_000f
        lastTs = e.timestamp
        // values[0]=pitch rate (x), [1]=yaw rate (y). Telefonni chapga burish -> kursor chapga.
        val dx = -e.values[1] * dt * gyroGain
        val dy = -e.values[0] * dt * gyroGain
        if (dx != 0f || dy != 0f) sendRel(dx.toDouble(), dy.toDouble())
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun sendRel(dx: Double, dy: Double) {
        client.send(
            JSONObject().put("t", "mouse").put("dx", dx).put("dy", dy)
                .put("buttons", relButtons).put("mode", "rel").toString()
        )
    }

    // --- Klaviatura ---------------------------------------------------
    @SuppressLint("ClickableViewAccessibility")
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

    // --- StreamClient.Listener ----------------------------------------
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
        stopGyro()
        client.close()
    }
}
