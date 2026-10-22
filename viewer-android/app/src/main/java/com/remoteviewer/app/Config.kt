package com.remoteviewer.app

/**
 * Ilova sozlamalari. Foydalanuvchi server manzilini kiritmaydi — u shu yerda belgilangan.
 * Backend'ni Railway'ga deploy qilgach, BACKEND_HTTP ni o'sha manzilga o'zgartiring.
 */
object Config {
    const val BOT_USERNAME = "Sharescreen_app_bot"

    // Backend (Render). Login (/auth/poll) HTTP; relay WS shu manzildan olinadi.
    const val BACKEND_HTTP = "https://remote-desktop-backend-1lfo.onrender.com"

    val backendWs: String
        get() = BACKEND_HTTP.replace("https://", "wss://").replace("http://", "ws://")
}
