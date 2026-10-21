"""Ekran capture: dxcam (tez, Desktop Duplication) + mss (fallback).

Kadrlar BGR/BGRA numpy massiv sifatida qaytadi. Faza 2 da bu kadrlar aiortc video
track'iga (PyAV orqali H.264) uzatiladi.
"""
from __future__ import annotations

import time
from typing import Iterator, Optional

import numpy as np


class ScreenCapture:
    """Ekran capture. Standart backend = mss (toza Python, ishonchli). dxcam opt-in:
    `backend="dxcam"` — lekin dxcam 0.3.x `cv2` (opencv) talab qilishi mumkin; o'rnatilmagan
    bo'lsa mss ga qaytadi."""

    def __init__(self, monitor: int = 0, target_fps: int = 30, backend: str = "mss") -> None:
        self.monitor = monitor
        self.target_fps = target_fps
        self._backend = None
        self._kind = None
        self._mss = None
        self._mon = None
        self._init_backend(backend)

    def _init_backend(self, backend: str) -> None:
        if backend == "dxcam":
            try:
                import dxcam  # type: ignore

                cam = dxcam.create(output_idx=self.monitor, output_color="BGR")
                if cam is not None:
                    cam.start(target_fps=self.target_fps, video_mode=True)
                    # bitta test kadr bilan ishlashiga ishonch hosil qilamiz
                    import time as _t
                    for _ in range(20):
                        if cam.get_latest_frame() is not None:
                            self._backend = cam
                            self._kind = "dxcam"
                            return
                        _t.sleep(0.02)
                    cam.stop()  # ishlamadi -> mss ga o'tamiz
            except Exception:
                pass
        # Standart / fallback: mss
        import mss  # type: ignore

        self._mss = mss.mss()
        mons = self._mss.monitors
        # monitors[0] — hammasi; [1..] — alohida. Asosiysi uchun 1.
        idx = self.monitor + 1 if self.monitor + 1 < len(mons) else 1
        self._mon = mons[idx]
        self._kind = "mss"

    @property
    def backend(self) -> str:
        return self._kind or "none"

    def grab(self) -> Optional[np.ndarray]:
        """Bitta kadr (BGR). dxcam yangi kadr bo'lmasa None qaytarishi mumkin."""
        if self._kind == "dxcam":
            return self._backend.get_latest_frame()
        shot = self._mss.grab(self._mon)
        # mss BGRA beradi → BGR
        arr = np.frombuffer(shot.rgb, dtype=np.uint8)  # mss.rgb aslida BGR tartibda
        return arr.reshape((shot.height, shot.width, 3))

    def frames(self) -> Iterator[np.ndarray]:
        """target_fps ga yaqin tezlikda kadrlar generatori."""
        interval = 1.0 / max(1, self.target_fps)
        while True:
            t0 = time.perf_counter()
            frame = self.grab()
            if frame is not None:
                yield frame
            dt = time.perf_counter() - t0
            if dt < interval:
                time.sleep(interval - dt)

    def close(self) -> None:
        if self._kind == "dxcam" and self._backend is not None:
            try:
                self._backend.stop()
            except Exception:
                pass
        if self._mss is not None:
            try:
                self._mss.close()
            except Exception:
                pass
