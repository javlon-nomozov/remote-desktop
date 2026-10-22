"""Host sessiya yadrosi — relay (internet) va LAN uchun umumiy.

Vazifalari:
  - ruxsat: ishonchli telefonlar ro'yxati (trusted.json) va notanish qurilma uchun so'rov
    (`ask_permission` — GUI oynasi yoki konsol);
  - bitta faol viewer: kadrlarni yuborish (pause/resume), inputni FAQAT ruxsatdan keyin qo'llash;
  - ishonch muddati tugaganda sessiyani to'xtatish.

Transport (relay_client / stream_server) viewer ulanganda `Viewer` yaratib `viewer_connected`,
har bir xabar uchun `viewer_message`, uzilganda `viewer_disconnected` chaqiradi.

host -> viewer matn xabarlari: waiting_approval, approved{until}, rejected, expired, kicked, busy,
hello{w,h,fps}; keyin binary JPEG kadrlar.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from io import BytesIO
from typing import Callable, Optional

from PIL import Image

from capture import ScreenCapture

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RemoteServer")

REJECT = False  # ask_permission natijasi: rad etildi. Aks holda soniyalar (int) yoki None = cheksiz.


def _load_json(name: str, default):
    try:
        with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(name: str, data) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    path = os.path.join(APP_DIR, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def host_identity() -> tuple[str, str]:
    """Kompyuterning doimiy relay kodi va secret'i (birinchi chaqiruvda yaratiladi)."""
    d = _load_json("host.json", {})
    hid, sec = str(d.get("id", "")), str(d.get("secret", ""))
    if not (len(hid) == 9 and hid.isdigit() and hid[0] != "0" and len(sec) >= 16):
        hid = str(secrets.randbelow(9 * 10**8) + 10**8)
        sec = secrets.token_hex(16)
        _save_json("host.json", {"id": hid, "secret": sec})
    return hid, sec


def encode_jpeg(frame, quality: int, scale: float = 1.0) -> bytes:
    """BGR kadr -> JPEG baytlar."""
    img = Image.fromarray(frame[:, :, ::-1])
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class TrustStore:
    """Ishonchli telefonlar: device_id -> {name, until (epoch) | None = cheksiz}."""

    FILE = "trusted.json"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict] = _load_json(self.FILE, {})

    def _prune(self) -> None:
        now = time.time()
        dead = [k for k, v in self._items.items() if v.get("until") is not None and v["until"] <= now]
        for k in dead:
            del self._items[k]
        if dead:
            _save_json(self.FILE, self._items)

    def get(self, device_id: str) -> Optional[dict]:
        if not device_id:
            return None
        with self._lock:
            self._prune()
            return self._items.get(device_id)

    def grant(self, device_id: str, name: str, seconds: Optional[int]) -> Optional[float]:
        until = None if seconds is None else time.time() + seconds
        with self._lock:
            self._items[device_id] = {"name": name, "until": until}
            _save_json(self.FILE, self._items)
        return until

    def revoke(self, device_id: str) -> None:
        with self._lock:
            if self._items.pop(device_id, None) is not None:
                _save_json(self.FILE, self._items)

    def items(self) -> list[tuple[str, str, Optional[float]]]:
        with self._lock:
            self._prune()
            return [(k, v.get("name", ""), v.get("until")) for k, v in self._items.items()]


class Viewer:
    """Bitta ulangan telefon (transportdan mustaqil)."""

    def __init__(
        self,
        send_text: Callable[[str], None],
        send_bytes: Callable[[bytes], None],
        close: Callable[[], None],
        device_id: str,
        device_name: str,
        user: str = "",
        via: str = "",
    ) -> None:
        self._send_text = send_text
        self.send_bytes = send_bytes
        self.close = close
        self.device_id = device_id
        self.device_name = device_name or "Noma'lum qurilma"
        self.user = user
        self.via = via  # "internet" | "lan"
        self.alive = True
        self.approved = False
        self.paused = False
        self.until: Optional[float] = None

    @property
    def label(self) -> str:
        return f"{self.device_name} ({self.user})" if self.user else self.device_name

    def send(self, obj: dict) -> None:
        try:
            self._send_text(json.dumps(obj))
        except Exception:
            pass


class HostCore:
    def __init__(
        self,
        fps: int = 20,
        quality: int = 60,
        on_input: Optional[Callable[[dict], None]] = None,
        ask_permission: Optional[Callable[[Viewer], object]] = None,
        on_event: Optional[Callable[[str, Viewer], None]] = None,
    ) -> None:
        self.fps = fps  # ishlab turganda ham o'zgartirish mumkin
        self.quality = quality
        self.on_input = on_input
        self.ask_permission = ask_permission
        self.on_event = on_event
        self.trust = TrustStore()
        self._lock = threading.Lock()
        self._active: Optional[Viewer] = None

    @property
    def active(self) -> Optional[Viewer]:
        return self._active

    def _emit(self, kind: str, v: Viewer) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, v)
            except Exception as e:
                print(f"[core] event xato: {e}")

    # --- transportdan chaqiriladi ---------------------------------------
    def viewer_connected(self, v: Viewer) -> None:
        with self._lock:
            cur = self._active
            if cur is not None and cur.alive:
                if v.device_id and v.device_id == cur.device_id:
                    self._drop(cur)  # o'sha telefonning eski (o'lik) ulanishi
                else:
                    v.send({"t": "busy"})
                    v.close()
                    return
            self._active = v
        print(f"[core] ulanish so'rovi: {v.label} [{v.via}]")
        t = self.trust.get(v.device_id)
        if t is not None:
            self._approve(v, t.get("until"))
            return
        v.send({"t": "waiting_approval"})
        threading.Thread(target=self._ask, args=(v,), daemon=True).start()

    def viewer_message(self, v: Viewer, data: dict) -> None:
        t = data.get("t")
        if t == "pause":
            v.paused = True
            return
        if t == "resume":
            v.paused = False
            return
        if not (v.approved and v.alive and self._active is v):
            return  # ruxsatsiz input qo'llanmaydi
        if v.until is not None and time.time() >= v.until:
            return
        if self.on_input is not None:
            try:
                self.on_input(data)
            except Exception as e:
                print(f"[core] input xato: {e}")

    def viewer_disconnected(self, v: Viewer) -> None:
        with self._lock:
            if self._active is v:
                self._drop(v)
            else:
                v.alive = False

    # --- GUI'dan chaqiriladi --------------------------------------------
    def kick(self) -> None:
        """Faol ulanishni uzadi va shu telefonning ishonchini bekor qiladi."""
        v = self._active
        if v is None:
            return
        self.trust.revoke(v.device_id)
        v.send({"t": "kicked"})
        with self._lock:
            if self._active is v:
                self._drop(v)
        v.close()

    def stop(self) -> None:
        v = self._active
        if v is not None:
            with self._lock:
                self._drop(v)
            v.close()

    # --- ichki ------------------------------------------------------------
    def _drop(self, v: Viewer) -> None:
        """_lock ostida chaqiriladi."""
        v.alive = False
        if self._active is v:
            self._active = None
        self._emit("disconnected", v)

    def _ask(self, v: Viewer) -> None:
        res = REJECT
        if self.ask_permission is not None:
            try:
                res = self.ask_permission(v)
            except Exception as e:
                print(f"[core] ruxsat so'rovi xato: {e}")
        if not v.alive or self._active is not v:
            return
        if res is REJECT:
            v.send({"t": "rejected"})
            with self._lock:
                if self._active is v:
                    self._drop(v)
            v.close()
            return
        seconds = None if res is None else int(res)
        if v.device_id:
            until = self.trust.grant(v.device_id, v.label, seconds)
        else:
            until = None if seconds is None else time.time() + seconds
        self._approve(v, until)

    def _approve(self, v: Viewer, until: Optional[float]) -> None:
        v.until = until
        v.approved = True
        v.send({"t": "approved", "until": until})
        self._emit("connected", v)
        threading.Thread(target=self._stream, args=(v,), daemon=True).start()

    def _stream(self, v: Viewer) -> None:
        cap = ScreenCapture(target_fps=self.fps)
        try:
            first = None
            for _ in range(40):
                first = cap.grab()
                if first is not None:
                    break
                time.sleep(0.02)
            if first is None:
                return
            v.send({"t": "hello", "w": int(first.shape[1]), "h": int(first.shape[0]), "fps": self.fps})
            while v.alive and self._active is v:
                if v.until is not None and time.time() >= v.until:
                    print(f"[core] ishonch muddati tugadi: {v.label}")
                    self.trust.revoke(v.device_id)
                    v.send({"t": "expired"})
                    with self._lock:
                        if self._active is v:
                            self._drop(v)
                    v.close()
                    break
                if v.paused:
                    time.sleep(0.1)
                    continue
                t0 = time.perf_counter()
                frame = cap.grab()
                if frame is not None:
                    try:
                        v.send_bytes(encode_jpeg(frame, self.quality))
                    except Exception:
                        break
                dt = time.perf_counter() - t0
                interval = 1.0 / max(1, self.fps)
                if dt < interval:
                    time.sleep(interval - dt)
        finally:
            cap.close()
