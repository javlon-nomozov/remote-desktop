"""Faza 1 lokal demo — tarmoqsiz. Windows'da ishlaydi.

Nimani tekshiradi:
  1) Click-through indikator ko'rinadimi va bosib bo'lmaydimi (tagidagi element bosiladi).
  2) Haqiqiy multi-touch injection → Windows gesturalarni o'zi taniydimi:
     tap, 2-barmoq scroll, pinch-zoom, 3-barmoq swipe (Task View).
  3) Ekran capture backend va tezligi.

Ishlatish (PowerShell, server-win papkasida venv faollashtirilgan holda):

  python test_harness.py indicator --mode dot
  python test_harness.py indicator --mode watermark
  python test_harness.py gesture tap
  python test_harness.py gesture scroll
  python test_harness.py gesture pinch --direction out
  python test_harness.py gesture swipe3
  python test_harness.py capture --seconds 3
  python test_harness.py all

Maslahat: gestura demolaridan oldin 3 soniya beriladi — shu vaqtda sinamoqchi bo'lgan
oynani (masalan Photos/Xaritalar/brauzer) bosib, fokusga oling.
"""
from __future__ import annotations

import argparse
import time

from capture import ScreenCapture
from input import winapi
from input.touch import Contact, TouchInjector
from overlay import Indicator


def _countdown(sec: int, msg: str) -> None:
    print(msg)
    for i in range(sec, 0, -1):
        print(f"  {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  boshladi!      ")


def _center() -> tuple[int, int]:
    w, h = winapi.primary_screen_size()
    return w // 2, h // 2


def _play(inj: TouchInjector, frames: list[list[Contact]], frame_delay: float = 0.012) -> None:
    for f in frames:
        inj.update(f)
        time.sleep(frame_delay)


# --- Gesturalar ----------------------------------------------------------
def gesture_tap(inj: TouchInjector) -> None:
    cx, cy = _center()
    _play(inj, [[Contact(0, cx, cy, "down")]])
    time.sleep(0.05)
    _play(inj, [[Contact(0, cx, cy, "up")]])
    print("tap -> bajarildi")


def gesture_scroll(inj: TouchInjector, dist: int = 300, steps: int = 25) -> None:
    cx, cy = _center()
    dx = 60
    # ikkala barmoq pastdan boshlab yuqoriga (kontent pastga scroll bo'ladi)
    y0 = cy + dist // 2
    frames = [[Contact(0, cx - dx, y0, "down"), Contact(1, cx + dx, y0, "down")]]
    for i in range(1, steps + 1):
        y = y0 - int(dist * i / steps)
        frames.append([Contact(0, cx - dx, y, "move"), Contact(1, cx + dx, y, "move")])
    yend = y0 - dist
    frames.append([Contact(0, cx - dx, yend, "up"), Contact(1, cx + dx, yend, "up")])
    _play(inj, frames)
    print("2-barmoq scroll -> bajarildi")


def gesture_pinch(inj: TouchInjector, direction: str = "out", steps: int = 25) -> None:
    cx, cy = _center()
    near, far = 60, 320
    if direction == "out":  # zoom in: yaqin -> uzoq
        start, end = near, far
    else:  # zoom out: uzoq -> yaqin
        start, end = far, near
    frames = [[Contact(0, cx - start, cy, "down"), Contact(1, cx + start, cy, "down")]]
    for i in range(1, steps + 1):
        d = start + int((end - start) * i / steps)
        frames.append([Contact(0, cx - d, cy, "move"), Contact(1, cx + d, cy, "move")])
    frames.append([Contact(0, cx - end, cy, "up"), Contact(1, cx + end, cy, "up")])
    _play(inj, frames)
    print(f"pinch ({direction}) -> bajarildi")


def gesture_swipe3(inj: TouchInjector, dist: int = 360, steps: int = 22) -> None:
    cx, cy = _center()
    offs = [-90, 0, 90]
    y0 = cy + dist // 2
    frames = [[Contact(i, cx + o, y0, "down") for i, o in enumerate(offs)]]
    for s in range(1, steps + 1):
        y = y0 - int(dist * s / steps)
        frames.append([Contact(i, cx + o, y, "move") for i, o in enumerate(offs)])
    yend = y0 - dist
    frames.append([Contact(i, cx + o, yend, "up") for i, o in enumerate(offs)])
    _play(inj, frames)
    print("3-barmoq swipe (Task View) -> bajarildi")


# --- Capture test --------------------------------------------------------
def test_capture(seconds: int) -> None:
    cap = ScreenCapture(target_fps=60)
    print(f"capture backend: {cap.backend}")
    n = 0
    t0 = time.perf_counter()
    last_shape = None
    while time.perf_counter() - t0 < seconds:
        f = cap.grab()
        if f is not None:
            n += 1
            last_shape = f.shape
    dt = time.perf_counter() - t0
    cap.close()
    print(f"kadrlar: {n}  |  ~{n/dt:.1f} fps  |  o'lcham: {last_shape}")


# --- CLI -----------------------------------------------------------------
def main() -> None:
    winapi.set_dpi_aware()
    p = argparse.ArgumentParser(description="Faza 1 lokal demo")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("indicator", help="indikatorni ko'rsatish (Ctrl+C bilan to'xtatish)")
    pi.add_argument("--mode", choices=["dot", "watermark"], default="dot")

    pg = sub.add_parser("gesture", help="bitta gesturani sinash")
    pg.add_argument("name", choices=["tap", "scroll", "pinch", "swipe3"])
    pg.add_argument("--direction", choices=["in", "out"], default="out")

    pc = sub.add_parser("capture", help="capture tezligini o'lchash")
    pc.add_argument("--seconds", type=int, default=3)

    sub.add_parser("all", help="indikator + barcha gesturalarni ketma-ket sinash")

    args = p.parse_args()

    if args.cmd == "indicator":
        ind = Indicator(mode=args.mode)
        ind.start()
        print(f"indikator ({args.mode}) ko'rsatildi. Uning ustidan bosib ko'ring — "
              f"bosish tagidagi oynaga o'tishi kerak. To'xtatish: Ctrl+C")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            ind.stop()
            print("\nto'xtatildi.")

    elif args.cmd == "gesture":
        inj = TouchInjector()
        _countdown(3, f"'{args.name}' gesturasi. Sinov oynasini fokusga oling...")
        if args.name == "tap":
            gesture_tap(inj)
        elif args.name == "scroll":
            gesture_scroll(inj)
        elif args.name == "pinch":
            gesture_pinch(inj, args.direction)
        elif args.name == "swipe3":
            gesture_swipe3(inj)

    elif args.cmd == "capture":
        test_capture(args.seconds)

    elif args.cmd == "all":
        ind = Indicator(mode="dot")
        ind.start()
        print("indikator yoqildi (burchakdagi qizil nuqta).")
        inj = TouchInjector()
        for name, fn in [
            ("tap", lambda: gesture_tap(inj)),
            ("2-barmoq scroll", lambda: gesture_scroll(inj)),
            ("pinch (zoom in)", lambda: gesture_pinch(inj, "out")),
            ("3-barmoq swipe", lambda: gesture_swipe3(inj)),
        ]:
            _countdown(3, f"keyingi: {name}. Mos oynani fokusga oling...")
            fn()
            time.sleep(0.6)
        print("\ncapture testi:")
        test_capture(3)
        ind.stop()
        print("tugadi.")


if __name__ == "__main__":
    main()
