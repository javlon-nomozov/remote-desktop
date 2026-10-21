# viewer-win — Windows viewer (Faza 2 MVP)

Boshqaruvchi Windows mashina. Serverga ulanib, ekranni ko'rsatadi va sichqoncha/klaviaturani
yuboradi. (Android viewer — Faza 5.)

## O'rnatish
```powershell
cd viewer-win
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Ishlatish
```powershell
python main.py                       # ws://localhost:8765 (bir mashinada sinov)
python main.py --host 192.168.1.50   # LAN'dagi server IP
```

Avval server tomonini ishga tushiring (boshqa mashinada yoki shu mashinada):
`server-win/server_main.py` (qarang [server-win/README.md](../server-win/README.md)).

## Boshqaruv
- Sichqoncha harakати/bosish → serverga yuboriladi.
- **F9** — rejim almashtirish: `abs` (oynadagi joy = ekrandagi joy, touchscreen kabi) ↔
  `touchpad` (nisbiy harakat, yaqinda bo'lganda).
- **Esc** — barcha tugmalarni qo'yib yuborish.
- Klaviatura — fokus viewer oynasida bo'lsa, tugmalar serverga uzatiladi.

## Eslatma
Bu MVP transporti — WebSocket + JPEG. Past kechikishli H.264/WebRTC keyingi bosqich;
input protokoli (PROTOCOL.md) o'zgarmaydi, shuning uchun viewer kodi deyarli o'zgarishsiz
qoladi.
