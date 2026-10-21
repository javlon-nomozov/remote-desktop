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
 * Server bilan WebSocket (WS+JPEG MVP protokoli):
 *   server -> bu: matn JSON {"t":"hello",...}, keyin binary JPEG kadrlar
 *   bu -> server: matn JSON input hodisalari (PROTOCOL.md §2)
 */
class StreamClient(
    private val host: String,
    private val port: Int,
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
        val req = Request.Builder().url("ws://$host:$port").build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val o = JSONObject(text)
                    if (o.optString("t") == "hello") {
                        listener.onHello(o.optInt("w"), o.optInt("h"), o.optInt("fps"))
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

    /** Input hodisasini (JSON satr) serverga yuboradi. */
    fun send(json: String) {
        ws?.send(json)
    }

    fun close() {
        ws?.close(1000, "bye")
        client.dispatcher.executorService.shutdown()
    }
}
