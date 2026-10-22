"""Relay host klienti — server backendga ulanib KOD oladi va shu orqali stream qiladi.

Server (boshqariladigan kompyuter) backendga `/relay/host?id=&secret=` ga ulanadi va o'zining
DOIMIY kodini oladi (kompyuter qayta yoqilganda ham o'sha kod — telefon o'zi qayta ulanadi).
Viewer o'sha kodni kiritganda backend juftlaydi; shundan so'ng kadrlar va input relay orqali
o'tadi. Telefon va kompyuter har xil tarmoqda bo'lsa ham ishlaydi.

Internet bo'lmasa yoki aloqa uzilsa — fonda qayta urinadi (LAN rejimi bunga bog'liq emas).
Ruxsat va kadr oqimi `HostCore` da.
"""
from __future__ import annotations

import json
import threading
from typing import Callable, Optional
from urllib.parse import urlencode

from websockets.sync.client import connect

from .host_core import HostCore, Viewer, host_identity


class RelayHost:
    def __init__(
        self,
        relay_url: str,
        core: HostCore,
        on_code: Optional[Callable[[dict], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        hid, secret = host_identity()
        self.url = relay_url.rstrip("/") + "/relay/host?" + urlencode({"id": hid, "secret": secret})
        self.core = core
        self.on_code = on_code
        self.on_status = on_status  # "online" | "offline"
        self.code: Optional[str] = None
        self._ws = None
        self._viewer: Optional[Viewer] = None
        self._send_lock = threading.Lock()
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass

    def _status(self, s: str) -> None:
        if self.on_status:
            self.on_status(s)

    def run_forever(self) -> None:
        """Uzilsa qayta ulanadi (2 -> 10 s oraliq) — stop() chaqirilguncha."""
        delay = 2.0
        while not self._stop.is_set():
            try:
                self._run_once()
                delay = 2.0
            except Exception as e:
                print(f"[relay] ulanib bo'lmadi: {e}")
            self._end_viewer()
            if self._stop.is_set():
                break
            self._status("offline")
            self._stop.wait(delay)
            delay = min(delay * 2, 10.0)

    def _send(self, data) -> None:
        ws = self._ws
        if ws is None:
            raise ConnectionError("relay yopiq")
        with self._send_lock:
            ws.send(data)

    def _end_viewer(self) -> None:
        v, self._viewer = self._viewer, None
        if v is not None:
            self.core.viewer_disconnected(v)

    def _run_once(self) -> None:
        with connect(self.url, max_size=None, open_timeout=15) as ws:
            self._ws = ws
            try:
                data = json.loads(ws.recv())
                if data.get("t") == "code":
                    self.code = data["code"]
                    print(f"\n======== ULANISH KODI: {data.get('pretty', self.code)} ========\n")
                    self._status("online")
                    if self.on_code:
                        self.on_code(data)
                for m in ws:
                    if isinstance(m, (bytes, bytearray)):
                        continue
                    try:
                        d = json.loads(m)
                    except Exception:
                        continue
                    t = d.get("t")
                    if t == "viewer_connected":
                        self._end_viewer()
                        v = Viewer(
                            send_text=self._send,
                            send_bytes=self._send,
                            close=lambda: None,  # relay'da viewer socketi backendda; u o'zi yopadi
                            device_id=str(d.get("device_id", "")),
                            device_name=str(d.get("device_name", "")),
                            user=str(d.get("user", "")),
                            via="internet",
                        )
                        self._viewer = v
                        self.core.viewer_connected(v)
                    elif t == "viewer_disconnected":
                        self._end_viewer()
                    elif self._viewer is not None:
                        self.core.viewer_message(self._viewer, d)
            finally:
                self._ws = None
