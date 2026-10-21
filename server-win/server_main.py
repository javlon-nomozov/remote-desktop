"""Server (boshqariladigan Windows mashina) — to'liq ishga tushirish.

Ekranni stream qiladi, viewerдан input qabul qiladi, ko'rinadigan "faol" indikatorni
yoqadi. Yopilsa — sessiya to'xtaydi (fon xizmati yo'q).

Ishlatish:
    python server_main.py                      # indikator=dot, input yoqilgan
    python server_main.py --no-input           # xavfsiz sinov (faqat ko'rsatish, injeksiyasiz)
    python server_main.py --indicator watermark
    python server_main.py --port 8765 --fps 25 --quality 65

Viewer: viewer-win (yoki keyin Android).
"""
from __future__ import annotations

import argparse

from input import InputController
from net import StreamServer
from overlay import Indicator


def main() -> None:
    p = argparse.ArgumentParser(description="Remote desktop server (Faza 2 MVP)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--quality", type=int, default=60)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--indicator", choices=["dot", "watermark", "off"], default="dot")
    p.add_argument("--no-input", action="store_true",
                   help="input injeksiyasini o'chirish (faqat ekran ko'rsatish; xavfsiz sinov)")
    args = p.parse_args()

    controller = None if args.no_input else InputController()

    def on_input(data: dict) -> None:
        if controller is not None:
            controller.handle(data)

    indicator = None
    if args.indicator != "off":
        indicator = Indicator(mode=args.indicator)
        indicator.start()

    server = StreamServer(
        host=args.host, port=args.port, fps=args.fps,
        quality=args.quality, scale=args.scale, on_input=on_input,
    )
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\nto'xtatildi.")
    finally:
        if indicator is not None:
            indicator.stop()
        if controller is not None:
            controller.reset()


if __name__ == "__main__":
    main()
