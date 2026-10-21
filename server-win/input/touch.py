"""Windows multi-touch injection (haqiqiy touchscreen emulyatsiyasi).

`InitializeTouchInjection` + `InjectTouchInput` orqali bir nechta touch kontakt yuboramiz.
Natijada Windows'ning o'z gestura mexanizmi ishlaydi: pinch-zoom, 2-barmoq scroll,
3/4-barmoq swipe (task view / virtual desktop) — "huddi haqiqiy touchscreen"dek.

Ref: learn.microsoft.com input_touchinjection; GitHub zyf722/wintoucher.

Ishlatish:
    inj = TouchInjector(max_contacts=10)
    inj.update([Contact(0, x, y, state="down")])   # barmoq tushdi
    inj.update([Contact(0, x2, y2, state="move")])  # siljidi
    inj.update([Contact(0, x3, y3, state="up")])     # ko'tarildi

Koordinatalar — ekran piksellarida (virtual desktop koordinatalari).
Normalizatsiyadan pikselga map qilishni `controller.py` bajaradi.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- Konstantalar --------------------------------------------------------
PT_TOUCH = 0x00000002

# POINTER_FLAGS
POINTER_FLAG_NONE = 0x00000000
POINTER_FLAG_INRANGE = 0x00000002
POINTER_FLAG_INCONTACT = 0x00000004
POINTER_FLAG_DOWN = 0x00010000
POINTER_FLAG_UPDATE = 0x00020000
POINTER_FLAG_UP = 0x00040000

# TOUCH_MASK
TOUCH_MASK_NONE = 0x00000000
TOUCH_MASK_CONTACTAREA = 0x00000001
TOUCH_MASK_ORIENTATION = 0x00000002
TOUCH_MASK_PRESSURE = 0x00000004
TOUCH_MASK_ALL = TOUCH_MASK_CONTACTAREA | TOUCH_MASK_ORIENTATION | TOUCH_MASK_PRESSURE

TOUCH_FLAG_NONE = 0x00000000

# InitializeTouchInjection mode
TOUCH_FEEDBACK_DEFAULT = 0x1
TOUCH_FEEDBACK_INDIRECT = 0x2
TOUCH_FEEDBACK_NONE = 0x3


# --- Strukturalar --------------------------------------------------------
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD),
        ("pointerId", wintypes.UINT),
        ("frameId", wintypes.UINT),
        ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", POINT),
        ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT),
        ("ptHimetricLocationRaw", POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", wintypes.UINT),
        ("InputData", ctypes.c_int32),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", ctypes.c_int),
    ]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("touchFlags", wintypes.DWORD),
        ("touchMask", wintypes.DWORD),
        ("rcContact", RECT),
        ("rcContactRaw", RECT),
        ("orientation", wintypes.UINT),
        ("pressure", wintypes.UINT),
    ]


# Funksiya imzolari
user32.InitializeTouchInjection.argtypes = [wintypes.UINT, wintypes.DWORD]
user32.InitializeTouchInjection.restype = wintypes.BOOL
user32.InjectTouchInput.argtypes = [wintypes.UINT, ctypes.POINTER(POINTER_TOUCH_INFO)]
user32.InjectTouchInput.restype = wintypes.BOOL


@dataclass
class Contact:
    """Bitta barmoq. `id` gestura davomida o'zgarmaydi."""

    id: int
    x: int  # piksel
    y: int  # piksel
    state: str = "move"  # "down" | "move" | "up"
    pressure: float = 0.5  # [0..1]
    radius: int = 4  # kontakt radiusi (px)


class TouchInjector:
    """Faol kontaktlarni kuzatadi va har bir `update` da to'liq kadrni injekt qiladi.

    Windows barcha hozirda-tushgan kontaktlarni har kadrda birga kutadi. Shu sabab biz
    ichki holatni saqlaymiz: `down` qo'shadi, `move` yangilaydi, `up` keyingi kadrdan
    o'chiradi.
    """

    def __init__(self, max_contacts: int = 10) -> None:
        if not user32.InitializeTouchInjection(max_contacts, TOUCH_FEEDBACK_DEFAULT):
            raise ctypes.WinError(ctypes.get_last_error())
        self.max_contacts = max_contacts
        # id -> (x, y, pressure)  — hozirda tushgan barmoqlar
        self._active: dict[int, tuple[int, int, float]] = {}

    def _build(self, contacts: list[Contact], flags_for: dict[int, int]) -> ctypes.Array:
        n = len(contacts)
        arr = (POINTER_TOUCH_INFO * n)()
        for i, c in enumerate(contacts):
            ti = arr[i]
            pi = ti.pointerInfo
            pi.pointerType = PT_TOUCH
            pi.pointerId = c.id
            pi.ptPixelLocation = POINT(int(c.x), int(c.y))
            pi.pointerFlags = flags_for[c.id]
            ti.touchFlags = TOUCH_FLAG_NONE
            ti.touchMask = TOUCH_MASK_ALL
            ti.orientation = 90
            ti.pressure = max(1, min(1024, int(c.pressure * 1024)))
            r = max(1, c.radius)
            ti.rcContact = RECT(c.x - r, c.y - r, c.x + r, c.y + r)
        return arr

    def update(self, contacts: list[Contact]) -> None:
        """Bir kadr: kelgan kontaktlar + hali tushib turgan (lekin yangilanmagan) barmoqlar.

        `contacts` — viewer'dan kelgan o'zgargan barmoqlar. Biz ularni ichki holat bilan
        birlashtiramiz va to'liq kadrni injekt qilamiz.
        """
        frame: dict[int, Contact] = {}
        flags: dict[int, int] = {}

        # 1) Hozirda tushib turgan barmoqlarni "update" sifatida saqlab qolamiz
        for cid, (x, y, p) in self._active.items():
            frame[cid] = Contact(cid, x, y, state="move", pressure=p)
            flags[cid] = POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT

        # 2) Kelgan o'zgarishlarni qo'llaymiz
        for c in contacts:
            if c.state == "down":
                flags[c.id] = POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
                frame[c.id] = c
                self._active[c.id] = (c.x, c.y, c.pressure)
            elif c.state == "move":
                flags[c.id] = POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
                frame[c.id] = c
                self._active[c.id] = (c.x, c.y, c.pressure)
            elif c.state == "up":
                flags[c.id] = POINTER_FLAG_UP
                frame[c.id] = Contact(c.id, c.x, c.y, state="up", pressure=c.pressure)
                self._active.pop(c.id, None)

        if not frame:
            return

        ordered = list(frame.values())
        arr = self._build(ordered, flags)
        if not user32.InjectTouchInput(len(ordered), arr):
            raise ctypes.WinError(ctypes.get_last_error())

    def cancel_all(self) -> None:
        """Barcha faol barmoqlarni darhol ko'tarish (xavfsiz tozalash)."""
        if not self._active:
            return
        ups = [Contact(cid, x, y, state="up", pressure=p) for cid, (x, y, p) in self._active.items()]
        self.update(ups)
        self._active.clear()
