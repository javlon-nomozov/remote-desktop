"""InputController — protokol (PROTOCOL.md §2) hodisalarini qurilmaga qo'llaydi.

Viewer normalizatsiyalangan [0..1] koordinatalar yuboradi; bu yerda ular ekran pikseliga
map qilinadi. Touch hodisalari `TouchInjector` ga, mouse/keyboard esa SendInput ga boradi.
"""
from __future__ import annotations

from . import keyboard, mouse, winapi
from .touch import Contact, TouchInjector


class InputController:
    def __init__(self) -> None:
        winapi.set_dpi_aware()
        self.vx, self.vy, self.vw, self.vh = winapi.virtual_screen_rect()
        self._touch: TouchInjector | None = None  # kerak bo'lganda yaratamiz
        self._btn_state = 0  # bosilgan tugmalar bitmask

    # --- koordinata map -------------------------------------------------
    def _to_px(self, nx: float, ny: float) -> tuple[int, int]:
        return self.vx + int(nx * self.vw), self.vy + int(ny * self.vh)

    def _touch_injector(self) -> TouchInjector:
        if self._touch is None:
            self._touch = TouchInjector(max_contacts=10)
        return self._touch

    # --- asosiy kirish nuqtasi -----------------------------------------
    def handle(self, msg: dict) -> None:
        """Bitta protokol xabarini qo'llaydi. Noma'lum tur — e'tiborsiz qoldiriladi."""
        t = msg.get("t")
        if t == "touch":
            self._on_touch(msg)
        elif t == "mouse":
            self._on_mouse(msg)
        elif t == "scroll":
            mouse.scroll(int(msg.get("dy", 0)), int(msg.get("dx", 0)))
        elif t == "key":
            self._on_key(msg)
        elif t == "text":
            keyboard.type_text(str(msg.get("value", "")))

    # --- touch ----------------------------------------------------------
    def _on_touch(self, msg: dict) -> None:
        contacts: list[Contact] = []
        for c in msg.get("contacts", []):
            px, py = self._to_px(float(c["x"]), float(c["y"]))
            contacts.append(
                Contact(
                    id=int(c["id"]),
                    x=px,
                    y=py,
                    state=c.get("state", "move"),
                    pressure=float(c.get("pressure", 0.5)),
                )
            )
        if contacts:
            self._touch_injector().update(contacts)

    # --- mouse / touchpad ----------------------------------------------
    def _on_mouse(self, msg: dict) -> None:
        mode = msg.get("mode", "abs")
        if mode == "rel":
            mouse.move_rel(int(msg.get("dx", 0) * self.vw), int(msg.get("dy", 0) * self.vh))
        else:
            mouse.move_abs(float(msg.get("x", 0.0)), float(msg.get("y", 0.0)))

        # tugma o'zgarishlarini aniqlab, down/up yuboramiz
        new = int(msg.get("buttons", self._btn_state))
        changed = new ^ self._btn_state
        for btn in (mouse.BTN_LEFT, mouse.BTN_RIGHT, mouse.BTN_MIDDLE):
            if changed & btn:
                mouse.button(btn, down=bool(new & btn))
        self._btn_state = new

    # --- keyboard -------------------------------------------------------
    def _on_key(self, msg: dict) -> None:
        keyboard.key(str(msg.get("code", "")), bool(msg.get("down", False)))

    # --- tozalash -------------------------------------------------------
    def reset(self) -> None:
        """Sessiya oxirida: barcha tugma/barmoqlarni qo'yib yuborish."""
        for btn in (mouse.BTN_LEFT, mouse.BTN_RIGHT, mouse.BTN_MIDDLE):
            if self._btn_state & btn:
                mouse.button(btn, down=False)
        self._btn_state = 0
        if self._touch is not None:
            self._touch.cancel_all()
