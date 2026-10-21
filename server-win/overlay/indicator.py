"""Ko'rinadigan, click-through "faol" indikatori.

Maqsad: dastur ishlab turganini ko'rsatish (shaffoflik). Bosilganda hech narsa qilmaydi —
sichqoncha/touch hodisasi to'g'ridan-to'g'ri tagidagi oynaga o'tadi (WS_EX_TRANSPARENT).

Rejimlar:
  - "dot"       — burchakda qizil nuqta (sekin "yonib" turadi)
  - "watermark" — ekran bo'ylab ~50% ko'rinadigan katta yozuv

Texnika: tkinter frameless, topmost oyna + `-transparentcolor` (fon to'liq shaffof) +
`-alpha` (kontent shaffofligi). Keyin ctypes bilan WS_EX_TRANSPARENT/NOACTIVATE/TOOLWINDOW
qo'shib, oynani butunlay "o'tkazuvchan" qilamiz.

Threadlar: `start()` indikatorni alohida threadда (o'z tk mainloop'i bilan) ishga tushiradi,
shunda u asosiy server oqimini bloklamaydi. `stop()` uni to'xtatadi.
"""
from __future__ import annotations

import ctypes
import threading
import tkinter as tk

_CHROMA = "#0b0c0e"  # fon uchun chroma-key (ekranda uchramaydigan rang)

# Win32 — click-through
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

_user32 = ctypes.WinDLL("user32", use_last_error=True)


def _make_click_through(hwnd: int) -> None:
    """Oynaga click-through uslublarini qo'shish."""
    try:
        get_ = _user32.GetWindowLongPtrW
        set_ = _user32.SetWindowLongPtrW
    except AttributeError:  # 32-bit Python
        get_ = _user32.GetWindowLongW
        set_ = _user32.SetWindowLongW
    style = get_(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    set_(hwnd, GWL_EXSTYLE, style)


class Indicator:
    def __init__(self, mode: str = "dot", dot_size: int = 16, margin: int = 14) -> None:
        self.mode = mode
        self.dot_size = dot_size
        self.margin = margin
        self._thread: threading.Thread | None = None
        self._root: tk.Tk | None = None
        self._stop = threading.Event()
        self._pulse_up = False

    # --- public ---------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="indicator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def set_mode(self, mode: str) -> None:
        """Rejimni almashtirish (keyingi start uchun). Jonli almashtirish keyinroq."""
        self.mode = mode

    # --- internal -------------------------------------------------------
    def _run(self) -> None:
        root = tk.Tk()
        self._root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=_CHROMA)
        try:
            root.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass  # platforma qo'llamasa, hech bo'lmasa topmost oyna chiqadi

        if self.mode == "watermark":
            self._build_watermark(root)
        else:
            self._build_dot(root)

        root.update_idletasks()
        try:
            _make_click_through(root.winfo_id())
        except Exception:
            pass  # click-through muvaffaqiyatsiz bo'lsa ham indikator ko'rinadi

        self._poll_stop(root)
        root.mainloop()

    def _build_dot(self, root: tk.Tk) -> None:
        s = self.dot_size
        pad = 4
        size = s + pad * 2
        sw = root.winfo_screenwidth()
        x = sw - size - self.margin
        y = self.margin
        root.geometry(f"{size}x{size}+{x}+{y}")
        root.attributes("-alpha", 1.0)
        cv = tk.Canvas(root, width=size, height=size, bg=_CHROMA, highlightthickness=0)
        cv.pack()
        self._dot = cv.create_oval(pad, pad, pad + s, pad + s, fill="#ff3b30", outline="")
        self._cv = cv
        self._animate_dot()

    def _animate_dot(self) -> None:
        """Sekin "nafas olish" effekti — faol ekanini bildiradi."""
        if self._stop.is_set() or self._root is None:
            return
        # alpha'ni 0.55..1.0 oralig'ida tebratamiz
        try:
            cur = float(self._root.attributes("-alpha"))
        except Exception:
            cur = 1.0
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
            self._root.attributes("-alpha", cur)
            self._root.after(60, self._animate_dot)
        except Exception:
            pass

    def _build_watermark(self, root: tk.Tk) -> None:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{sw}x{sh}+0+0")
        root.attributes("-alpha", 0.5)  # 50% ko'rinadigan
        cv = tk.Canvas(root, width=sw, height=sh, bg=_CHROMA, highlightthickness=0)
        cv.pack()
        text = "REMOTE SESSION ACTIVE"
        # diagonal takrorlangan yozuv
        step = 260
        for gy in range(0, sh + step, step):
            for gx in range(0, sw + step, step):
                cv.create_text(
                    gx, gy, text=text, fill="#ff3b30", font=("Segoe UI", 22, "bold"), angle=30
                )

    def _poll_stop(self, root: tk.Tk) -> None:
        if self._stop.is_set():
            try:
                root.destroy()
            except Exception:
                pass
            return
        root.after(120, lambda: self._poll_stop(root))
