package com.remoteviewer.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import java.net.Inet4Address
import java.net.InetAddress

/**
 * Telefonning lokal tarmoqlari (Wi-Fi, hotspot va h.k.).
 *
 * Android'da Wi-Fi'da internet bo'lmasa (yoki "internetsiz" deb belgilansa) ilova trafigi standart
 * bo'yicha mobil internetga ketadi va lokal manzilga (192.168.x.x) yetib bormaydi. Shuning uchun
 * lokal kompyuterga boradigan socketlarni aynan o'sha manzil turgan tarmoqqa bog'laymiz.
 * (USB modem interfeysi Android "Network" emas — u tizimning lokal yo'nalishi orqali ishlaydi.)
 */
object LanNet {
    class Subnet(val network: Network, private val address: Inet4Address, private val prefix: Int) {
        private val mask: Int = if (prefix <= 0) 0 else (-1 shl (32 - prefix))
        val broadcast: InetAddress get() = toAddr(toInt(address) or mask.inv())
        fun contains(host: InetAddress): Boolean =
            host is Inet4Address && (toInt(host) and mask) == (toInt(address) and mask)
    }

    @Suppress("DEPRECATION")
    fun subnets(ctx: Context): List<Subnet> {
        val out = ArrayList<Subnet>()
        try {
            val cm = ctx.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            for (n in cm.allNetworks) {
                val lp = cm.getLinkProperties(n) ?: continue
                for (la in lp.linkAddresses) {
                    val a = la.address
                    if (a is Inet4Address && !a.isLoopbackAddress && !a.isLinkLocalAddress) {
                        out.add(Subnet(n, a, la.prefixLength))
                    }
                }
            }
        } catch (_: Exception) {
        }
        return out
    }

    /** `host` (IP) qaysi tarmoqda bo'lsa o'sha Network; topilmasa null (tizim yo'nalishi). */
    fun networkFor(ctx: Context, host: String): Network? = try {
        val addr = InetAddress.getByName(host)
        subnets(ctx).firstOrNull { it.contains(addr) }?.network
    } catch (_: Exception) {
        null
    }

    private fun toInt(a: InetAddress): Int {
        val b = a.address
        return ((b[0].toInt() and 0xff) shl 24) or ((b[1].toInt() and 0xff) shl 16) or
            ((b[2].toInt() and 0xff) shl 8) or (b[3].toInt() and 0xff)
    }

    private fun toAddr(v: Int): InetAddress = InetAddress.getByAddress(
        byteArrayOf((v ushr 24).toByte(), (v ushr 16).toByte(), (v ushr 8).toByte(), v.toByte())
    )
}
