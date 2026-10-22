"""Remote Server — zamonaviy GUI (CustomTkinter).

Terminalsiz (exe --windowed): faqat bitta oyna. Yopilsa — toza to'xtaydi. Backend manzili
ilovaга singdirilgan (app_config.BACKEND_URL) — foydalanuvchi hech narsa kiritmaydi, faqat
"Boshlash" bosadi va unique KOD ko'rinadi.
"""
from __future__ import annotations

import os
import queue
import sys
import threading

import customtkinter as ctk

import app_config
from input import InputController, winapi
from net import RelayHost
from overlay import Indicator

ACCENT = "#1a1acf"
ACCENT_HOVER = "#1414a0"
GREEN = "#22c55e"
GREEN_DIM = "#15803d"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


class ServerApp:
    def __init__(self) -> None:
        winapi.set_dpi_aware()
        self.root = ctk.CTk()
        self.root.title(app_config.APP_NAME)
        self.root.geometry("460x520")
        self.root.resizable(False, False)

        self.q: queue.Queue = queue.Queue()
        self.controller: InputController | None = None
        self.indicator: Indicator | None = None
        self.server_obj: RelayHost | None = None
        self.worker: threading.Thread | None = None
        self.running = False
        self._pulse_on = False

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll)

    def _build(self) -> None:
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(pady=(20, 6))
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(resource_path("logo.jpg")), size=(52, 52))
            ctk.CTkLabel(header, image=img, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass
        ctk.CTkLabel(header, text=app_config.APP_NAME,
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        card = ctk.CTkFrame(self.root, corner_radius=16)
        card.pack(fill="x", padx=20, pady=12)

        fr1 = ctk.CTkFrame(card, fg_color="transparent")
        fr1.pack(fill="x", padx=16, pady=(16, 0))
        self.fps_lbl = ctk.CTkLabel(fr1, text="FPS: 20", width=80, anchor="w")
        self.fps_lbl.pack(side="left")
        self.fps = ctk.CTkSlider(fr1, from_=5, to=60, number_of_steps=55,
                                 command=lambda v: self.fps_lbl.configure(text=f"FPS: {int(v)}"))
        self.fps.set(20)
        self.fps.pack(side="right", fill="x", expand=True, padx=(8, 0))

        fr2 = ctk.CTkFrame(card, fg_color="transparent")
        fr2.pack(fill="x", padx=16, pady=(8, 0))
        self.q_lbl = ctk.CTkLabel(fr2, text="Sifat: 60", width=80, anchor="w")
        self.q_lbl.pack(side="left")
        self.quality = ctk.CTkSlider(fr2, from_=20, to=90, number_of_steps=70,
                                     command=lambda v: self.q_lbl.configure(text=f"Sifat: {int(v)}"))
        self.quality.set(60)
        self.quality.pack(side="right", fill="x", expand=True, padx=(8, 0))

        fr3 = ctk.CTkFrame(card, fg_color="transparent")
        fr3.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkLabel(fr3, text="Indikator", width=80, anchor="w").pack(side="left")
        self.ind = ctk.CTkOptionMenu(fr3, values=["dot", "watermark", "off"])
        self.ind.set("dot")
        self.ind.pack(side="right")

        self.btn = ctk.CTkButton(self.root, text="Boshlash", height=48,
                                 font=ctk.CTkFont(size=16, weight="bold"),
                                 fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                 cursor="hand2", command=self._toggle)
        self.btn.pack(fill="x", padx=20, pady=(6, 12))

        statusf = ctk.CTkFrame(self.root, fg_color="transparent")
        statusf.pack()
        self.dot = ctk.CTkLabel(statusf, text="●", text_color="#555", font=ctk.CTkFont(size=16))
        self.dot.pack(side="left", padx=(0, 6))
        self.status = ctk.CTkLabel(statusf, text="To'xtagan", text_color="#999")
        self.status.pack(side="left")

        ctk.CTkLabel(self.root, text="Ulanish kodi:", text_color="#888").pack(pady=(12, 0))
        self.code_lbl = ctk.CTkLabel(self.root, text="— — —",
                                     font=ctk.CTkFont(family="Consolas", size=30, weight="bold"),
                                     text_color=ACCENT)
        self.code_lbl.pack()
        self.hint = ctk.CTkLabel(self.root, text="Telefonда shu kodni kiriting",
                                 text_color="#888", wraplength=400)
        self.hint.pack()

    def _toggle(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        fps = int(self.fps.get())
        quality = int(self.quality.get())

        self.controller = InputController()
        if self.ind.get() != "off":
            self.indicator = Indicator(mode=self.ind.get())
            self.indicator.attach(self.root)

        def on_code(d: dict) -> None:
            self.q.put(("code", d.get("pretty", d.get("code", ""))))

        def on_status(s: str) -> None:
            self.q.put(("status", s))

        self.server_obj = RelayHost(app_config.BACKEND_URL, fps=fps, quality=quality,
                                    on_input=self.controller.handle,
                                    on_code=on_code, on_status=on_status)
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()
        self.running = True
        self.btn.configure(text="To'xtatish", fg_color="#b02020", hover_color="#8a1818")
        self.status.configure(text="Ulanmoqda...", text_color=GREEN)
        self.code_lbl.configure(text="...")
        self._lock(True)
        self._pulse_on = True
        self._pulse()

    def _run_worker(self) -> None:
        try:
            self.server_obj.run()
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", str(e)))
        self.q.put(("stopped", None))

    def _stop(self) -> None:
        try:
            if self.server_obj is not None:
                self.server_obj.stop()
        except Exception:
            pass
        self._cleanup()

    def _cleanup(self) -> None:
        self.running = False
        self._pulse_on = False
        if self.indicator is not None:
            self.indicator.detach()
            self.indicator = None
        if self.controller is not None:
            try:
                self.controller.reset()
            except Exception:
                pass
            self.controller = None
        self.server_obj = None
        self.btn.configure(text="Boshlash", fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.status.configure(text="To'xtagan", text_color="#999")
        self.dot.configure(text_color="#555")
        self.code_lbl.configure(text="— — —")
        self._lock(False)

    def _lock(self, lock: bool) -> None:
        st = "disabled" if lock else "normal"
        self.fps.configure(state=st)
        self.quality.configure(state=st)
        self.ind.configure(state=st)

    def _pulse(self) -> None:
        if not self._pulse_on:
            return
        self.dot.configure(text_color=GREEN if self.dot.cget("text_color") != GREEN else GREEN_DIM)
        self.root.after(550, self._pulse)

    def _poll(self) -> None:
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "code":
                    self.code_lbl.configure(text=val)
                    self.status.configure(text="Tayyor — kodni kiriting", text_color=GREEN)
                elif kind == "status":
                    if val == "viewer_connected":
                        self.status.configure(text="Viewer ulandi ✓", text_color=GREEN)
                    elif val == "viewer_disconnected":
                        self.status.configure(text="Tayyor (kutilmoqda)", text_color=GREEN)
                elif kind == "error":
                    self.status.configure(text="Xato: " + val, text_color="#e05555")
                    self.code_lbl.configure(text="— — —")
                elif kind == "stopped":
                    if self.running:
                        self._cleanup()
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ServerApp().run()


if __name__ == "__main__":
    main()
