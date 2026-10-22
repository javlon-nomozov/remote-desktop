"""HostService — kompyuter tomonidagi hamma narsa bitta joyda.

  - HostCore: ruxsat, ishonchli telefonlar, kadr oqimi
  - StreamServer: LAN (ws 47865) — internet kerak emas
  - Discovery: lokal tarmoqdagi telefonlar ro'yxati (UDP 47866) va taklif
  - RelayHost: internet orqali doimiy kod (backend), uzilsa qayta urinadi

Ishonchli (muddati o'tmagan) telefon lokal tarmoqda ko'rinsa va ulanmagan bo'lsa — so'rovsiz
taklif yuboriladi. Kompyuter qayta yoqilganda telefon shu yo'l bilan o'zi qayta ulanadi.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .discovery import Discovery
from .host_core import HostCore, Viewer, host_identity
from .relay_client import RelayHost
from .stream_server import StreamServer


class HostService:
    def __init__(
        self,
        backend_url: str = "",
        fps: int = 20,
        quality: int = 60,
        on_input: Optional[Callable[[dict], None]] = None,
        ask_permission: Optional[Callable[[Viewer], object]] = None,
        on_event: Optional[Callable[[str, Viewer], None]] = None,
        on_code: Optional[Callable[[dict], None]] = None,
        on_relay_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.core = HostCore(fps=fps, quality=quality, on_input=on_input,
                             ask_permission=ask_permission, on_event=on_event)
        self.lan = StreamServer(self.core)
        self.discovery = Discovery(on_phone=self._on_phone, pc_id=host_identity()[0],
                                   port_fn=lambda: self.lan.port)
        self.relay = (RelayHost(backend_url, self.core, on_code=on_code, on_status=on_relay_status)
                      if backend_url else None)
        self.lan_error: Optional[str] = None
        self._invited: dict[str, float] = {}  # device_id -> oxirgi avto-taklif vaqti

    def start(self) -> None:
        threading.Thread(target=self._run_lan, name="lan", daemon=True).start()
        threading.Thread(target=self._run_discovery, name="discovery", daemon=True).start()
        if self.relay is not None:
            threading.Thread(target=self.relay.run_forever, name="relay", daemon=True).start()

    def stop(self) -> None:
        self.core.stop()
        self.lan.stop()
        self.discovery.stop()
        if self.relay is not None:
            self.relay.stop()

    def _run_lan(self) -> None:
        try:
            self.lan.serve()
        except OSError as e:
            self.lan_error = str(e)
            print(f"[lan] ishga tushmadi: {e}")

    def _run_discovery(self) -> None:
        try:
            self.discovery.run()
        except OSError as e:
            self.lan_error = str(e)
            print(f"[discovery] ishga tushmadi: {e}")

    # --- lokal tarmoq --------------------------------------------------
    def connect_phone(self, device_id: str, name: str, seconds: Optional[int]) -> bool:
        """GUI'da tanlangan telefonga taklif yuboradi. Telefon (o'zida ruxsat berib) 2 daqiqa ichida
        ulansa — so'rovsiz qabul qilinadi va shu muddatga ishonchli bo'ladi."""
        self.core.preapprove(device_id, name, seconds)
        self._invited[device_id] = time.time()
        return self.discovery.invite(device_id, self.lan.port)

    def _on_phone(self, device_id: str, name: str, ip: str, auto: bool) -> None:
        if not auto or self.core.trust.get(device_id) is None:
            return
        cur = self.core.active
        if cur is not None and cur.alive:
            return  # kimdir ulangan (shu telefonning o'zi yoki boshqasi)
        now = time.time()
        if now - self._invited.get(device_id, 0) < 3.0:
            return
        self._invited[device_id] = now
        self.discovery.invite(device_id, self.lan.port)
