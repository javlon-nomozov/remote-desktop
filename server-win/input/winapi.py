"""Umumiy Win32 ctypes bindings: DPI awareness, ekran metrikasi, SendInput.

Bu modul `keyboard.py` va `mouse.py` uchun `SendInput` asosini beradi.
Touch injection alohida (`touch.py`) — u boshqa API (InjectTouchInput) ishlatadi.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# ---------------------------------------------------------------------------
# DPI awareness — koordinatalar haqiqiy pikselga mos bo'lishi uchun.
# Bir marta dastur boshida chaqiramiz.
# ---------------------------------------------------------------------------
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_DPI_PER_MONITOR_V2 = ctypes.c_void_p(-4)


def set_dpi_aware() -> None:
    """Jarayonni DPI-aware qilish (bir marta, boshqa oynalardan oldin)."""
    try:
        user32.SetProcessDpiAwarenessContext(_DPI_PER_MONITOR_V2)
        return
    except Exception:
        pass
    try:  # eski Windows uchun fallback
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


# SystemMetrics indekslari
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def primary_screen_size() -> tuple[int, int]:
    """Asosiy monitor o'lchami (px)."""
    return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """Barcha monitorlarni qamrovchi virtual ish stoli: (x, y, w, h)."""
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


# ---------------------------------------------------------------------------
# SendInput strukturalari (mouse + keyboard)
# ---------------------------------------------------------------------------
ULONG_PTR = ctypes.wintypes.WPARAM  # platformaga mos (32/64-bit) pointer-size int

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# MOUSEINPUT.dwFlags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120

# KEYBDINPUT.dwFlags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def send_inputs(*inputs: INPUT) -> int:
    """SendInput chaqiruvi; yuborilgan hodisalar sonini qaytaradi."""
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())
    return sent
