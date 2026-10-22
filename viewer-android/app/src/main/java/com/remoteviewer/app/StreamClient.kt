package com.remoteviewer.app

import android.net.Network
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * WebSocket klient, qayta ulana oladi. Ikki yo'l:
 *  - Relay (internet, kod): url = <backend>/relay/viewer, handshake = {code, token, device_id, device_name}
 *  - LAN (Wi-Fi / USB): url = ws://<kompyuter IP>:<port>, handshake = {"t":"viewer_hello", device_id, device_name}
 * Handshake ochilishi bilan yuboriladi.
 *
 * Qabul: matn JSON (waiting_approval, approved, hello, rejected, ...) va binary JPEG kadrlar.
 * Har bir [connect] yangi "avlod": eski socketning kech kelgan callback'lari e'tiborsiz qoladi.
 */
class StreamClient(private val listener: Listener) {
    interface Listener {
        fun onText(o: JSONObject)
        fun onFrame(data: ByteArray)
        fun onClosed(reason: String)
    }

    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var ws: WebSocket? = null
    @Volatile private var gen = 0

    /** Socket ochiq (yuborish mumkin). */
    @Volatile var isOpen = false
        private set

    /** Ulanayotgan yoki ochiq (qayta ulanish shart emas). */
    @Volatile var isActive = false
        private set

    /** [network] — lokal kompyuter uchun socket shu tarmoqqa bog'lanadi (Wi-Fi internetsiz bo'lsa ham). */
    @Synchronized
    fun connect(url: String, handshake: String, network: Network? = null) {
        ws?.cancel()
        isOpen = false
        isActive = true
        val my = ++gen
        val c = if (network != null) client.newBuilder().socketFactory(network.socketFactory).build() else client
        ws = c.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (my != gen) return
                isOpen = true
                webSocket.send(handshake)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (my != gen) return
                try {
                    listener.onText(JSONObject(text))
                } catch (_: Exception) {
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                if (my == gen) listener.onFrame(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (my != gen) return
                isOpen = false
                isActive = false
                listener.onClosed(t.message ?: "ulanish uzildi")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (my != gen) return
                isOpen = false
                isActive = false
                listener.onClosed(reason)
            }
        })
    }

    fun send(json: String) {
        if (isOpen) ws?.send(json)
    }

    /** Joriy socketni yopadi; uning callback'lari endi chaqirilmaydi. */
    @Synchronized
    fun disconnect() {
        gen++
        isOpen = false
        isActive = false
        ws?.close(1000, "bye")
        ws = null
    }

    fun shutdown() {
        disconnect()
        client.dispatcher.executorService.shutdown()
    }
}
