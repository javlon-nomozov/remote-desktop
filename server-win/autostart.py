"""Windows bilan birga ishga tushish (shell:startup yorlig'i) va bitta nusxa nazorati.

Yorliq: %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\RemoteServer.lnk ->
RemoteServer.exe --autostart. Faqat exe (PyInstaller) uchun; `python server_gui.py` da o'chiq.
Eslatma: Startup Windows'ga KIRILGANDAN keyin ishlaydi (login ekranida emas).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys

STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu",
                           "Programs", "Startup")
LINK = os.path.join(STARTUP_DIR, "RemoteServer.lnk")
_CREATE_NO_WINDOW = 0x08000000
_ERROR_ALREADY_EXISTS = 183
_mutex = None


def exe_path() -> str | None:
    return sys.executable if getattr(sys, "frozen", False) else None


def is_enabled() -> bool:
    return os.path.exists(LINK)


def enable() -> bool:
    """Yorliqni yaratadi/yangilaydi (exe ko'chirilgan bo'lsa ham to'g'ri yo'lga)."""
    exe = exe_path()
    if not exe:
        return False
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:RS_LINK);"
          "$s.TargetPath=$env:RS_EXE;$s.Arguments='--autostart';"
          "$s.WorkingDirectory=(Split-Path $env:RS_EXE);$s.IconLocation=$env:RS_EXE;$s.Save()")
    env = dict(os.environ, RS_LINK=LINK, RS_EXE=exe)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           env=env, capture_output=True, timeout=30, creationflags=_CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception as e:
        print(f"[autostart] yorliq yaratilmadi: {e}")
        return False


def disable() -> None:
    try:
        os.remove(LINK)
    except FileNotFoundError:
        pass


def acquire_single_instance(name: str = "Local\\RemoteServerSingleton") -> bool:
    """True — birinchi nusxa. False — dastur allaqachon ochiq."""
    global _mutex
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = k32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def focus_existing(title: str) -> None:
    """Ochiq nusxaning oynasini oldinga chiqaradi."""
    u = ctypes.WinDLL("user32")
    u.FindWindowW.restype = ctypes.c_void_p
    h = u.FindWindowW(None, title)
    if h:
        u.ShowWindow(ctypes.c_void_p(h), 9)  # SW_RESTORE
        u.SetForegroundWindow(ctypes.c_void_p(h))
