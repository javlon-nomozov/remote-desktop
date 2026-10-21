"""Klaviatura injection (SendInput).

Ikki yo'l:
  - `key(code, down)` — W3C `KeyboardEvent.code` (fizik tugma) → Windows scancode (set 1).
    O'yinlar/ilovalar uchun ishonchli, klaviatura tiliga bog'liq emas.
  - `type_text(s)` — unicode matn (IME/maxsus belgilar) KEYEVENTF_UNICODE orqali.
"""
from __future__ import annotations

from . import winapi as w

# W3C KeyboardEvent.code -> PS/2 scancode (set 1). Kengaytirilgan tugmalar `ext=True`.
# (scancode, is_extended)
_CODE_TO_SCAN: dict[str, tuple[int, bool]] = {
    # Harflar
    "KeyA": (0x1E, False), "KeyB": (0x30, False), "KeyC": (0x2E, False), "KeyD": (0x20, False),
    "KeyE": (0x12, False), "KeyF": (0x21, False), "KeyG": (0x22, False), "KeyH": (0x23, False),
    "KeyI": (0x17, False), "KeyJ": (0x24, False), "KeyK": (0x25, False), "KeyL": (0x26, False),
    "KeyM": (0x32, False), "KeyN": (0x31, False), "KeyO": (0x18, False), "KeyP": (0x19, False),
    "KeyQ": (0x10, False), "KeyR": (0x13, False), "KeyS": (0x1F, False), "KeyT": (0x14, False),
    "KeyU": (0x16, False), "KeyV": (0x2F, False), "KeyW": (0x11, False), "KeyX": (0x2D, False),
    "KeyY": (0x15, False), "KeyZ": (0x2C, False),
    # Raqamlar
    "Digit1": (0x02, False), "Digit2": (0x03, False), "Digit3": (0x04, False),
    "Digit4": (0x05, False), "Digit5": (0x06, False), "Digit6": (0x07, False),
    "Digit7": (0x08, False), "Digit8": (0x09, False), "Digit9": (0x0A, False),
    "Digit0": (0x0B, False),
    # Funksional
    "F1": (0x3B, False), "F2": (0x3C, False), "F3": (0x3D, False), "F4": (0x3E, False),
    "F5": (0x3F, False), "F6": (0x40, False), "F7": (0x41, False), "F8": (0x42, False),
    "F9": (0x43, False), "F10": (0x44, False), "F11": (0x57, False), "F12": (0x58, False),
    # Boshqaruv
    "Escape": (0x01, False), "Backspace": (0x0E, False), "Tab": (0x0F, False),
    "Enter": (0x1C, False), "Space": (0x39, False), "CapsLock": (0x3A, False),
    "ShiftLeft": (0x2A, False), "ShiftRight": (0x36, False),
    "ControlLeft": (0x1D, False), "ControlRight": (0x1D, True),
    "AltLeft": (0x38, False), "AltRight": (0x38, True),
    "MetaLeft": (0x5B, True), "MetaRight": (0x5C, True),
    "ContextMenu": (0x5D, True),
    # Belgilar
    "Minus": (0x0C, False), "Equal": (0x0D, False), "BracketLeft": (0x1A, False),
    "BracketRight": (0x1B, False), "Backslash": (0x2B, False), "Semicolon": (0x27, False),
    "Quote": (0x28, False), "Backquote": (0x29, False), "Comma": (0x33, False),
    "Period": (0x34, False), "Slash": (0x35, False),
    # Navigatsiya (kengaytirilgan)
    "Insert": (0x52, True), "Delete": (0x53, True), "Home": (0x47, True), "End": (0x4F, True),
    "PageUp": (0x49, True), "PageDown": (0x51, True),
    "ArrowUp": (0x48, True), "ArrowDown": (0x50, True),
    "ArrowLeft": (0x4B, True), "ArrowRight": (0x4D, True),
    "PrintScreen": (0x37, True), "ScrollLock": (0x46, False), "Pause": (0x45, False),
    # Numpad
    "Numpad0": (0x52, False), "Numpad1": (0x4F, False), "Numpad2": (0x50, False),
    "Numpad3": (0x51, False), "Numpad4": (0x4B, False), "Numpad5": (0x4C, False),
    "Numpad6": (0x4D, False), "Numpad7": (0x47, False), "Numpad8": (0x48, False),
    "Numpad9": (0x49, False), "NumpadDecimal": (0x53, False), "NumpadAdd": (0x4E, False),
    "NumpadSubtract": (0x4A, False), "NumpadMultiply": (0x37, False),
    "NumpadDivide": (0x35, True), "NumpadEnter": (0x1C, True), "NumLock": (0x45, True),
}


def _key_input(scan: int, ext: bool, up: bool) -> w.INPUT:
    flags = w.KEYEVENTF_SCANCODE
    if ext:
        flags |= w.KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= w.KEYEVENTF_KEYUP
    ki = w.KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return w.INPUT(type=w.INPUT_KEYBOARD, u=w._INPUTunion(ki=ki))


def key(code: str, down: bool) -> bool:
    """Fizik tugmani bosish/qo'yib yuborish. Noma'lum `code` → False."""
    hit = _CODE_TO_SCAN.get(code)
    if hit is None:
        return False
    scan, ext = hit
    w.send_inputs(_key_input(scan, ext, up=not down))
    return True


def _unicode_input(ch: str, up: bool) -> w.INPUT:
    flags = w.KEYEVENTF_UNICODE | (w.KEYEVENTF_KEYUP if up else 0)
    ki = w.KEYBDINPUT(wVk=0, wScan=ord(ch), dwFlags=flags, time=0, dwExtraInfo=0)
    return w.INPUT(type=w.INPUT_KEYBOARD, u=w._INPUTunion(ki=ki))


def type_text(text: str) -> None:
    """Unicode matn kiritish (klaviatura tilidan mustaqil)."""
    seq: list[w.INPUT] = []
    for ch in text:
        # BMP tashqari belgilar (surrogate pair) ham ord() orqali to'g'ri uzatiladi,
        # chunki Python str element kodi UTF-16 kod birligi emas; oddiy holat uchun yetarli.
        seq.append(_unicode_input(ch, up=False))
        seq.append(_unicode_input(ch, up=True))
    if seq:
        w.send_inputs(*seq)
