package com.remoteviewer.app

/**
 * Ilova sozlamalari. Foydalanuvchi server manzilini kiritmaydi — u shu yerda belgilangan.
 */
object Config {
    const val BOT_USERNAME = "Sharescreen_app_bot"

    // Backend (Railway). Login (/auth/poll) HTTP; relay WS shu manzildan olinadi.
    const val BACKEND_HTTP = "https://app-production-207d7.up.railway.app"

    val backendWs: String
        get() = BACKEND_HTTP.replace("https://", "wss://").replace("http://", "ws://")

    // Lokal tarmoq (Wi-Fi / USB modem): telefon o'zini e'lon qiladi, kompyuter taklif yuboradi.
    const val LAN_DISCOVERY_PORT = 47866  // telefon -> kompyuter (broadcast)
    const val LAN_INVITE_PORT = 47867     // kompyuter -> telefon (taklif)
}
