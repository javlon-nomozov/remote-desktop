package com.remoteviewer.app

import android.content.Context
import org.json.JSONObject

/**
 * Telefon ruxsat bergan (ishonchli) kompyuterlar: kompyuter lokal tarmoqdan ulanish taklif qilganda telefon
 * ham ruxsat va muddat so'raydi; muddat ichida shu kompyuterning takliflari so'rovsiz qabul qilinadi.
 * Kalit — kompyuterning doimiy ID'si (pc_id = uning internet kodi).
 */
object TrustedPcs {
    class Entry(val pcId: String, val name: String, val untilMs: Long)  // untilMs = 0 — cheksiz

    /** Nom -> soniya (null = cheksiz). Kompyuterdagi ruxsat oynasi bilan bir xil. */
    val DURATIONS: List<Pair<String, Long?>> = listOf(
        "30 daqiqa" to 1800L, "1 soat" to 3600L, "1 kun" to 86400L, "Cheksiz" to null,
    )

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("rv_trusted_pcs", Context.MODE_PRIVATE)

    fun list(ctx: Context): List<Entry> {
        val p = prefs(ctx)
        val now = System.currentTimeMillis()
        val out = ArrayList<Entry>()
        val dead = ArrayList<String>()
        for ((key, value) in p.all) {
            try {
                val o = JSONObject(value as String)
                val e = Entry(key, o.optString("name"), o.optLong("until"))
                if (e.untilMs != 0L && e.untilMs <= now) dead.add(key) else out.add(e)
            } catch (_: Exception) {
                dead.add(key)
            }
        }
        if (dead.isNotEmpty()) p.edit().apply { dead.forEach { remove(it) } }.apply()
        return out.sortedBy { it.name }
    }

    fun get(ctx: Context, pcId: String): Entry? = list(ctx).firstOrNull { it.pcId == pcId }

    fun grant(ctx: Context, pcId: String, name: String, seconds: Long?) {
        val until = if (seconds == null) 0L else System.currentTimeMillis() + seconds * 1000
        prefs(ctx).edit().putString(pcId, JSONObject().put("name", name).put("until", until).toString()).apply()
    }

    fun revoke(ctx: Context, pcId: String) {
        prefs(ctx).edit().remove(pcId).apply()
    }

    fun describe(e: Entry): String {
        if (e.untilMs == 0L) return "cheksiz"
        val left = (e.untilMs - System.currentTimeMillis()) / 1000
        return when {
            left < 3600 -> "${maxOf(1, left / 60)} daq qoldi"
            left < 86400 -> "${left / 3600} soat ${left % 3600 / 60} daq qoldi"
            else -> java.text.SimpleDateFormat("dd.MM HH:mm", java.util.Locale.US)
                .format(java.util.Date(e.untilMs)) + " gacha"
        }
    }
}
