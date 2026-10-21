"""Windows viewer (boshqaruvchi) — Faza 2 MVP.

Serverga ulanadi, JPEG oqimini ko'rsatadi, sichqoncha/klaviaturani ushlab, input
hodisalarini (PROTOCOL.md §2) serverga yuboradi.

Rejimlar:
  - abs (standart): oynadagi joy -> ekranda o'sha nuqta (touchscreen tap/drag kabi)
  - touchpad (F9): nisbiy harakat (yaqinda bo'lganda touchpad kabi)
  Esc -> barcha tugmalarni qo'yib yuboradi.

Ishlatish:
    python main.py                      # ws://localhost:8765
    python main.py --host 192.168.1.50  # LAN'dagi server
    python main.py --port 8765
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import tkinter as tk
from io import BytesIO

from PIL import Image, ImageTk
from websockets.sync.client import connect

# Tk keysym -> W3C KeyboardEvent.code (maxsus tugmalar)
_SPECIAL = {
    "Return": "Enter", "BackSpace": "Backspace", "Escape": "Escape", "Tab": "Tab",
    "space": "Space", "Left": "ArrowLeft", "Right": "ArrowRight", "Up": "ArrowUp",
    "Down": "ArrowDown", "Home": "Home", "End": "End", "Prior": "PageUp",
    "Next": "PageDown", "Delete": "Delete", "Insert": "Insert", "Caps_Lock": "CapsLock",
    "Shift_L": "ShiftLeft", "Shift_R": "ShiftRight", "Control_L": "ControlLeft",
    "Control_R": "ControlRight", "Alt_L": "AltLeft", "Alt_R": "AltRight",
    "Super_L": "MetaLeft", "Super_R": "MetaRight",
}
for _i in range(1, 13):
    _SPECIAL[f"F{_i}"] = f"F{_i}"


def tk_to_code(keysym: str) -> str | None:
    if keysym in _SPECIAL:
        return _SPECIAL[keysym]
    if len(keysym) == 1:
        ch = keysym
        if ch.isalpha():
            return "Key" + ch.upper()
        if ch.isdigit():
            return "Digit" + ch
    return None


class Viewer:
    def __init__(self, host: str, port: int) -> None:
        self.uri = f"ws://{host}:{port}"
        self.ws = None
        self._latest: bytes | None = None
        self._lock = threading.Lock()
        self._buttons = 0
        self._mode = "abs"  # yoki "touchpad"
        self._last_motion = 0.0
        self._last_pos: tuple[int, int] | None = None
        self._running = True

        self.root = tk.Tk()
        self.root.title("Remote Viewer — ulanmoqda...")
        self.root.geometry("1100x650")
        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._imgtk = None
        self._img_id = self.canvas.create_text(
            550, 325, text="Ulanmoqda...", fill="white", font=("Segoe UI", 16)
        )
        self._bind()

    # --- tarmoq ---------------------------------------------------------
    def connect_and_run(self) -> None:
        threading.Thread(target=self._net_loop, daemon=True).start()
        self.root.after(30, self._render)
        self.root.mainloop()
        self._running = False

    def _net_loop(self) -> None:
        try:
            with connect(self.uri, max_size=None, open_timeout=10) as ws:
                self.ws = ws
                hello = ws.recv()
                if isinstance(hello, str):
                    info = json.loads(hello)
                    self.root.title(f"Remote Viewer — {info.get('w')}x{info.get('h')} "
                                    f"@ {info.get('fps')}fps  [abs]  (F9: touchpad, Esc: release)")
                while self._running:
                    msg = ws.recv()
                    if isinstance(msg, (bytes, bytearray)):
                        with self._lock:
                            self._latest = bytes(msg)
        except Exception as e:
            self._set_status(f"Ulanish xatosi: {e}")

    def _send(self, obj: dict) -> None:
        ws = self.ws
        if ws is None:
            return
        try:
            ws.send(json.dumps(obj))
        except Exception:
            pass

    # --- render ---------------------------------------------------------
    def _render(self) -> None:
        if not self._running:
            return
        with self._lock:
            data = self._latest
            self._latest = None
        if data is not None:
            try:
                img = Image.open(BytesIO(data))
                cw = max(1, self.canvas.winfo_width())
                ch = max(1, self.canvas.winfo_height())
                img = img.resize((cw, ch))
                self._imgtk = ImageTk.PhotoImage(img)
                self.canvas.delete("all")
                self._img_id = self.canvas.create_image(0, 0, anchor="nw", image=self._imgtk)
            except Exception:
                pass
        self.root.after(15, self._render)

    def _set_status(self, text: str) -> None:
        try:
            self.canvas.delete("all")
            self.canvas.create_text(self.canvas.winfo_width() // 2,
                                    self.canvas.winfo_height() // 2,
                                    text=text, fill="white", font=("Segoe UI", 14))
        except Exception:
            pass

    # --- input ----------------------------------------------------------
    def _bind(self) -> None:
        c = self.canvas
        c.bind("<Motion>", self._on_motion)
        for b in (1, 2, 3):
            c.bind(f"<Button-{b}>", self._on_button)
            c.bind(f"<ButtonRelease-{b}>", self._on_button)
        c.bind("<MouseWheel>", self._on_wheel)
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.bind("<F9>", self._toggle_mode)
        self.root.bind("<Escape>", self._release_all)
        c.focus_set()

    def _norm(self, x: int, y: int) -> tuple[float, float]:
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        return min(1.0, max(0.0, x / cw)), min(1.0, max(0.0, y / ch))

    def _on_motion(self, e) -> None:
        now = time.perf_counter()
        if now - self._last_motion < 0.016:  # ~60/s throttle
            return
        self._last_motion = now
        if self._mode == "touchpad":
            if self._last_pos is not None:
                dx = (e.x - self._last_pos[0]) / max(1, self.canvas.winfo_width())
                dy = (e.y - self._last_pos[1]) / max(1, self.canvas.winfo_height())
                self._send({"t": "mouse", "dx": dx, "dy": dy, "buttons": self._buttons, "mode": "rel"})
            self._last_pos = (e.x, e.y)
        else:
            nx, ny = self._norm(e.x, e.y)
            self._send({"t": "mouse", "x": nx, "y": ny, "buttons": self._buttons, "mode": "abs"})

    def _on_button(self, e) -> None:
        bit = {1: 1, 3: 2, 2: 4}.get(e.num, 0)
        if e.type == tk.EventType.ButtonPress:
            self._buttons |= bit
        else:
            self._buttons &= ~bit
        self.canvas.focus_set()
        nx, ny = self._norm(e.x, e.y)
        if self._mode == "abs":
            self._send({"t": "mouse", "x": nx, "y": ny, "buttons": self._buttons, "mode": "abs"})
        else:
            self._send({"t": "mouse", "dx": 0, "dy": 0, "buttons": self._buttons, "mode": "rel"})

    def _on_wheel(self, e) -> None:
        self._send({"t": "scroll", "dy": 1 if e.delta > 0 else -1, "dx": 0})

    def _on_key_press(self, e) -> None:
        if e.keysym in ("F9",):
            return
        code = tk_to_code(e.keysym)
        if code:
            self._send({"t": "key", "code": code, "down": True})
        elif e.char and e.char.isprintable():
            self._send({"t": "text", "value": e.char})

    def _on_key_release(self, e) -> None:
        code = tk_to_code(e.keysym)
        if code:
            self._send({"t": "key", "code": code, "down": False})

    def _toggle_mode(self, _e=None) -> None:
        self._mode = "touchpad" if self._mode == "abs" else "abs"
        self._last_pos = None
        title = self.root.title()
        base = title.split("  [")[0]
        self.root.title(f"{base}  [{self._mode}]  (F9: almashtirish, Esc: release)")

    def _release_all(self, _e=None) -> None:
        self._buttons = 0
        self._send({"t": "mouse", "x": 0.5, "y": 0.5, "buttons": 0, "mode": "abs"})


def main() -> None:
    p = argparse.ArgumentParser(description="Remote desktop viewer (Faza 2 MVP)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    Viewer(args.host, args.port).connect_and_run()


if __name__ == "__main__":
    main()
