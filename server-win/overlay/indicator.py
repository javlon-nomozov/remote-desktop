"""Ko'rinadigan, click-through "faol" indikatori.

Maqsad: dastur ishlab turganini ko'rsatish (shaffoflik). Bosilganda hech narsa qilmaydi —
sichqoncha/touch hodisasi to'g'ridan-to'g'ri tagidagi oynaga o'tadi (WS_EX_TRANSPARENT).

Rejimlar: "dot" (yashil nuqta, sekin "nafas oladi") yoki "watermark" (~50% yozuv).

Ikki ishlatish usuli:
  - `start()` / `stop()` — alohida threadда o'z Tk mainloop'i bilan (konsol server uchun).
  - `attach(parent)` / `detach()` — mavjud Tk root'ining Toplevel'i sifatida (GUI ilova uchun,
    asosiy threadда chaqiriladi). Shunda bitta Tk bo'ladi.
"""
from __future__ import annotations

import ctypes
import threading
import tkinter as tk
from ctypes import wintypes

_CHROMA = "#0b0c0e"  # fon uchun chroma-key (ekranda uchramaydigan rang)

# Win32 — click-through
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_LONG_PTR = ctypes.c_ssize_t
_GA_ROOT = 2

# MUHIM: imzolarni aniq belgilaymiz. Aks holda 64-bit'da ctypes HWND/style'ni c_int'ga
# qisqartiradi va uslub NOTO'G'RI oynaga qo'llanadi — click-through shu sabab ishlamagan edi.
try:
    _get_wl = _user32.GetWindowLongPtrW
    _set_wl = _user32.SetWindowLongPtrW
except AttributeError:  # 32-bit Python
    _get_wl = _user32.GetWindowLongW
    _set_wl = _user32.SetWindowLongW
_get_wl.restype = _LONG_PTR
_get_wl.argtypes = [wintypes.HWND, ctypes.c_int]
_set_wl.restype = _LONG_PTR
_set_wl.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]


def _make_click_through(hwnd: int) -> None:
    """Oynani va uning top-level ajdodini click-through qiladi."""
    top = _user32.GetAncestor(hwnd, _GA_ROOT) or hwnd
    bits = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    for h in {hwnd, top}:
        cur = _get_wl(h, GWL_EXSTYLE)
        _set_wl(h, GWL_EXSTYLE, cur | bits)


class Indicator:
    def __init__(self, mode: str = "dot", dot_size: int = 16, margin: int = 14) -> None:
        self.mode = mode
        self.dot_size = dot_size
        self.margin = margin
        self._thread: threading.Thread | None = None
        self._win: tk.Misc | None = None  # Tk (threaded) yoki Toplevel (attached)
        self._stop = threading.Event()
        self._pulse_up = False

    # --- threaded (konsol) ---------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="indicator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _run(self) -> None:
        root = tk.Tk()
        self._win = root
        self._setup(root)
        self._poll_stop(root)
        root.mainloop()

    def _poll_stop(self, win: tk.Tk) -> None:
        if self._stop.is_set():
            try:
                win.destroy()
            except Exception:
                pass
            return
        win.after(120, lambda: self._poll_stop(win))

    # --- attached (GUI) ------------------------------------------------
    def attach(self, parent: tk.Misc) -> None:
        """GUI root'ining Toplevel'i sifatida ko'rsatadi (asosiy threadда)."""
        self._stop.clear()
        win = tk.Toplevel(parent)
        self._win = win
        self._setup(win)

    def detach(self) -> None:
        self._stop.set()
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    # --- umumiy qurish -------------------------------------------------
    def _setup(self, win: tk.Misc) -> None:
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.config(bg=_CHROMA)
        try:
            win.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        if self.mode == "watermark":
            self._build_watermark(win)
        else:
            self._build_dot(win)
        win.update_idletasks()
        try:
            _make_click_through(win.winfo_id())
        except Exception:
            pass

    def _build_dot(self, win: tk.Misc) -> None:
        s = self.dot_size
        pad = 4
        size = s + pad * 2
        sw = win.winfo_screenwidth()
        x = sw - size - self.margin
        y = self.margin
        win.geometry(f"{size}x{size}+{x}+{y}")
        win.attributes("-alpha", 1.0)
        cv = tk.Canvas(win, width=size, height=size, bg=_CHROMA, highlightthickness=0)
        cv.pack()
        cv.create_oval(pad, pad, pad + s, pad + s, fill="#22c55e", outline="")
        self._animate_dot()

    def _animate_dot(self) -> None:
        if self._stop.is_set() or self._win is None:
            return
        try:
            cur = float(self._win.attributes("-alpha"))
        except Exception:
            return
        step = 0.05
        if self._pulse_up:
            cur += step
            if cur >= 1.0:
                cur, self._pulse_up = 1.0, False
        else:
            cur -= step
            if cur <= 0.55:
                cur, self._pulse_up = 0.55, True
        try:
            self._win.attributes("-alpha", cur)
            self._win.after(60, self._animate_dot)
        except Exception:
            pass

    def _build_watermark(self, win: tk.Misc) -> None:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{sw}x{sh}+0+0")
        win.attributes("-alpha", 0.5)
        cv = tk.Canvas(win, width=sw, height=sh, bg=_CHROMA, highlightthickness=0)
        cv.pack()
        text = "REMOTE SESSION ACTIVE"
        step = 260
        for gy in range(0, sh + step, step):
            for gx in range(0, sw + step, step):
                cv.create_text(gx, gy, text=text, fill="#22c55e",
                               font=("Segoe UI", 22, "bold"), angle=30)
