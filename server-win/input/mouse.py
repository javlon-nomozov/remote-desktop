"""Sichqoncha injection (SendInput): absolute (touchscreen tap), relative (touchpad), wheel."""
from __future__ import annotations

from . import winapi as w

# buttons bitmask
BTN_LEFT = 1
BTN_RIGHT = 2
BTN_MIDDLE = 4

_DOWN = {BTN_LEFT: w.MOUSEEVENTF_LEFTDOWN, BTN_RIGHT: w.MOUSEEVENTF_RIGHTDOWN, BTN_MIDDLE: w.MOUSEEVENTF_MIDDLEDOWN}
_UP = {BTN_LEFT: w.MOUSEEVENTF_LEFTUP, BTN_RIGHT: w.MOUSEEVENTF_RIGHTUP, BTN_MIDDLE: w.MOUSEEVENTF_MIDDLEUP}


def _mi(dx: int, dy: int, data: int, flags: int) -> w.INPUT:
    mi = w.MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
    return w.INPUT(type=w.INPUT_MOUSE, u=w._INPUTunion(mi=mi))


def move_abs(nx: float, ny: float) -> None:
    """Virtual desktop bo'yicha absolute harakat. nx, ny ∈ [0..1]."""
    # Absolute koordinatalar 0..65535 oralig'iga normalizatsiya qilinadi.
    ax = int(max(0.0, min(1.0, nx)) * 65535)
    ay = int(max(0.0, min(1.0, ny)) * 65535)
    flags = w.MOUSEEVENTF_MOVE | w.MOUSEEVENTF_ABSOLUTE | w.MOUSEEVENTF_VIRTUALDESK
    w.send_inputs(_mi(ax, ay, 0, flags))


def move_rel(dx: int, dy: int) -> None:
    """Touchpad rejimi: nisbiy harakat (piksel)."""
    if dx or dy:
        w.send_inputs(_mi(dx, dy, 0, w.MOUSEEVENTF_MOVE))


def button(btn: int, down: bool) -> None:
    table = _DOWN if down else _UP
    flag = table.get(btn)
    if flag:
        w.send_inputs(_mi(0, 0, 0, flag))


def scroll(dy: int, dx: int = 0) -> None:
    """Wheel. dy>0 — yuqoriga, dx>0 — o'ngga."""
    seq = []
    if dy:
        seq.append(_mi(0, 0, dy * w.WHEEL_DELTA, w.MOUSEEVENTF_WHEEL))
    if dx:
        seq.append(_mi(0, 0, dx * w.WHEEL_DELTA, w.MOUSEEVENTF_HWHEEL))
    if seq:
        w.send_inputs(*seq)
