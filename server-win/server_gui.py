"""Remote Server — zamonaviy GUI (CustomTkinter).

Terminalsiz (exe --windowed): faqat bitta oyna. Ochilishi bilan xizmat o'zi boshlanadi:
  - internet orqali DOIMIY kod (backend manzili app_config.BACKEND_URL ga singdirilgan);
  - lokal tarmoq (bitta Wi-Fi / USB modem): telefonlar ro'yxati, kompyuterdan tanlab ulash.
Notanish telefon ulanmoqchi bo'lsa ruxsat va muddat so'raladi (30 daq / 1 soat / 1 kun / cheksiz);
muddat ichida shu telefon so'rovsiz ulanadi. `--autostart` (Windows bilan birga) — oyna yig'ilgan
holda ochiladi. Yopilsa — toza to'xtaydi.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time

import customtkinter as ctk

import app_config
import autostart
from input import InputController, winapi
from net import REJECT, HostService, Viewer
from net.discovery import lan_ips
from net.host_core import _load_json, _save_json
from overlay import Indicator

ACCENT = "#1a1acf"
ACCENT_HOVER = "#1414a0"
GREEN = "#22c55e"
GREEN_DIM = "#15803d"
RED = "#b02020"
RED_HOVER = "#8a1818"
MUTED = "#888"

# Ruxsat (ishonch) muddatlari: nom -> soniya (None = cheksiz)
DURATIONS: dict[str, int | None] = {"30 daqiqa": 1800, "1 soat": 3600, "1 kun": 86400, "Cheksiz": None}
DEFAULT_DURATION = "1 soat"
ASK_TIMEOUT = 60  # ruxsat oynasi shuncha soniyada javobsiz bo'lsa — rad

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def fmt_left(until: float | None) -> str:
    if until is None:
        return "cheksiz"
    left = int(until - time.time())
    if left <= 0:
        return "tugadi"
    if left < 3600:
        return f"{max(1, left // 60)} daq qoldi"
    if left < 86400:
        return f"{left // 3600} soat {left % 3600 // 60} daq qoldi"
    return time.strftime("%d.%m %H:%M", time.localtime(until)) + " gacha"


class PermissionDialog(ctk.CTkToplevel):
    """Notanish telefon ulanmoqchi: ruxsat + muddat."""

    def __init__(self, master, v: Viewer, on_done) -> None:
        super().__init__(master)
        self._on_done = on_done
        self._done = False
        self._left = ASK_TIMEOUT
        self.title("Ulanish so'rovi")
        self.geometry("440x290")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: self.finish(REJECT))

        ctk.CTkLabel(self, text="Ulanish so'rovi", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(18, 6))
        via = "internet" if v.via == "internet" else "lokal tarmoq"
        ctk.CTkLabel(self, text=f"«{v.label}» {via} orqali\nkompyuteringizga ulanmoqchi.",
                     wraplength=400, justify="center").pack(pady=(0, 12))
        ctk.CTkLabel(self, text="Ruxsat muddati:", text_color=MUTED).pack()
        self.dur = ctk.CTkSegmentedButton(self, values=list(DURATIONS))
        self.dur.set(DEFAULT_DURATION)
        self.dur.pack(pady=(4, 14))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Ruxsat berish", fg_color=GREEN_DIM, hover_color="#166534", width=150,
                      command=lambda: self.finish(DURATIONS[self.dur.get()])).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Rad etish", fg_color=RED, hover_color=RED_HOVER, width=150,
                      command=lambda: self.finish(REJECT)).pack(side="left", padx=6)
        self.timer = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.timer.pack(pady=(10, 0))
        self.after(150, self._focus)
        self.after(300, lambda: ServerApp._set_icon(self))
        self._tick()

    def _focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.bell()
        except Exception:
            pass

    def _tick(self) -> None:
        if self._done:
            return
        if self._left <= 0:
            self.finish(REJECT)
            return
        self.timer.configure(text=f"{self._left} s ichida javob bo'lmasa rad etiladi")
        self._left -= 1
        self.after(1000, self._tick)

    def finish(self, result) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._on_done(result)
        finally:
            self.destroy()


class ServerApp:
    def __init__(self, autostarted: bool = False) -> None:
        winapi.set_dpi_aware()
        self.cfg = {"fps": 20, "quality": 60, "indicator": "dot", "autostart": True}
        self.cfg.update(_load_json("settings.json", {}))

        self.root = ctk.CTk()
        self.root.title(app_config.APP_NAME)
        self.root.geometry("480x740")
        self.root.minsize(440, 520)
        # CTk o'z ikonkasini ~200 ms keyin qo'yadi — logotipni undan keyin o'rnatamiz
        self.root.after(300, lambda: self._set_icon(self.root))

        self.q: queue.Queue = queue.Queue()
        self.controller: InputController | None = None
        self.indicator: Indicator | None = None
        self.service: HostService | None = None
        self.running = False
        self._dialogs: dict[int, PermissionDialog] = {}
        self._phone_ids: tuple | None = None  # None — hali chizilmagan
        self._phone_dur: dict[str, ctk.StringVar] = {}
        self._trust_snapshot: list | None = None

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll)
        self.root.after(1000, self._refresh)

        if self.cfg["autostart"] and autostart.exe_path():
            threading.Thread(target=autostart.enable, daemon=True).start()  # yo'lni yangilab turamiz
        self._start()
        if autostarted:
            self.root.after(300, self.root.iconify)

    # --- UI ---------------------------------------------------------------
    @staticmethod
    def _set_icon(win) -> None:
        try:
            win.iconbitmap(resource_path("logo.ico"))
        except Exception:
            pass

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.pack(fill="x", padx=14, pady=7)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                     anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        return card

    def _build(self) -> None:
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(pady=(14, 4))
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(resource_path("logo.jpg")), size=(44, 44))
            ctk.CTkLabel(header, image=img, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass
        ctk.CTkLabel(header, text=app_config.APP_NAME,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        body = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4)

        # Holat
        st = self._card(body, "Holat")
        ctk.CTkLabel(st, text="Internet orqali ulanish kodi:", text_color=MUTED,
                     anchor="w").pack(fill="x", padx=14)
        self.code_lbl = ctk.CTkLabel(st, text="— — —", text_color=ACCENT,
                                     font=ctk.CTkFont(family="Consolas", size=30, weight="bold"))
        self.code_lbl.pack(pady=(0, 2))
        self.relay_lbl = ctk.CTkLabel(st, text="", text_color=MUTED)
        self.relay_lbl.pack()
        self.lan_lbl = ctk.CTkLabel(st, text="", text_color=MUTED, wraplength=420)
        self.lan_lbl.pack(pady=(2, 6))
        # Windows Firewall lokal tarmoqni bloklasa — ogohlantirish + ruxsat tugmasi (UAC)
        self.fw_box = ctk.CTkFrame(st, fg_color="#3a2a10")
        ctk.CTkLabel(self.fw_box, text="Windows Firewall telefonning Wi-Fi / USB orqali ulanishini bloklayapti.",
                     text_color="#e0a030", wraplength=280, justify="left").pack(side="left", padx=10, pady=8)
        self.fw_btn = ctk.CTkButton(self.fw_box, text="Ruxsat berish", width=110, command=self._allow_firewall)
        self.fw_btn.pack(side="right", padx=10)
        self._fw_anchor = ctk.CTkFrame(st, fg_color="transparent", height=0)  # fw_box shu joyga chiqadi
        self._fw_anchor.pack(fill="x")
        sess = ctk.CTkFrame(st, fg_color="transparent")
        sess.pack(fill="x", padx=14, pady=(0, 12))
        self.dot = ctk.CTkLabel(sess, text="●", text_color="#555", font=ctk.CTkFont(size=16))
        self.dot.pack(side="left", padx=(0, 6))
        self.sess_lbl = ctk.CTkLabel(sess, text="Hech kim ulanmagan", anchor="w")
        self.sess_lbl.pack(side="left", fill="x", expand=True)
        self.kick_btn = ctk.CTkButton(sess, text="Uzish", width=80, fg_color=RED, hover_color=RED_HOVER,
                                      command=self._kick)

        # Tarmoqdagi telefonlar
        ph = self._card(body, "Tarmoqdagi telefonlar")
        ctk.CTkLabel(ph, text="Bitta Wi-Fi yoki USB modemda ilovasi ochiq telefonlar. "
                              "Tanlang va «Ulash» bosing.",
                     text_color=MUTED, wraplength=420, justify="left", anchor="w").pack(fill="x", padx=14)
        self.phones_box = ctk.CTkFrame(ph, fg_color="transparent")
        self.phones_box.pack(fill="x", padx=10, pady=(4, 10))

        # Ishonchli telefonlar
        tr = self._card(body, "Ishonchli telefonlar")
        ctk.CTkLabel(tr, text="Muddat ichida bu telefonlar so'rovsiz ulanadi.",
                     text_color=MUTED, anchor="w").pack(fill="x", padx=14)
        self.trust_box = ctk.CTkFrame(tr, fg_color="transparent")
        self.trust_box.pack(fill="x", padx=10, pady=(4, 10))

        # Sozlamalar
        se = self._card(body, "Sozlamalar")
        fr1 = ctk.CTkFrame(se, fg_color="transparent")
        fr1.pack(fill="x", padx=14, pady=(4, 0))
        self.fps_lbl = ctk.CTkLabel(fr1, text=f"FPS: {self.cfg['fps']}", width=80, anchor="w")
        self.fps_lbl.pack(side="left")
        self.fps = ctk.CTkSlider(fr1, from_=5, to=60, number_of_steps=55, command=self._on_fps)
        self.fps.set(self.cfg["fps"])
        self.fps.pack(side="right", fill="x", expand=True, padx=(8, 0))
        fr2 = ctk.CTkFrame(se, fg_color="transparent")
        fr2.pack(fill="x", padx=14, pady=(8, 0))
        self.q_lbl = ctk.CTkLabel(fr2, text=f"Sifat: {self.cfg['quality']}", width=80, anchor="w")
        self.q_lbl.pack(side="left")
        self.quality = ctk.CTkSlider(fr2, from_=20, to=90, number_of_steps=70, command=self._on_quality)
        self.quality.set(self.cfg["quality"])
        self.quality.pack(side="right", fill="x", expand=True, padx=(8, 0))
        fr3 = ctk.CTkFrame(se, fg_color="transparent")
        fr3.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(fr3, text="Indikator", width=80, anchor="w").pack(side="left")
        self.ind = ctk.CTkOptionMenu(fr3, values=["dot", "watermark", "off"], command=self._on_indicator)
        self.ind.set(self.cfg["indicator"])
        self.ind.pack(side="right")
        self.auto_sw = ctk.CTkSwitch(se, text="Windows bilan birga ishga tushsin", command=self._on_autostart)
        if self.cfg["autostart"]:
            self.auto_sw.select()
        if not autostart.exe_path():
            self.auto_sw.configure(state="disabled", text="Windows bilan birga ishga tushsin (faqat exe)")
        self.auto_sw.pack(anchor="w", padx=14, pady=(10, 12))

        self.btn = ctk.CTkButton(self.root, text="To'xtatish", height=44,
                                 font=ctk.CTkFont(size=15, weight="bold"),
                                 fg_color=RED, hover_color=RED_HOVER, command=self._toggle)
        self.btn.pack(fill="x", padx=18, pady=(6, 12))

    # --- sozlamalar (ishlab turganda ham) ----------------------------------
    def _save_cfg(self) -> None:
        try:
            _save_json("settings.json", self.cfg)
        except Exception as e:
            print(f"[gui] sozlama saqlanmadi: {e}")

    def _on_fps(self, v) -> None:
        self.cfg["fps"] = int(v)
        self.fps_lbl.configure(text=f"FPS: {int(v)}")
        if self.service:
            self.service.core.fps = int(v)
        self._save_cfg()

    def _on_quality(self, v) -> None:
        self.cfg["quality"] = int(v)
        self.q_lbl.configure(text=f"Sifat: {int(v)}")
        if self.service:
            self.service.core.quality = int(v)
        self._save_cfg()

    def _on_indicator(self, mode: str) -> None:
        self.cfg["indicator"] = mode
        self._save_cfg()
        cur = self.service.core.active if self.service else None
        self._hide_indicator()
        if cur is not None and cur.approved:
            self._show_indicator()

    def _on_autostart(self) -> None:
        on = bool(self.auto_sw.get())
        self.cfg["autostart"] = on
        self._save_cfg()
        if on:
            threading.Thread(target=autostart.enable, daemon=True).start()
        else:
            autostart.disable()

    # --- xizmat -----------------------------------------------------------
    def _toggle(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        self.controller = InputController()
        self.service = HostService(
            app_config.BACKEND_URL,
            fps=self.cfg["fps"], quality=self.cfg["quality"],
            on_input=self.controller.handle,
            ask_permission=self._ask_permission,
            on_event=lambda kind, v: self.q.put(("event", kind, v)),
            on_code=lambda d: self.q.put(("code", d.get("pretty", d.get("code", "")))),
            on_relay_status=lambda s: self.q.put(("relay", s)),
        )
        self.service.start()
        self.running = True
        self.btn.configure(text="To'xtatish", fg_color=RED, hover_color=RED_HOVER)
        self.relay_lbl.configure(text="Internetga ulanmoqda...", text_color=MUTED)
        self.root.after(800, self._update_lan_label)
        self.root.after(1500, self._check_firewall)

    def _stop(self) -> None:
        if self.service is not None:
            try:
                self.service.stop()
            except Exception:
                pass
            self.service = None
        for d in list(self._dialogs.values()):
            d.finish(REJECT)
        self._hide_indicator()
        if self.controller is not None:
            try:
                self.controller.reset()
            except Exception:
                pass
            self.controller = None
        self.running = False
        self.btn.configure(text="Boshlash", fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.code_lbl.configure(text="— — —")
        self.relay_lbl.configure(text="To'xtatilgan", text_color=MUTED)
        self.lan_lbl.configure(text="")
        self._set_session(None)

    def _update_lan_label(self) -> None:
        if not self.running or self.service is None:
            return
        if self.service.lan_error:
            self.lan_lbl.configure(text=f"Lokal tarmoq ishlamayapti: {self.service.lan_error}",
                                   text_color="#e05555")
        else:
            ips = ", ".join(lan_ips()) or "tarmoq yo'q"
            self.lan_lbl.configure(text=f"Lokal: {self.service.discovery.name} · {ips}", text_color=MUTED)

    def _check_firewall(self) -> None:
        threading.Thread(target=lambda: self.q.put(("fw", autostart.lan_firewall_ok())), daemon=True).start()

    def _allow_firewall(self) -> None:
        self.fw_btn.configure(state="disabled", text="Kutilmoqda...")
        threading.Thread(target=lambda: self.q.put(("fw", autostart.allow_lan_firewall())), daemon=True).start()

    def _kick(self) -> None:
        if self.service is not None:
            self.service.core.kick()

    # --- ruxsat (xizmat thread'idan chaqiriladi) ----------------------------
    def _ask_permission(self, v: Viewer):
        box = {"res": REJECT, "ev": threading.Event()}
        self.q.put(("ask", v, box))
        box["ev"].wait(ASK_TIMEOUT + 5)
        return box["res"]

    def _open_dialog(self, v: Viewer, box: dict) -> None:
        def done(res) -> None:
            self._dialogs.pop(id(v), None)
            box["res"] = res
            box["ev"].set()

        if self.root.state() == "iconic":
            self.root.deiconify()
        self._dialogs[id(v)] = PermissionDialog(self.root, v, done)

    # --- indikator ---------------------------------------------------------
    def _show_indicator(self) -> None:
        if self.indicator is None and self.cfg["indicator"] != "off":
            self.indicator = Indicator(mode=self.cfg["indicator"])
            self.indicator.attach(self.root)

    def _hide_indicator(self) -> None:
        if self.indicator is not None:
            self.indicator.detach()
            self.indicator = None

    # --- holat yangilash ----------------------------------------------------
    def _set_session(self, v: Viewer | None) -> None:
        if v is None:
            self.dot.configure(text_color="#555")
            self.sess_lbl.configure(text="Hech kim ulanmagan")
            self.kick_btn.pack_forget()
        else:
            self.dot.configure(text_color=GREEN)
            self.sess_lbl.configure(text=f"Ulangan: {v.label} — {fmt_left(v.until)}")
            if not self.kick_btn.winfo_ismapped():
                self.kick_btn.pack(side="right")

    def _poll(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "code":
                    self.code_lbl.configure(text=item[1])
                elif kind == "fw":
                    self.fw_btn.configure(state="normal", text="Ruxsat berish")
                    if item[1] is False:
                        if not self.fw_box.winfo_ismapped():
                            self.fw_box.pack(fill="x", padx=14, pady=(0, 8), before=self._fw_anchor)
                    else:
                        self.fw_box.pack_forget()
                elif kind == "relay":
                    if item[1] == "online":
                        self.relay_lbl.configure(text="Internet: ulangan", text_color=GREEN)
                    else:
                        self.relay_lbl.configure(text="Internet yo'q — qayta urinilmoqda (lokal tarmoq ishlaydi)",
                                                 text_color="#e0a030")
                elif kind == "ask":
                    _, v, box = item
                    if v.alive:
                        self._open_dialog(v, box)
                    else:
                        box["ev"].set()
                elif kind == "event":
                    _, ev, v = item
                    if ev == "connected":
                        self._set_session(v)
                        self._show_indicator()
                    elif ev == "disconnected":
                        d = self._dialogs.get(id(v))
                        if d is not None:
                            d.finish(REJECT)  # so'rov kutayotgan telefon ketib qoldi
                        cur = self.service.core.active if self.service else None
                        if cur is None or not cur.approved:
                            self._set_session(None)
                            self._hide_indicator()
                            if self.controller is not None:
                                try:
                                    self.controller.reset()  # bosilib qolgan tugma/barmoqlar
                                except Exception:
                                    pass
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _refresh(self) -> None:
        """Har soniyada: qolgan vaqt, telefonlar ro'yxati, ishonchli telefonlar."""
        try:
            svc = self.service
            cur = svc.core.active if svc else None
            if cur is not None and cur.approved and cur.alive:
                self._set_session(cur)
            self._refresh_phones(svc)
            self._refresh_trusted(svc)
        except Exception as e:
            print(f"[gui] refresh xato: {e}")
        self.root.after(1000, self._refresh)

    def _refresh_phones(self, svc: HostService | None) -> None:
        phones = svc.discovery.phones() if svc else []
        ids = tuple(sorted(p["device_id"] for p in phones))
        if ids == self._phone_ids:
            return
        self._phone_ids = ids
        for w in self.phones_box.winfo_children():
            w.destroy()
        if not phones:
            ctk.CTkLabel(self.phones_box, text="Hozircha telefon topilmadi.",
                         text_color="#666").pack(anchor="w", padx=4)
            return
        for p in phones:
            dev = p["device_id"]
            row = ctk.CTkFrame(self.phones_box)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"{p['name']}\n{p['ip']}", justify="left",
                         anchor="w").pack(side="left", padx=8, pady=4)
            var = self._phone_dur.setdefault(dev, ctk.StringVar(value=DEFAULT_DURATION))
            ctk.CTkButton(row, text="Ulash", width=70,
                          command=lambda d=dev, n=p["name"], vr=var: self._connect_phone(d, n, vr.get())
                          ).pack(side="right", padx=6)
            ctk.CTkOptionMenu(row, values=list(DURATIONS), variable=var, width=110).pack(side="right")

    def _connect_phone(self, device_id: str, name: str, dur: str) -> None:
        if self.service is None:
            return
        ok = self.service.connect_phone(device_id, name, DURATIONS[dur])
        if not ok:
            self.sess_lbl.configure(text="Telefonga taklif yuborilmadi (tarmoqni tekshiring)")
        self._trust_snapshot = None  # ro'yxatni yangilash

    def _refresh_trusted(self, svc: HostService | None) -> None:
        items = sorted(svc.core.trust.items(), key=lambda x: x[1]) if svc else []
        snap = [(k, n, fmt_left(u)) for k, n, u in items]
        if snap == self._trust_snapshot:
            return
        self._trust_snapshot = snap
        for w in self.trust_box.winfo_children():
            w.destroy()
        if not snap:
            ctk.CTkLabel(self.trust_box, text="Yo'q.", text_color="#666").pack(anchor="w", padx=4)
            return
        for dev, name, left in snap:
            row = ctk.CTkFrame(self.trust_box)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"{name}\n{left}", justify="left", anchor="w").pack(side="left", padx=8, pady=4)
            ctk.CTkButton(row, text="O'chirish", width=80, fg_color="#444", hover_color="#333",
                          command=lambda d=dev: self._revoke(d)).pack(side="right", padx=6)

    def _revoke(self, device_id: str) -> None:
        svc = self.service
        if svc is None:
            return
        cur = svc.core.active
        if cur is not None and cur.device_id == device_id:
            svc.core.kick()
        else:
            svc.core.trust.revoke(device_id)
        self._trust_snapshot = None

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def _redirect_output_to_log() -> None:
    """Windowed exe'da konsol yo'q (sys.stdout = None) — print/xatolar log faylga yozilsin.
    Fayl: %LOCALAPPDATA%\\RemoteServer\\server.log (1 MB dan oshsa yangidan boshlanadi)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RemoteServer")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "server.log")
        mode = "w" if os.path.exists(path) and os.path.getsize(path) > 1_000_000 else "a"
        f = open(path, mode, encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
    except Exception:
        pass


def main() -> None:
    _redirect_output_to_log()
    if not autostart.acquire_single_instance():
        autostart.focus_existing(app_config.APP_NAME)  # dastur allaqachon ochiq
        return
    ServerApp(autostarted="--autostart" in sys.argv).run()


if __name__ == "__main__":
    main()
