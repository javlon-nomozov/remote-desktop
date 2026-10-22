package com.remoteviewer.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.BitmapFactory
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.MediaScannerConnection
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.text.Editable
import android.text.TextWatcher
import android.util.TypedValue
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ViewerActivity : AppCompatActivity(), StreamClient.Listener, SensorEventListener {

    private lateinit var view: RemoteView
    private lateinit var client: StreamClient
    private lateinit var hiddenInput: EditText
    private lateinit var touchpadBar: LinearLayout
    private lateinit var keysBar: LinearLayout

    // Kompyuter tugmalari: yoniq (yopishqoq) modifikatorlar, code -> tugma.
    // Keyingi oddiy tugma/harfdan keyin avtomatik qo'yib yuboriladi (Ctrl+C, Win+R, Alt+F4...).
    private val heldMods = LinkedHashMap<String, MaterialButton>()

    // Ulanish holati
    private lateinit var statusView: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var mode = "relay"  // "relay" (internet kodi) | "lan" (Wi-Fi / USB)
    private var relayUrl = ""
    private var code = ""
    private var token = ""
    private var lanHost = ""
    private var lanPort = 0
    private var approvedOnce = false   // shu ekranda kamida bir marta ruxsat olindi
    private var trustUntilMs = 0L      // ishonch muddati (0 = cheksiz/noma'lum)
    private var terminal = false       // rad / muddat / ✕ — qayta ulanmaymiz
    private var visible = false
    private var attempt = 0
    private var reconnectPending = false
    @Volatile private var lastRxMs = 0L
    private var lanPresence: LanPresence? = null

    // Screenshot: oxirgi kelgan JPEG kadr (qayta siqilmasdan saqlanadi)
    @Volatile private var lastJpeg: ByteArray? = null
    private var pendingShot: ByteArray? = null  // Android 9 va past: ruxsat kutilayotgan kadr

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
        keysBar = findViewById(R.id.keysBar)

        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        gyroSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        statusView = findViewById(R.id.statusText)
        mode = intent.getStringExtra("mode") ?: "relay"
        relayUrl = (intent.getStringExtra("relay") ?: "").trimEnd('/')
        code = (intent.getStringExtra("code") ?: "").replace(" ", "")
        token = intent.getStringExtra("token") ?: ""
        lanHost = intent.getStringExtra("host") ?: ""
        lanPort = intent.getIntExtra("port", 0)

        view.onInput = { json -> client.send(json) }

        findViewById<Button>(R.id.btnMode).setOnClickListener {
            view.touchpadMode = !view.touchpadMode
            (it as Button).text = if (view.touchpadMode) "Touchpad" else "Touch"
            touchpadBar.visibility = if (view.touchpadMode) View.VISIBLE else View.GONE
            if (!view.touchpadMode) stopGyro()  // touch rejimiga qaytganda gyroni o'chiramiz
        }
        findViewById<Button>(R.id.btnKeyboard).setOnClickListener {
            val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
            if (keysBar.visibility == View.VISIBLE) {
                keysBar.visibility = View.GONE
                releaseMods()
                imm.hideSoftInputFromWindow(hiddenInput.windowToken, 0)
            } else {
                keysBar.visibility = View.VISIBLE
                hiddenInput.requestFocus()
                imm.showSoftInput(hiddenInput, InputMethodManager.SHOW_IMPLICIT)
            }
        }
        findViewById<Button>(R.id.btnScreenshot).setOnClickListener { saveScreenshot() }
        findViewById<Button>(R.id.btnDisconnect).setOnClickListener {
            terminal = true
            Device.blockAutoConnect(this, 60_000)  // kompyuter darhol qayta ulab qo'ymasin
            finish()
        }

        setupTouchpadButtons()
        setupKeyboardCapture()
        setupPcKeys()

        client = StreamClient(this)
        showStatus("Ulanmoqda…")
        connectNow()
        handler.postDelayed(watchdog, 2000)
    }

    // --- Ulanish: ruxsat, fon/old, avtomatik qayta ulanish -------------
    private fun connectNow() {
        if (terminal || isFinishing) return
        val dev = Device.id(this)
        val name = Device.name()
        if (mode == "relay") {
            client.connect(
                "$relayUrl/relay/viewer",
                JSONObject().put("code", code).put("token", token)
                    .put("device_id", dev).put("device_name", name).toString(),
            )
        } else {
            client.connect(
                "ws://$lanHost:$lanPort",
                JSONObject().put("t", "viewer_hello").put("device_id", dev).put("device_name", name).toString(),
            )
        }
    }

    private fun handleControl(o: JSONObject) {
        lastRxMs = System.currentTimeMillis()
        when (o.optString("t")) {
            "waiting_approval" -> showStatus("Kompyuterda ruxsat kutilmoqda…")
            "approved" -> {
                approvedOnce = true
                attempt = 0
                trustUntilMs = if (o.isNull("until")) 0L else (o.optDouble("until") * 1000).toLong()
                hideStatus()
                stopLanSearch()
                if (!visible) client.send(PAUSE)
            }
            "hello" -> title = "Remote ${o.optInt("w")}x${o.optInt("h")} @${o.optInt("fps")}fps"
            "rejected" -> end("Kompyuter ulanishni rad etdi")
            "expired" -> end("Ruxsat muddati tugadi")
            "kicked" -> end("Kompyuter ulanishni uzdi")
            "busy" -> end("Kompyuter band: boshqa telefon ulangan")
            "error" -> when (o.optString("code")) {
                // kompyuter qayta yoqilayotgan bo'lishi mumkin — ilgari ulangan bo'lsak kutamiz
                "not_found" -> if (approvedOnce) scheduleReconnect()
                               else end("Kompyuter topilmadi. Kodni tekshiring")
                "busy" -> end("Kompyuter band: boshqa telefon ulangan")
                "unauthorized" -> end("Kirish tasdiqlanmadi. Qayta kiring")
                else -> end("Xato: ${o.optString("code")}")
            }
        }
    }

    private fun scheduleReconnect() {
        if (terminal || isFinishing || reconnectPending) return
        if (trustUntilMs > 0 && System.currentTimeMillis() > trustUntilMs) {
            end("Ruxsat muddati tugadi")
            return
        }
        if (!approvedOnce && attempt >= 5) {
            end(if (mode == "relay") "Ulanib bo'lmadi. Internet va kodni tekshiring" else "Kompyuterga ulanib bo'lmadi")
            return
        }
        clearModsUi()
        showStatus(if (approvedOnce) "Aloqa uzildi — kompyuter kutilmoqda…" else "Ulanmoqda…")
        if (mode == "lan" && approvedOnce) startLanSearch()  // kompyuter IP'si o'zgargan bo'lishi mumkin
        if (!visible) return  // fonda urinmaymiz — ilovaga qaytganda davom etadi
        reconnectPending = true
        val delay = RETRY_DELAYS[minOf(attempt, RETRY_DELAYS.size - 1)]
        attempt++
        handler.postDelayed({
            reconnectPending = false
            if (!client.isActive) connectNow()
        }, delay)
    }

    /** Socket "tirik" ko'rinsa ham kadr kelmay qolsa (fonda muzlatilgan jarayon) — qayta ulanamiz. */
    private val watchdog = object : Runnable {
        override fun run() {
            if (terminal) return
            if (visible && approvedOnce && client.isOpen && statusView.visibility != View.VISIBLE &&
                System.currentTimeMillis() - lastRxMs > 6000
            ) {
                client.disconnect()
                attempt = 0
                scheduleReconnect()
            }
            handler.postDelayed(this, 2000)
        }
    }

    private fun startLanSearch() {
        if (lanPresence != null) return
        lanPresence = LanPresence(this, true) { host, port, _ ->
            runOnUiThread {
                if (terminal || client.isOpen) return@runOnUiThread
                lanHost = host
                lanPort = port
                attempt = 0
                connectNow()
            }
        }.also { it.start() }
    }

    private fun stopLanSearch() {
        lanPresence?.stop()
        lanPresence = null
    }

    private fun showStatus(text: String) {
        statusView.text = text
        statusView.visibility = View.VISIBLE
    }

    private fun hideStatus() {
        statusView.visibility = View.GONE
    }

    private fun end(message: String) {
        if (terminal && isFinishing) return
        terminal = true
        handler.removeCallbacksAndMessages(null)
        stopLanSearch()
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        finish()
    }

    override fun onStart() {
        super.onStart()
        visible = true
        if (terminal) return
        if (client.isOpen) {
            lastRxMs = System.currentTimeMillis()  // watchdog kadrlar qayta kelishini kutsin
            client.send(RESUME)
        } else if (!client.isActive) {
            attempt = 0
            scheduleReconnect()
        }
    }

    override fun onStop() {
        super.onStop()
        visible = false
        stopGyro()
        if (client.isOpen) client.send(PAUSE)  // fonda kadr kerak emas (trafik/batareya)
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
                    // Modifikator yoniq bo'lsa harf fizik tugma sifatida ketadi: unicode matn
                    // Ctrl/Alt/Win bilan ishlamaydi (Ctrl+C, Win+R uchun KeyC/KeyR kerak).
                    val code = if (heldMods.isNotEmpty() && added.length == 1) charToCode(added[0]) else null
                    if (code != null) {
                        pressKey(code)
                    } else {
                        client.send(JSONObject().put("t", "text").put("value", added).toString())
                        releaseMods()
                    }
                }
            }
            override fun afterTextChanged(s: Editable?) {
                if ((s?.length ?: 0) > 32) s?.clear()
            }
        })
        hiddenInput.setOnKeyListener { _, keyCode, event ->
            if (event.action == KeyEvent.ACTION_DOWN) {
                when (keyCode) {
                    KeyEvent.KEYCODE_DEL -> { pressKey("Backspace"); return@setOnKeyListener true }
                    KeyEvent.KEYCODE_ENTER -> { pressKey("Enter"); return@setOnKeyListener true }
                }
            }
            false
        }
    }

    // --- Kompyuter tugmalari paneli -----------------------------------
    // Tugma guruhlari: [Esc..Del], [strelkalar, Home..PgDn], [F1-F12]. Qatorlarga layoutPcKeys() joylaydi.
    private val keyGroups = ArrayList<List<MaterialButton>>()

    private fun setupPcKeys() {
        fun key(label: String, onClick: (MaterialButton) -> Unit): MaterialButton {
            val b = MaterialButton(this)
            b.text = label
            b.isAllCaps = false
            b.letterSpacing = 0f
            b.maxLines = 1
            b.minWidth = 0
            b.minimumWidth = 0
            b.minHeight = 0
            b.minimumHeight = 0
            b.insetTop = 0
            b.insetBottom = 0
            b.cornerRadius = dp(6)
            b.setPadding(0, 0, 0, 0)
            b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            b.backgroundTintList = ColorStateList.valueOf(KEY_COLOR)
            b.setOnClickListener { onClick(b) }
            return b
        }
        val main = ArrayList<MaterialButton>()
        main += key("Esc") { pressKey("Escape") }
        main += key("Tab") { pressKey("Tab") }
        for ((label, code) in MOD_KEYS) main += key(label) { toggleMod(code, it) }
        main += key("Del") { pressKey("Delete") }
        keyGroups.add(main)
        keyGroups.add(NAV_KEYS.map { (label, code) -> key(label) { pressKey(code) } })
        keyGroups.add((1..12).map { i -> key("F$i") { pressKey("F$i") } })
        layoutPcKeys()
    }

    /** Hamma tugma ekranga sig'sin: yotiq ekranda 2 qator, tik ekranda 3 qator, teng enli tugmalar. */
    private fun layoutPcKeys() {
        keysBar.removeAllViews()
        for (group in keyGroups) for (b in group) (b.parent as? ViewGroup)?.removeView(b)
        val landscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
        val rows = if (landscape) listOf(keyGroups[0] + keyGroups[1], keyGroups[2]) else keyGroups
        for (keys in rows) {
            val row = LinearLayout(this)
            row.orientation = LinearLayout.HORIZONTAL
            for (b in keys) {
                val lp = LinearLayout.LayoutParams(0, dp(34), 1f)
                lp.setMargins(dp(2), dp(2), dp(2), dp(2))
                row.addView(b, lp)
            }
            keysBar.addView(
                row,
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT),
            )
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        layoutPcKeys()  // telefon burilganda qatorlarni qayta joylash
    }

    /** Modifikatorni yoqadi/o'chiradi. Yolg'iz Win yoqib-o'chirilsa — Start menyu ochiladi. */
    private fun toggleMod(code: String, b: MaterialButton) {
        if (heldMods.remove(code) != null) {
            keyEvent(code, false)
            b.backgroundTintList = ColorStateList.valueOf(KEY_COLOR)
        } else {
            heldMods[code] = b
            keyEvent(code, true)
            b.backgroundTintList = ColorStateList.valueOf(MOD_ON_COLOR)
        }
    }

    /** Oddiy tugma: bosib qo'yib yuboradi, keyin yoniq modifikatorlarni bo'shatadi. */
    private fun pressKey(code: String) {
        keyEvent(code, true)
        keyEvent(code, false)
        releaseMods()
    }

    private fun releaseMods() {
        for ((code, b) in heldMods.entries.reversed()) {
            keyEvent(code, false)
            b.backgroundTintList = ColorStateList.valueOf(KEY_COLOR)
        }
        heldMods.clear()
    }

    /** Aloqa uzilganda: kompyuter tugmalarni o'zi qo'yib yuboradi, biz faqat ko'rinishni tozalaymiz. */
    private fun clearModsUi() {
        for (b in heldMods.values) b.backgroundTintList = ColorStateList.valueOf(KEY_COLOR)
        heldMods.clear()
    }

    private fun keyEvent(code: String, down: Boolean) {
        client.send(JSONObject().put("t", "key").put("code", code).put("down", down).toString())
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    // --- Screenshot -> galereya ---------------------------------------
    private fun saveScreenshot() {
        val data = lastJpeg
        if (data == null) {
            Toast.makeText(this, "Hali ekran kelmadi", Toast.LENGTH_SHORT).show()
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
            != PackageManager.PERMISSION_GRANTED
        ) {
            pendingShot = data
            ActivityCompat.requestPermissions(
                this, arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), REQ_STORAGE
            )
            return
        }
        writeScreenshot(data)
    }

    private fun writeScreenshot(data: ByteArray) {
        val name = "Remote_" + SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date()) + ".jpg"
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, name)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/RemoteViewer")
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                }
                val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                    ?: throw IOException("MediaStore")
                contentResolver.openOutputStream(uri)?.use { it.write(data) } ?: throw IOException("stream")
                values.clear()
                values.put(MediaStore.Images.Media.IS_PENDING, 0)
                contentResolver.update(uri, values, null, null)
            } else {
                @Suppress("DEPRECATION")
                val pictures = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                val dir = File(pictures, "RemoteViewer")
                dir.mkdirs()
                val f = File(dir, name)
                f.writeBytes(data)
                MediaScannerConnection.scanFile(this, arrayOf(f.absolutePath), arrayOf("image/jpeg"), null)
            }
            Toast.makeText(this, "Saqlandi: Galereya → RemoteViewer", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Saqlab bo'lmadi: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_STORAGE) return
        val data = pendingShot
        pendingShot = null
        if (data != null && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            writeScreenshot(data)
        } else {
            Toast.makeText(this, "Ruxsat berilmadi", Toast.LENGTH_SHORT).show()
        }
    }

    // --- StreamClient.Listener ----------------------------------------
    override fun onText(o: JSONObject) {
        runOnUiThread { handleControl(o) }
    }

    override fun onFrame(data: ByteArray) {
        lastRxMs = System.currentTimeMillis()
        lastJpeg = data
        val bmp = BitmapFactory.decodeByteArray(data, 0, data.size) ?: return
        view.setFrame(bmp)
    }

    override fun onClosed(reason: String) {
        runOnUiThread { scheduleReconnect() }  // ✕ / rad / muddat tugashi bo'lmasa — qayta ulanamiz
    }

    override fun onDestroy() {
        super.onDestroy()
        terminal = true
        handler.removeCallbacksAndMessages(null)
        stopLanSearch()
        stopGyro()
        releaseMods()  // kompyuterda Ctrl/Alt/Win bosilib qolmasin
        client.shutdown()
    }

    companion object {
        private const val REQ_STORAGE = 41
        private val PAUSE = JSONObject().put("t", "pause").toString()
        private val RESUME = JSONObject().put("t", "resume").toString()
        private val RETRY_DELAYS = longArrayOf(300, 1000, 2000, 3000, 5000)
        private val KEY_COLOR = Color.parseColor("#37474F")
        private val MOD_ON_COLOR = Color.parseColor("#F57C00")  // yoniq modifikator

        private val MOD_KEYS = listOf(
            "Ctrl" to "ControlLeft", "Alt" to "AltLeft", "Shift" to "ShiftLeft", "Win" to "MetaLeft",
        )
        private val NAV_KEYS = listOf(
            "←" to "ArrowLeft", "↑" to "ArrowUp", "↓" to "ArrowDown", "→" to "ArrowRight",
            "Home" to "Home", "End" to "End", "PgUp" to "PageUp", "PgDn" to "PageDown",
        )

        /** Belgi -> W3C fizik tugma kodi (modifikator bilan yuborish uchun). Topilmasa null. */
        private fun charToCode(ch: Char): String? {
            val c = ch.lowercaseChar()
            return when (c) {
                in 'a'..'z' -> "Key" + c.uppercaseChar()
                in '0'..'9' -> "Digit$c"
                ' ' -> "Space"
                '-' -> "Minus"
                '=' -> "Equal"
                '[' -> "BracketLeft"
                ']' -> "BracketRight"
                '\\' -> "Backslash"
                ';' -> "Semicolon"
                '\'' -> "Quote"
                '`' -> "Backquote"
                ',' -> "Comma"
                '.' -> "Period"
                '/' -> "Slash"
                else -> null
            }
        }
    }
}
