package com.remoteviewer.app

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * WebSocket klient. Ikki rejim:
 *  - To'g'ridan-to'g'ri (LAN): url = ws://host:port, handshake = null.
 *  - Relay (unique kod): url = <backend>/relay/viewer, handshake = {"code":..,"token":..}
 *    (ochilishi bilan yuboriladi).
 *
 * Qabul: matn {"t":"hello"|"error"|...} va binary JPEG kadrlar.
 */
class StreamClient(
    private val url: String,
    private val handshake: String?,
    private val listener: Listener,
) {
    interface Listener {
        fun onHello(w: Int, h: Int, fps: Int)
        fun onFrame(data: ByteArray)
        fun onClosed(reason: String)
    }

    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var ws: WebSocket? = null

    fun connect() {
        val req = Request.Builder().url(url).build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (handshake != null) webSocket.send(handshake)  // relay: {code, token}
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val o = JSONObject(text)
                    when (o.optString("t")) {
                        "hello" -> listener.onHello(o.optInt("w"), o.optInt("h"), o.optInt("fps"))
                        "error" -> listener.onClosed("error:" + o.optString("code"))
                    }
                } catch (_: Exception) {
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                listener.onFrame(bytes.toByteArray())
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                listener.onClosed(t.message ?: "ulanish uzildi")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                listener.onClosed(reason)
            }
        })
    }

    fun send(json: String) {
        ws?.send(json)
    }

    fun close() {
        ws?.close(1000, "bye")
        client.dispatcher.executorService.shutdown()
    }
}
