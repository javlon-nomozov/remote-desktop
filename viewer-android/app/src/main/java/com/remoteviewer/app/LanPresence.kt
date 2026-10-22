package com.remoteviewer.app

import android.content.Context
import android.net.wifi.WifiManager
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface

/**
 * Lokal tarmoqda "men shu yerdaman" (internet kerak emas).
 *
 * Har 2 soniyada UDP broadcast yuboradi: {"t":"rv_phone", device_id, device_name, auto} ->
 * kompyuter UDP 47866. Har bir tarmoq interfeysining broadcast manziliga alohida yuboriladi:
 * Wi-Fi, telefon hotspoti, USB modem (USB tethering). Kompyuter telefonni ro'yxatda ko'rsatadi;
 * tanlansa (yoki telefon ishonchli bo'lsa) UDP 47867 ga taklif keladi:
 * {"t":"rv_invite", host, port, name} -> [onInvite] (fon thread'ida chaqiriladi).
 */
class LanPresence(
    private val ctx: Context,
    private val auto: Boolean,
    private val onInvite: (host: String, port: Int, name: String) -> Unit,
) {
    @Volatile private var running = false
    @Volatile private var recvSocket: DatagramSocket? = null
    private var multicastLock: WifiManager.MulticastLock? = null

    fun start() {
        if (running) return
        running = true
        try {
            // ba'zi telefonlar Wi-Fi'da broadcast paketlarni filtrlaydi — lock bilan ochamiz
            val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            multicastLock = wifi.createMulticastLock("remoteviewer").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (_: Exception) {
        }
        Thread({ receiveLoop() }, "lan-invite").start()
        Thread({ announceLoop() }, "lan-announce").start()
    }

    fun stop() {
        running = false
        try {
            recvSocket?.close()
        } catch (_: Exception) {
        }
        try {
            multicastLock?.release()
        } catch (_: Exception) {
        }
        multicastLock = null
    }

    private fun announceLoop() {
        val msg = JSONObject()
            .put("t", "rv_phone")
            .put("device_id", Device.id(ctx))
            .put("device_name", Device.name())
            .put("auto", auto)
            .toString().toByteArray()
        try {
            DatagramSocket().use { s ->
                s.broadcast = true
                while (running) {
                    for (addr in broadcastAddresses()) {
                        try {
                            s.send(DatagramPacket(msg, msg.size, addr, Config.LAN_DISCOVERY_PORT))
                        } catch (_: Exception) {
                        }
                    }
                    Thread.sleep(2000)
                }
            }
        } catch (_: Exception) {
        }
    }

    private fun broadcastAddresses(): Set<InetAddress> {
        val out = LinkedHashSet<InetAddress>()
        try {
            for (ni in NetworkInterface.getNetworkInterfaces()) {
                if (!ni.isUp || ni.isLoopback) continue
                for (ia in ni.interfaceAddresses) ia.broadcast?.let { out.add(it) }
            }
        } catch (_: Exception) {
        }
        try {
            out.add(InetAddress.getByName("255.255.255.255"))
        } catch (_: Exception) {
        }
        return out
    }

    private fun receiveLoop() {
        try {
            val s = DatagramSocket(null)
            s.reuseAddress = true
            s.bind(InetSocketAddress(Config.LAN_INVITE_PORT))
            recvSocket = s
            val buf = ByteArray(2048)
            while (running) {
                val p = DatagramPacket(buf, buf.size)
                s.receive(p)
                try {
                    val o = JSONObject(String(p.data, 0, p.length, Charsets.UTF_8))
                    if (o.optString("t") == "rv_invite" && o.optInt("port") > 0) {
                        val host = o.optString("host").ifEmpty { p.address.hostAddress ?: "" }
                        if (host.isNotEmpty()) onInvite(host, o.optInt("port"), o.optString("name"))
                    }
                } catch (_: Exception) {
                }
            }
        } catch (_: Exception) {
        } finally {
            try {
                recvSocket?.close()
            } catch (_: Exception) {
            }
        }
    }
}
