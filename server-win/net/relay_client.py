"""Relay host klienti — server backendga ulanib UNIQUE KOD oladi va shu orqali stream qiladi.

Server (boshqariladigan kompyuter) backendga `/relay/host` ga ulanadi, kod oladi va uni
ko'rsatadi. Viewer o'sha kodni kiritganda backend juftlaydi; shundan so'ng kadrlar va input
relay orqali o'tadi. Telefon va kompyuter har xil tarmoqda bo'lsa ham ishlaydi.
"""
from __future__ import annotations

import json
import threading
import time
from io import BytesIO
from typing import Callable, Optional

from PIL import Image
from websockets.sync.client import connect

from capture import ScreenCapture


class RelayHost:
    def __init__(
        self,
        relay_url: str,
        fps: int = 20,
        quality: int = 60,
        scale: float = 1.0,
        on_input: Optional[Callable[[dict], None]] = None,
        on_code: Optional[Callable[[dict], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.url = relay_url.rstrip("/") + "/relay/host"
        self.fps = fps
        self.quality = quality
        self.scale = scale
        self.on_input = on_input
        self.on_code = on_code
        self.on_status = on_status
        self.code: Optional[str] = None
        self._present = threading.Event()  # viewer ulanganmi
        self._cap: Optional[ScreenCapture] = None
        self._ws = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass

    def _encode(self, frame) -> bytes:
        rgb = frame[:, :, ::-1]
        img = Image.fromarray(rgb)
        if self.scale != 1.0:
            img = img.resize((int(img.width * self.scale), int(img.height * self.scale)))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=self.quality)
        return buf.getvalue()

    def _send_hello(self, ws) -> None:
        for _ in range(40):
            f = self._cap.grab() if self._cap else None
            if f is not None:
                h, w = f.shape[0], f.shape[1]
                ws.send(json.dumps({"t": "hello", "w": int(w), "h": int(h), "fps": self.fps}))
                return
            time.sleep(0.02)

    def _send_frames(self, ws, stop: threading.Event) -> None:
        interval = 1.0 / max(1, self.fps)
        while not stop.is_set():
            if not self._present.is_set():
                time.sleep(0.1)
                continue
            t0 = time.perf_counter()
            frame = self._cap.grab() if self._cap else None
            if frame is not None:
                try:
                    ws.send(self._encode(frame))
                except Exception:
                    break
            dt = time.perf_counter() - t0
            if dt < interval:
                time.sleep(interval - dt)

    def run(self) -> None:
        self._cap = ScreenCapture(target_fps=self.fps)
        try:
            with connect(self.url, max_size=None, open_timeout=15) as ws:
                self._ws = ws
                data = json.loads(ws.recv())
                if data.get("t") == "code":
                    self.code = data["code"]
                    pretty = data.get("pretty", self.code)
                    print(f"\n======== ULANISH KODI: {pretty} ========")
                    print("Telefonда shu kodni kiriting.\n")
                    if self.on_code:
                        self.on_code(data)

                stop = threading.Event()
                sender = threading.Thread(target=self._send_frames, args=(ws, stop), daemon=True)
                sender.start()
                try:
                    for m in ws:
                        if isinstance(m, (bytes, bytearray)):
                            continue
                        try:
                            d = json.loads(m)
                        except Exception:
                            continue
                        t = d.get("t")
                        if t == "viewer_connected":
                            print("[relay] viewer ulandi")
                            self._present.set()
                            self._send_hello(ws)
                            if self.on_status:
                                self.on_status("viewer_connected")
                        elif t == "viewer_disconnected":
                            print("[relay] viewer uzildi")
                            self._present.clear()
                            if self.on_status:
                                self.on_status("viewer_disconnected")
                        elif self.on_input is not None:
                            self.on_input(d)
                finally:
                    stop.set()
        finally:
            if self._cap:
                self._cap.close()
