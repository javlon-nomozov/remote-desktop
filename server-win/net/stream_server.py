"""Faza 2 MVP transport: WebSocket + JPEG stream (server tomoni).

Server ekranni JPEG kadrlar sifatida viewerга yuboradi va viewerдан kelgan input
hodisalarini (PROTOCOL.md §2) qabul qilib qurilmaga qo'llaydi. Bu to'liq zanjirni
(capture -> stream -> input injection) darhol ishlatib ko'rsatadi. Past kechikishli
H.264/WebRTC keyingi bosqich (aiortc) — bir xil input protokol saqlanadi.

Transport (bu MVP uchun oddiy, hujjatlashtirilgan):
  Server -> viewer:  matn JSON {"t":"hello","w":W,"h":H,"fps":N}, keyin ketma-ket binary JPEG
  viewer -> server:  matn JSON input hodisalari (mouse/scroll/key/text/touch)

Bitta WebSocket ulanishi = bitta sessiya. Ulanish uzilsa yoki server yopilsa — to'xtaydi.
"""
from __future__ import annotations

import json
import threading
import time
from io import BytesIO
from typing import Callable, Optional

import numpy as np
from PIL import Image
from websockets.sync.server import serve

from capture import ScreenCapture


class StreamServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        fps: int = 20,
        quality: int = 60,
        scale: float = 1.0,
        on_input: Optional[Callable[[dict], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality
        self.scale = scale
        self.on_input = on_input
        self.on_status = on_status
        self._server = None

    def stop(self) -> None:
        try:
            if self._server is not None:
                self._server.shutdown()
        except Exception:
            pass

    def _send_frames(self, ws, stop: threading.Event) -> None:
        cap = ScreenCapture(target_fps=self.fps)
        try:
            # ekran o'lchamini bilish uchun bitta kadr
            first = None
            for _ in range(30):
                first = cap.grab()
                if first is not None:
                    break
                time.sleep(0.02)
            if first is None:
                return
            h, w = first.shape[0], first.shape[1]
            ws.send(json.dumps({"t": "hello", "w": int(w), "h": int(h), "fps": self.fps}))

            interval = 1.0 / max(1, self.fps)
            while not stop.is_set():
                t0 = time.perf_counter()
                frame = cap.grab()
                if frame is not None:
                    jpeg = self._encode(frame)
                    try:
                        ws.send(jpeg)
                    except Exception:
                        break
                dt = time.perf_counter() - t0
                if dt < interval:
                    time.sleep(interval - dt)
        finally:
            cap.close()

    def _encode(self, frame: np.ndarray) -> bytes:
        # capture BGR beradi -> PIL uchun RGB
        rgb = frame[:, :, ::-1]
        img = Image.fromarray(rgb)
        if self.scale != 1.0:
            img = img.resize((int(img.width * self.scale), int(img.height * self.scale)))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=self.quality)
        return buf.getvalue()

    def _handler(self, ws) -> None:
        peer = getattr(ws, "remote_address", None)
        print(f"[stream] viewer ulandi: {peer}")
        if self.on_status:
            self.on_status("viewer_connected")
        stop = threading.Event()
        sender = threading.Thread(target=self._send_frames, args=(ws, stop), daemon=True)
        sender.start()
        try:
            for msg in ws:  # viewerдан kelgan input hodisalari
                if isinstance(msg, (bytes, bytearray)):
                    continue  # viewer binary yubormaydi
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                if self.on_input is not None:
                    try:
                        self.on_input(data)
                    except Exception as e:
                        print(f"[stream] input xato: {e}")
        finally:
            stop.set()
            print(f"[stream] viewer uzildi: {peer}")
            if self.on_status:
                self.on_status("viewer_disconnected")

    def serve(self) -> None:
        print(f"[stream] tinglanmoqda ws://{self.host}:{self.port}  (fps={self.fps}, q={self.quality})")
        with serve(self._handler, self.host, self.port, max_size=None) as server:
            self._server = server
            server.serve_forever()
