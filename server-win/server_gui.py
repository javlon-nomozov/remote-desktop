"""Remote Server — zamonaviy GUI (CustomTkinter).

Terminalsiz (exe --windowed): faqat bitta oyna. Yopilsa — toza to'xtaydi. Boshqa yopiladigan
terminal yo'q, shuning uchun "terminalni yopib qo'yish -> crash" xavfi yo'q.

Arxitektura: GUI asosiy threadда; server (RelayHost/StreamServer) ishchi threadда;
ular orasida queue. Ekranда yashil click-through indikator (attach orqali, bitta Tk).
"""
from __future__ import annotations

import os
import queue
import socket
import sys
import threading

import customtkinter as ctk

from input import InputController, winapi
from net import RelayHost, StreamServer
from overlay import Indicator

LAN_PORT = 8765
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
        self.root.title("Remote Server")
        self.root.geometry("480x560")
        self.root.resizable(False, False)

        self.q: queue.Queue = queue.Queue()
        self.controller: InputController | None = None
        self.indicator: Indicator | None = None
        self.server_obj = None
        self.worker: threading.Thread | None = None
        self.running = False
        self._pulse_on = False

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll)

    # --- UI ------------------------------------------------------------
    def _build(self) -> None:
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(pady=(18, 6))
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(resource_path("logo.jpg")), size=(52, 52))
            ctk.CTkLabel(header, image=img, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass
        ctk.CTkLabel(header, text="Remote Server",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        card = ctk.CTkFrame(self.root, corner_radius=16)
        card.pack(fill="x", padx=20, pady=10)

        self.mode = ctk.CTkSegmentedButton(
            card, values=["Internet (kod)", "LAN (IP)"], command=self._mode_changed
        )
        self.mode.set("Internet (kod)")
        self.mode.pack(fill="x", padx=16, pady=(16, 8))

        self.relay = ctk.CTkEntry(card, placeholder_text="Backend manzili (wss://...)")
        self.relay.pack(fill="x", padx=16, pady=6)

        # FPS slider
        fr1 = ctk.CTkFrame(card, fg_color="transparent")
        fr1.pack(fill="x", padx=16, pady=(10, 0))
        self.fps_lbl = ctk.CTkLabel(fr1, text="FPS: 20", width=80, anchor="w")
        self.fps_lbl.pack(side="left")
        self.fps = ctk.CTkSlider(fr1, from_=5, to=60, number_of_steps=55,
                                 command=lambda v: self.fps_lbl.configure(text=f"FPS: {int(v)}"))
        self.fps.set(20)
        self.fps.pack(side="right", fill="x", expand=True, padx=(8, 0))

        # Quality slider
        fr2 = ctk.CTkFrame(card, fg_color="transparent")
        fr2.pack(fill="x", padx=16, pady=(6, 0))
        self.q_lbl = ctk.CTkLabel(fr2, text="Sifat: 60", width=80, anchor="w")
        self.q_lbl.pack(side="left")
        self.quality = ctk.CTkSlider(fr2, from_=20, to=90, number_of_steps=70,
                                     command=lambda v: self.q_lbl.configure(text=f"Sifat: {int(v)}"))
        self.quality.set(60)
        self.quality.pack(side="right", fill="x", expand=True, padx=(8, 0))

        # Indicator
        fr3 = ctk.CTkFrame(card, fg_color="transparent")
        fr3.pack(fill="x", padx=16, pady=(6, 16))
        ctk.CTkLabel(fr3, text="Indikator", width=80, anchor="w").pack(side="left")
        self.ind = ctk.CTkOptionMenu(fr3, values=["dot", "watermark", "off"])
        self.ind.set("dot")
        self.ind.pack(side="right")

        self.btn = ctk.CTkButton(self.root, text="Boshlash", height=46,
                                 font=ctk.CTkFont(size=16, weight="bold"),
                                 fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                 cursor="hand2", command=self._toggle)
        self.btn.pack(fill="x", padx=20, pady=(6, 10))

        statusf = ctk.CTkFrame(self.root, fg_color="transparent")
        statusf.pack()
        self.dot = ctk.CTkLabel(statusf, text="●", text_color="#555",
                                font=ctk.CTkFont(size=16))
        self.dot.pack(side="left", padx=(0, 6))
        self.status = ctk.CTkLabel(statusf, text="To'xtagan", text_color="#999")
        self.status.pack(side="left")

        self.code_lbl = ctk.CTkLabel(self.root, text="",
                                     font=ctk.CTkFont(family="Consolas", size=30, weight="bold"),
                                     text_color=ACCENT)
        self.code_lbl.pack(pady=(10, 2))
        self.hint = ctk.CTkLabel(self.root, text="", text_color="#888", wraplength=420)
        self.hint.pack()
        self._mode_changed()

    def _is_relay(self) -> bool:
        return self.mode.get().startswith("Internet")

    def _mode_changed(self, _=None) -> None:
        if self._is_relay():
            self.relay.configure(state="normal")
        else:
            self.relay.configure(state="disabled")

    # --- start/stop ----------------------------------------------------
    def _toggle(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        fps = int(self.fps.get())
        quality = int(self.quality.get())

        self.controller = InputController()
        on_input = self.controller.handle

        if self.ind.get() != "off":
            self.indicator = Indicator(mode=self.ind.get())
            self.indicator.attach(self.root)

        def on_code(d: dict) -> None:
            self.q.put(("code", d.get("pretty", d.get("code", ""))))

        def on_status(s: str) -> None:
            self.q.put(("status", s))

        if self._is_relay():
            url = self.relay.get().strip()
            if not url or url in ("wss://", "ws://"):
                self.status.configure(text="Backend manzilini kiriting", text_color="#e05555")
                self._cleanup()
                return
            self.server_obj = RelayHost(url, fps=fps, quality=quality,
                                        on_input=on_input, on_code=on_code, on_status=on_status)
            target = self.server_obj.run
        else:
            self.server_obj = StreamServer(fps=fps, quality=quality,
                                           on_input=on_input, on_status=on_status)
            target = self.server_obj.serve
            ip = self._lan_ip()
            self.code_lbl.configure(text=ip)
            self.hint.configure(text=f"Telefonда LAN: IP {ip}  ·  port {LAN_PORT}")

        self.worker = threading.Thread(target=self._run_worker, args=(target,), daemon=True)
        self.worker.start()
        self.running = True
        self.btn.configure(text="To'xtatish", fg_color="#b02020", hover_color="#8a1818")
        self.status.configure(text="Ishlamoqda...", text_color=GREEN)
        self._lock(True)
        self._pulse_on = True
        self._pulse()

    def _run_worker(self, target) -> None:
        try:
            target()
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
        self.code_lbl.configure(text="")
        self.hint.configure(text="")
        self._lock(False)

    def _lock(self, lock: bool) -> None:
        st = "disabled" if lock else "normal"
        self.fps.configure(state=st)
        self.quality.configure(state=st)
        self.ind.configure(state=st)
        self.mode.configure(state=st)
        if lock:
            self.relay.configure(state="disabled")
        else:
            self._mode_changed()

    # --- animatsiya (pulslovchi holat nuqtasi) -------------------------
    def _pulse(self) -> None:
        if not self._pulse_on:
            return
        self.dot.configure(text_color=GREEN if self.dot.cget("text_color") != GREEN else GREEN_DIM)
        self.root.after(550, self._pulse)

    # --- queue ---------------------------------------------------------
    def _poll(self) -> None:
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "code":
                    self.code_lbl.configure(text=val)
                    self.hint.configure(text="Telefonда shu kodni kiriting")
                elif kind == "status":
                    if val == "viewer_connected":
                        self.status.configure(text="Viewer ulandi ✓", text_color=GREEN)
                    elif val == "viewer_disconnected":
                        self.status.configure(text="Ishlamoqda (kutilmoqda)", text_color=GREEN)
                elif kind == "error":
                    self.status.configure(text="Xato: " + val, text_color="#e05555")
                elif kind == "stopped":
                    if self.running:
                        self._cleanup()
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _lan_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ServerApp().run()


if __name__ == "__main__":
    main()
