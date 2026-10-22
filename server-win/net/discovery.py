"""Lokal tarmoqdagi telefonlarni topish (UDP) — internet kerak emas.

Telefon (ilova ulanish sahifasida yoki qayta ulanishni kutayotganda) har 2 s broadcast yuboradi:
    {"t":"rv_phone","device_id":..,"device_name":..,"auto":true}   -> UDP 47866
(`auto`=false — telefonda foydalanuvchi o'zi uzgan: ishonchli bo'lsa ham avtomatik taklif qilinmaydi.)
Kompyuter ularni ro'yxatda ko'rsatadi. Tanlansa (yoki telefon ishonchli bo'lsa) telefonga taklif:
    {"t":"rv_invite","host":<kompyuter IP>,"port":<LAN port>,"name":<kompyuter nomi>}  -> telefon UDP 47867
Telefon taklifni olib `ws://host:port` ga ulanadi (net/stream_server.py).

Kompyuter ham har 2 s o'z tarmoqlarining har biriga mayoq yuboradi:
    {"t":"rv_host","name":..,"pc_id":..,"port":..}  -> telefon UDP 47867
Telefon unga unicast `rv_phone` bilan javob beradi — broadcast bir tomonga to'silgan tarmoqlarda ham
telefon ro'yxatga tushadi. `pc_id` (doimiy relay kodi) telefonda "ishonchli kompyuter"ni eslab qolish uchun.

Bitta Wi-Fi, telefon hotspoti yoki USB modem (USB tethering) — hammasi oddiy lokal tarmoq.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
import threading
import time
from typing import Callable, Optional

DISCOVERY_PORT = 47866
INVITE_PORT = 47867
SEEN_TTL = 6.0  # shuncha soniya ko'rinmasa ro'yxatdan chiqadi
BEACON_EVERY = 2.0


def local_ip_for(peer_ip: str) -> str:
    """Shu telefonga yetib boradigan interfeysdagi kompyuter IP'si (paket yuborilmaydi)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((peer_ip, INVITE_PORT))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def lan_ips() -> list[str]:
    """Kompyuterning lokal IPv4 manzillari (GUI'da ko'rsatish uchun)."""
    out: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in out:
                out.append(ip)
    except OSError:
        pass
    return out


def local_ipv4_networks() -> list[ipaddress.IPv4Interface]:
    """Kompyuterning lokal IPv4 manzillari maska bilan (har bir tarmoqqa alohida mayoq uchun).
    Windows'da 255.255.255.255 faqat bitta interfeysdan chiqadi — shuning uchun har biriga yo'naltirilgan
    broadcast kerak. PowerShell bo'lmasa /24 deb faraz qilinadi."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | ?{ $_.IPAddress -notlike '127.*' -and "
             "$_.IPAddress -notlike '169.254.*' } | %{ $_.IPAddress + '/' + $_.PrefixLength }"],
            capture_output=True, text=True, timeout=20, creationflags=0x08000000,
        ).stdout
        nets = [ipaddress.IPv4Interface(line.strip()) for line in out.splitlines() if line.strip()]
        if nets:
            return nets
    except Exception:
        pass
    return [ipaddress.IPv4Interface(f"{ip}/24") for ip in lan_ips()]


class Discovery:
    def __init__(
        self,
        on_phone: Optional[Callable[[str, str, str, bool], None]] = None,
        pc_id: str = "",
        port_fn: Callable[[], int] = lambda: 0,
    ) -> None:
        self.on_phone = on_phone  # (device_id, device_name, ip, auto) — har bir signalda
        self.pc_id = pc_id
        self.port_fn = port_fn  # LAN ws port (band bo'lsa boshqasi tanlanadi)
        self.name = socket.gethostname()
        self._phones: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None

    def phones(self) -> list[dict]:
        """Hozir ko'rinib turgan telefonlar: [{device_id, name, ip, seen}]."""
        now = time.time()
        with self._lock:
            return [dict(p, device_id=k) for k, p in self._phones.items() if now - p["seen"] < SEEN_TTL]

    def invite(self, device_id: str, port: int) -> bool:
        with self._lock:
            p = self._phones.get(device_id)
        if p is None:
            return False
        host = local_ip_for(p["ip"])
        if not host:
            return False
        msg = json.dumps({"t": "rv_invite", "host": host, "port": port, "name": self.name,
                          "pc_id": self.pc_id}).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for _ in range(3):  # UDP — ishonch uchun bir necha marta
                s.sendto(msg, (p["ip"], INVITE_PORT))
                time.sleep(0.05)
        except OSError as e:
            print(f"[discovery] taklif yuborilmadi: {e}")
            return False
        finally:
            s.close()
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass

    def _beacon_loop(self) -> None:
        nets: list[ipaddress.IPv4Interface] = []
        refreshed = 0.0
        while not self._stop.is_set():
            if time.time() - refreshed > 30:  # tarmoqlar o'zgarishi mumkin (USB modem ulanishi va h.k.)
                nets = local_ipv4_networks()
                refreshed = time.time()
            msg = json.dumps({"t": "rv_host", "name": self.name, "pc_id": self.pc_id,
                              "port": self.port_fn()}).encode()
            for net in nets:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                        b.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        b.bind((str(net.ip), 0))
                        b.sendto(msg, (str(net.network.broadcast_address), INVITE_PORT))
                except OSError:
                    pass
            self._stop.wait(BEACON_EVERY)

    def run(self) -> None:
        threading.Thread(target=self._beacon_loop, name="lan-beacon", daemon=True).start()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", DISCOVERY_PORT))
        s.settimeout(1.0)
        self._sock = s
        print(f"[discovery] UDP {DISCOVERY_PORT} tinglanmoqda")
        while not self._stop.is_set():
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                d = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(d, dict) or d.get("t") != "rv_phone":
                continue
            dev = str(d.get("device_id", ""))[:64]
            if not dev:
                continue
            name = str(d.get("device_name", ""))[:80] or "Telefon"
            auto = d.get("auto", True) is not False
            with self._lock:
                self._phones[dev] = {"name": name, "ip": addr[0], "seen": time.time()}
            if self.on_phone is not None:
                try:
                    self.on_phone(dev, name, addr[0], auto)
                except Exception as e:
                    print(f"[discovery] xato: {e}")
