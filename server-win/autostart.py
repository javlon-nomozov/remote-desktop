"""Windows integratsiyasi: shell:startup yorlig'i, lokal tarmoq uchun Firewall ruxsati, bitta nusxa.

Yorliq: %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\RemoteServer.lnk ->
RemoteServer.exe --autostart. Faqat exe (PyInstaller) uchun; `python server_gui.py` da o'chiq.
Eslatma: Startup Windows'ga KIRILGANDAN keyin ishlaydi (login ekranida emas).
"""
from __future__ import annotations

import base64
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


def _powershell(command: str, timeout: int = 60, env: dict | None = None) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       env=env, capture_output=True, text=True, timeout=timeout,
                       creationflags=_CREATE_NO_WINDOW)
    return (r.stdout or "").strip()


def lan_firewall_ok() -> bool | None:
    """Windows Firewall shu exe'ga lokal tarmoqdan kirishga ruxsat beradimi.
    None — tekshirib bo'lmaydi (exe emas). Ruxsat qoidasi bo'lmasa yoki bloklovchi qoida bo'lsa —
    telefon Wi-Fi / USB orqali ulana olmaydi (Windows ko'pincha tarmoqni "Public" deb bloklaydi)."""
    exe = exe_path()
    if not exe:
        return None
    ps = ("$f=Get-NetFirewallApplicationFilter -Program $env:RS_EXE -ErrorAction SilentlyContinue;"
          "if(-not $f){'none';exit};"
          "$r=$f|Get-NetFirewallRule|?{$_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound'};"
          "if($r|?{$_.Action -eq 'Block'}){'block'}elseif($r|?{$_.Action -eq 'Allow'}){'allow'}else{'none'}")
    try:
        return _powershell(ps, env=dict(os.environ, RS_EXE=exe)) == "allow"
    except Exception as e:
        print(f"[firewall] tekshirib bo'lmadi: {e}")
        return None


def allow_lan_firewall() -> bool:
    """Administrator ruxsati (UAC) bilan: shu exe uchun bloklovchi qoidalarni o'chirib, barcha tarmoq
    turlarida kiruvchi ulanishga ruxsat qo'shadi. Ulanishni baribir kompyuterda tasdiqlash kerak."""
    exe = exe_path()
    if not exe:
        return False
    p = exe.replace("'", "''")
    inner = (f"$p='{p}';"
             "Get-NetFirewallApplicationFilter -Program $p -ErrorAction SilentlyContinue|"
             "Get-NetFirewallRule|Remove-NetFirewallRule;"
             "New-NetFirewallRule -DisplayName 'Remote Server (lokal tarmoq)' -Direction Inbound "
             "-Program $p -Action Allow -Profile Any|Out-Null")
    enc = base64.b64encode(inner.encode("utf-16-le")).decode()
    outer = ("Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
             f"-ArgumentList '-NoProfile','-EncodedCommand','{enc}'")
    try:
        _powershell(outer, timeout=180)
    except Exception as e:
        print(f"[firewall] ruxsat berilmadi: {e}")
    return lan_firewall_ok() is True


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
