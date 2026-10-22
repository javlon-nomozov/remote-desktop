package com.remoteviewer.app

/**
 * Ilova sozlamalari. Foydalanuvchi server manzilini kiritmaydi — u shu yerda belgilangan.
 * Backend'ni Railway'ga deploy qilgach, BACKEND_HTTP ni o'sha manzilga o'zgartiring.
 */
object Config {
    const val BOT_USERNAME = "Sharescreen_app_bot"

    // MUHIM: Railway deploy'dan keyin shu yerni o'zgartiring (masalan https://xxx.up.railway.app)
    const val BACKEND_HTTP = "https://change-me.up.railway.app"

    val backendWs: String
        get() = BACKEND_HTTP.replace("https://", "wss://").replace("http://", "ws://")
}
