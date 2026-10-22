# Wire Protocol (v0)

Barcha komponentlar (server-win, viewer-win, viewer-android, backend) shu protokolni
ishlatadi. Transport: **WebRTC** (video track + DataChannel). Fallback: WebSocket + JPEG.
Xabarlar — JSON (DataChannel/signaling). Video — alohida media track (H.264).

## 1. Signaling (viewer ↔ backend ↔ server)

Backend `wss` broker, `room` = `session_id`. Xabarlar:

```jsonc
{ "t": "join",  "role": "server|viewer", "device_id": "...", "token": "..." }
{ "t": "peers", "members": ["serverId", "viewerId"] }
{ "t": "offer", "sdp": "..." }
{ "t": "answer","sdp": "..." }
{ "t": "ice",   "candidate": { ... } }
{ "t": "bye",   "reason": "..." }
{ "t": "error", "code": "unauthorized|expired|busy", "msg": "..." }
```

Litsenziya: `join` dagi `token` backendда tekshiriladi. Obuna faol bo'lmasa →
`error: expired`, ulanish yopiladi.

## 2. Input events (viewer → server, DataChannel)

Koordinatalar **normalizatsiya qilingan** [0.0, 1.0] (ekran o'lchamidan mustaqil).
Server ularni o'z ekran pikseliga map qiladi.

### 2.1 Touch (eng muhim — multi-finger)
Barmoqlar massivi; har bir `id` bitta barmoqni butun gestura davomida kuzatadi.
Server bularni **haqiqiy touch kontakt** sifatida injekt qiladi → OS gesturani (pinch,
2-finger scroll, 3/4-finger swipe) **o'zi taniydi**.

```jsonc
{
  "t": "touch",
  "contacts": [
    { "id": 0, "x": 0.42, "y": 0.55, "state": "down|move|up", "pressure": 0.5 },
    { "id": 1, "x": 0.60, "y": 0.55, "state": "down" }
  ]
}
```

- `state`: `down` (yangi), `move` (yangilash), `up` (ko'tarildi).
- `pressure`: ixtiyoriy [0..1] (default 0.5).

### 2.2 Mouse / touchpad
```jsonc
{ "t": "mouse", "x": 0.5, "y": 0.5, "buttons": 1, "mode": "abs" }   // touchscreen tap/drag
{ "t": "mouse", "dx": 0.01, "dy": -0.02, "buttons": 0, "mode": "rel" } // touchpad (relative)
{ "t": "scroll", "dx": 0, "dy": 3 }                                   // wheel
```
`buttons` — bitmask: 1=left, 2=right, 4=middle.

### 2.3 Gesture (ko'p barmoqli — viewer aniqlaydi)
3/4 barmoqli swipe'ni viewer (Android) aniqlaydi va semantik buyruq yuboradi; server uni
Windows tugma kombinatsiyasiga map qiladi (touchscreen OS-gesturasiga tayanmaydi).
```jsonc
{ "t": "gesture", "name": "switch_next" }
```
Nomlar: `taskview`, `showdesktop`, `switch_next`, `switch_prev`, `desktop_next`, `desktop_prev`.
Odatiy map (4-barmoq L/R = oyna almashtirish): [`input/controller.py` → `GESTURES`].

### 2.4 Keyboard
```jsonc
{ "t": "key", "code": "KeyA", "down": true, "mods": ["ctrl","shift"] }
{ "t": "text", "value": "salom" }   // IME/unicode kiritish
```
`code` — [W3C `KeyboardEvent.code`](https://www.w3.org/TR/uievents-code/) qiymati; server
uni Windows virtual-key / scancode ga map qiladi.

## 3. Control (ikki tomonlama, DataChannel)
```jsonc
{ "t": "indicator", "mode": "dot|watermark|off" }   // faol indikator rejimi
{ "t": "quality",   "fps": 30, "bitrate": 4000000, "scale": 1.0 }
{ "t": "disconnect" }                                // viewer uzadi
{ "t": "stat", "rtt_ms": 24, "fps": 30 }             // telemetriya
```

> Eslatma: server ilova yopilsa — sessiya o'ladi (fon xizmati yo'q). Indikator doim
> ko'rinadi; `off` faqat test/admin uchun.
