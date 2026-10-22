"""LAN transport: to'g'ridan-to'g'ri WebSocket (bitta Wi-Fi / USB modem), internet kerak emas.

Telefon `ws://<kompyuter IP>:<port>` ga ulanadi va birinchi xabarda o'zini tanishtiradi:
    {"t":"viewer_hello","device_id":..,"device_name":..}
Keyin hammasi relay bilan bir xil (`HostCore`): ruxsat, kadrlar, input.
Kompyuter IP'sini telefon UDP taklifdan oladi (net/discovery.py).
"""
from __future__ import annotations

import json
import threading

from websockets.sync.server import serve

from .host_core import HostCore, Viewer

LAN_PORT = 47865  # kam ishlatiladigan port; band bo'lsa serve() boshqasini oladi


class StreamServer:
    def __init__(self, core: HostCore, host: str = "0.0.0.0", port: int = LAN_PORT) -> None:
        self.core = core
        self.host = host
        self.port = port
        self._server = None

    def stop(self) -> None:
        try:
            if self._server is not None:
                self._server.shutdown()
        except Exception:
            pass

    def _handler(self, ws) -> None:
        peer = getattr(ws, "remote_address", None)
        try:
            hello = json.loads(ws.recv(timeout=10))
        except Exception:
            return
        if not isinstance(hello, dict) or hello.get("t") != "viewer_hello":
            return
        lock = threading.Lock()

        def send(data) -> None:
            with lock:
                ws.send(data)

        v = Viewer(
            send_text=send,
            send_bytes=send,
            close=ws.close,
            device_id=str(hello.get("device_id", ""))[:64],
            device_name=str(hello.get("device_name", ""))[:80],
            via="lan",
        )
        print(f"[lan] viewer ulandi: {peer}")
        self.core.viewer_connected(v)
        try:
            for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    continue
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                self.core.viewer_message(v, data)
        except Exception:
            pass
        finally:
            print(f"[lan] viewer uzildi: {peer}")
            self.core.viewer_disconnected(v)

    def serve(self) -> None:
        try:
            server = serve(self._handler, self.host, self.port, max_size=None)
        except OSError:
            # port band (boshqa dastur) — bo'sh port olamiz; telefon portni taklifdan biladi
            print(f"[lan] port {self.port} band, boshqasi tanlanadi")
            server = serve(self._handler, self.host, 0, max_size=None)
        self.port = server.socket.getsockname()[1]
        print(f"[lan] tinglanmoqda ws://{self.host}:{self.port}")
        with server:
            self._server = server
            server.serve_forever()
