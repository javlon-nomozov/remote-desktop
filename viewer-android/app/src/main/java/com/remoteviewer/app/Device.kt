package com.remoteviewer.app

import android.content.Context
import android.os.Build
import java.util.UUID

/**
 * Shu telefonning doimiy identifikatori va nomi. Kompyuter ruxsat berganda telefonni shu `id`
 * bo'yicha "ishonchli" ro'yxatda eslab qoladi; nom kompyuterdagi ro'yxat/so'rovda ko'rinadi.
 */
object Device {
    fun id(ctx: Context): String {
        val prefs = ctx.getSharedPreferences("rv", Context.MODE_PRIVATE)
        prefs.getString("device_id", null)?.let { return it }
        val id = UUID.randomUUID().toString().replace("-", "")
        prefs.edit().putString("device_id", id).apply()
        return id
    }

    fun name(): String {
        val maker = Build.MANUFACTURER.replaceFirstChar { it.uppercaseChar() }
        return if (Build.MODEL.startsWith(maker, ignoreCase = true)) Build.MODEL else "$maker ${Build.MODEL}"
    }

    /** Foydalanuvchi ✕ bilan uzgandan keyin bir muddat kompyuter avtomatik qayta ulamasin. */
    fun blockAutoConnect(ctx: Context, millis: Long) {
        ctx.getSharedPreferences("rv", Context.MODE_PRIVATE).edit()
            .putLong("auto_blocked_until", System.currentTimeMillis() + millis).apply()
    }

    fun autoConnectAllowed(ctx: Context): Boolean =
        System.currentTimeMillis() >= ctx.getSharedPreferences("rv", Context.MODE_PRIVATE)
            .getLong("auto_blocked_until", 0L)
}
