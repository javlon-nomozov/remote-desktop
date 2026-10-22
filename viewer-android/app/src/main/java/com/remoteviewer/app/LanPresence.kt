package com.remoteviewer.app

import android.content.Context
import android.net.Network
import android.net.wifi.WifiManager
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.util.concurrent.ConcurrentHashMap

/**
 * Lokal tarmoqda "men shu yerdaman" (internet kerak emas).
 *
 * Har 2 soniyada {"t":"rv_phone", device_id, device_name, auto} -> kompyuter UDP 47866:
 *  - har bir Android tarmog'ining (Wi-Fi, hotspot) broadcast manziliga — socket o'sha tarmoqqa bog'lanadi;
 *  - har bir interfeysning (USB modem ham) broadcast manziliga va 255.255.255.255 ga;
 *  - mayog'i eshitilgan kompyuterlarga to'g'ridan-to'g'ri (unicast).
 * UDP 47867 da kompyuterdan keladi:
 *  - {"t":"rv_host", name, pc_id, port} — mayoq: darhol unicast javob beramiz ([onHost]);
 *  - {"t":"rv_invite", host, port, name, pc_id} — ulanish taklifi ([onInvite]).
 * Callback'lar fon thread'ida chaqiriladi.
 */
class LanPresence(
    private val ctx: Context,
    private val auto: Boolean,
    private val onInvite: (Invite) -> Unit,
    private val onHost: ((name: String) -> Unit)? = null,
) {
    class Invite(val host: String, val port: Int, val name: String, val pcId: String)

    @Volatile private var running = false
    @Volatile private var recvSocket: DatagramSocket? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private val knownHosts = ConcurrentHashMap<String, Long>()  // kompyuter IP -> oxirgi mayoq vaqti

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

    private val message: ByteArray by lazy {
        JSONObject()
            .put("t", "rv_phone")
            .put("device_id", Device.id(ctx))
            .put("device_name", Device.name())
            .put("auto", auto)
            .toString().toByteArray()
    }

    private fun send(addr: InetAddress, network: Network?) {
        try {
            DatagramSocket().use { s ->
                s.broadcast = true
                network?.bindSocket(s)
                s.send(DatagramPacket(message, message.size, addr, Config.LAN_DISCOVERY_PORT))
            }
        } catch (_: Exception) {
        }
    }

    private fun announceLoop() {
        while (running) {
            for (sn in LanNet.subnets(ctx)) send(sn.broadcast, sn.network)
            for (addr in interfaceBroadcasts()) send(addr, null)
            val now = System.currentTimeMillis()
            for ((ip, seen) in knownHosts) {
                if (now - seen > 30_000) {
                    knownHosts.remove(ip)
                    continue
                }
                unicast(ip)
            }
            try {
                Thread.sleep(2000)
            } catch (_: InterruptedException) {
                break
            }
        }
    }

    private fun unicast(ip: String) {
        try {
            send(InetAddress.getByName(ip), LanNet.networkFor(ctx, ip))
        } catch (_: Exception) {
        }
    }

    private fun interfaceBroadcasts(): Set<InetAddress> {
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
                val from = p.address.hostAddress ?: continue
                try {
                    val o = JSONObject(String(p.data, 0, p.length, Charsets.UTF_8))
                    when (o.optString("t")) {
                        "rv_host" -> {
                            val fresh = knownHosts.put(from, System.currentTimeMillis()) == null
                            if (fresh) unicast(from)  // darhol javob — kompyuter ro'yxatida tez chiqamiz
                            onHost?.invoke(o.optString("name"))
                        }
                        "rv_invite" -> if (o.optInt("port") > 0) {
                            val host = o.optString("host").ifEmpty { from }
                            onInvite(Invite(host, o.optInt("port"), o.optString("name"),
                                o.optString("pc_id").ifEmpty { "ip:$host" }))
                        }
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
