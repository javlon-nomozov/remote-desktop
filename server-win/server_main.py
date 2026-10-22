"""Server (boshqariladigan Windows mashina) — konsol versiyasi (sinov/dev uchun; asosiysi server_gui).

Ekranni stream qiladi: internet orqali doimiy kod (--relay) va lokal tarmoq (ws 47865 + UDP
47866 topish). Notanish telefon ulanmoqchi bo'lsa konsolda ruxsat so'raladi. Indikator telefon ulangan
paytda ko'rinadi. Yopilsa — sessiya to'xtaydi (fon xizmati yo'q).

Ishlatish:
    python server_main.py                                  # faqat lokal tarmoq
    python server_main.py --relay wss://xxx.up.railway.app # + internet orqali kod
    python server_main.py --no-input                       # xavfsiz sinov (injeksiyasiz)
    python server_main.py --indicator watermark --fps 25 --quality 65
"""
from __future__ import annotations

import argparse
import threading

from input import InputController
from net import REJECT, HostService, Viewer
from overlay import Indicator

_DURATIONS = {"1": 1800, "2": 3600, "3": 86400, "4": None}
_ask_lock = threading.Lock()


def ask_console(v: Viewer):
    with _ask_lock:
        print(f"\n>>> «{v.label}» ({v.via}) ulanmoqchi.")
        ans = input("    Muddat: 1=30 daq, 2=1 soat, 3=1 kun, 4=cheksiz, boshqa=rad > ").strip()
    return _DURATIONS[ans] if ans in _DURATIONS else REJECT


def main() -> None:
    p = argparse.ArgumentParser(description="Remote desktop server (konsol)")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--quality", type=int, default=60)
    p.add_argument("--indicator", choices=["dot", "watermark", "off"], default="dot")
    p.add_argument("--no-input", action="store_true",
                   help="input injeksiyasini o'chirish (faqat ekran ko'rsatish; xavfsiz sinov)")
    p.add_argument("--relay", default="",
                   help="backend relay URL (masalan ws://localhost:8000 yoki wss://xxx.up.railway.app)")
    args = p.parse_args()

    controller = None if args.no_input else InputController()
    indicator = Indicator(mode=args.indicator) if args.indicator != "off" else None

    def on_input(data: dict) -> None:
        if controller is not None:
            controller.handle(data)

    def on_event(kind: str, v: Viewer) -> None:
        print(f"[server] {kind}: {v.label}")
        if indicator is not None:
            indicator.start() if kind == "connected" else indicator.stop()
        if kind == "disconnected" and controller is not None:
            controller.reset()

    svc = HostService(args.relay, fps=args.fps, quality=args.quality, on_input=on_input,
                      ask_permission=ask_console, on_event=on_event)
    svc.start()
    print("Ishlamoqda. To'xtatish: Ctrl+C")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nto'xtatildi.")
    finally:
        svc.stop()
        if indicator is not None:
            indicator.stop()
        if controller is not None:
            controller.reset()


if __name__ == "__main__":
    main()
