package com.remoteviewer.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * Asosiy ekran (login'dan keyin). Ikki yo'l:
 *  - Internet: kompyuterdagi doimiy KODni kiritish (oxirgisi eslab qolinadi). Server manzili Config'da.
 *  - Lokal tarmoq (Wi-Fi / USB modem): ekran ochiq ekan, telefon o'zini e'lon qiladi; kompyuterdagi
 *    "Tarmoqdagi telefonlar" ro'yxatidan tanlansa taklif keladi va TELEFON HAM ruxsat + muddat so'raydi.
 *    Ishonchli kompyuterning takliflari so'rovsiz qabul qilinadi.
 * Ilova yopilib qayta ochilsa — oxirgi internet ulanishi avtomatik tiklanadi (✕ bilan uzilmagan bo'lsa).
 */
class ConnectActivity : AppCompatActivity() {
    private var presence: LanPresence? = null
    private var launching = false
    private var dialog: AlertDialog? = null
    private var resumeCode: String? = null  // ilova qayta ochilganda tiklanadigan internet ulanishi
    private lateinit var lanHost: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_connect)
        val prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        val code = findViewById<EditText>(R.id.code)
        lanHost = findViewById(R.id.lanHost)
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
            launchRelay(c)
        }

        findViewById<Button>(R.id.btnLogout).setOnClickListener {
            prefs.edit().remove("token").remove(ViewerActivity.PREF_RESUME_CODE).apply()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }

        // Ilova qayta ochildi: oxirgi internet ulanishini davom ettiramiz (onResume'da)
        if (savedInstanceState == null && Device.autoConnectAllowed(this)) {
            resumeCode = prefs.getString(ViewerActivity.PREF_RESUME_CODE, null)
        }
    }

    override fun onResume() {
        super.onResume()
        launching = false
        refreshTrusted()
        resumeCode?.let {
            resumeCode = null
            launchRelay(it, resume = true)
            return
        }
        presence = LanPresence(
            this, Device.autoConnectAllowed(this),
            onInvite = { inv -> runOnUiThread { onInvite(inv) } },
            onHost = { name ->
                runOnUiThread {
                    lanHost.text = "Kompyuter topildi: $name — unda «Ulash» bosing"
                    lanHost.visibility = View.VISIBLE
                }
            },
        ).also { it.start() }
    }

    override fun onPause() {
        super.onPause()
        presence?.stop()
        presence = null
        dialog?.dismiss()
        dialog = null
    }

    /** Kompyuter ulanishni taklif qildi: ishonchli bo'lsa darhol, aks holda ruxsat va muddat so'raymiz. */
    private fun onInvite(inv: LanPresence.Invite) {
        if (launching || isFinishing || dialog != null) return
        if (TrustedPcs.get(this, inv.pcId) != null) {
            launchLan(inv)
            return
        }
        val labels = TrustedPcs.DURATIONS.map { it.first }.toTypedArray()
        var choice = 1  // "1 soat"
        dialog = AlertDialog.Builder(this)
            .setTitle("«${inv.name}» ulanmoqchi")
            .setSingleChoiceItems(labels, choice) { _, which -> choice = which }
            .setPositiveButton("Qabul qilish") { _, _ ->
                TrustedPcs.grant(this, inv.pcId, inv.name, TrustedPcs.DURATIONS[choice].second)
                launchLan(inv)
            }
            .setNegativeButton("Rad etish", null)
            .setOnDismissListener { dialog = null }
            .show()
    }

    private fun refreshTrusted() {
        val box = findViewById<LinearLayout>(R.id.trustedBox)
        box.removeAllViews()
        val items = TrustedPcs.list(this)
        findViewById<View>(R.id.trustedTitle).visibility = if (items.isEmpty()) View.GONE else View.VISIBLE
        for (e in items) {
            val row = LinearLayout(this)
            row.orientation = LinearLayout.HORIZONTAL
            row.gravity = Gravity.CENTER_VERTICAL
            val t = TextView(this)
            t.text = "${e.name}\n${TrustedPcs.describe(e)}"
            row.addView(t, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            val b = Button(this, null, android.R.attr.borderlessButtonStyle)
            b.text = "O'chirish"
            b.setOnClickListener {
                TrustedPcs.revoke(this, e.pcId)
                refreshTrusted()
            }
            row.addView(b)
            box.addView(row)
        }
    }

    /** [resume] — avvalgi ulanishni tiklash: kompyuter hali yoqilmagan bo'lsa ham kutib turadi. */
    private fun launchRelay(code: String, resume: Boolean = false) {
        val prefs = getSharedPreferences("rv", Context.MODE_PRIVATE)
        val i = Intent(this, ViewerActivity::class.java)
        i.putExtra("mode", "relay")
        i.putExtra("relay", Config.backendWs)
        i.putExtra("code", code)
        i.putExtra("token", prefs.getString("token", "") ?: "")
        i.putExtra("resume", resume)
        launch(i)
    }

    private fun launchLan(inv: LanPresence.Invite) {
        val i = Intent(this, ViewerActivity::class.java)
        i.putExtra("mode", "lan")
        i.putExtra("host", inv.host)
        i.putExtra("port", inv.port)
        i.putExtra("pc_id", inv.pcId)
        launch(i)
    }

    private fun launch(i: Intent) {
        if (launching) return
        launching = true
        startActivity(i)
    }
}
