# Remote Desktop (AnyDesk/RustDesk uslubida)

O'z qurilmalaring uchun masofaviy boshqaruv mahsuloti. Windows laptop = **server**
(boshqariladigan), viewer = **Android (Kotlin)** yoki **Windows**. Android'da haqiqiy
touchscreen kabi (2/3/4 barmoqli native gesturalar), ekran klaviaturasi va touchpad rejimi.

Ishlab turganini bildirish uchun ekranda **ko'rinadigan "faol" indikatori** bo'ladi
(click-through — ishga xalaqit bermaydi). Server ilovasini mashina egasi o'zi ishga tushiradi
va yopsa — ish to'xtaydi.

## Tarkib (monorepo)

| Papka | Vazifasi |
|-------|----------|
| `protocol/` | Umumiy wire-protokol (signaling + input event sxema) |
| `server-win/` | Windows server: ekran capture, touch/keyboard injection, indikator |
| `viewer-win/` | Windows viewer (pipeline'ni tekshirish uchun) |
| `viewer-android/` | Kotlin native app (Android Studio loyihasi) |
| `backend/` | Railway: FastAPI signaling + REST + admin panel |
| `bot/` | aiogram Telegram bot (ro'yxat, linklar, to'lov) |
| `turn/` | coturn (NAT traversal) konfiguratsiyasi |

## Holati (progress)

- [x] **Faza 0** — protokol va repo asosi
- [x] **Faza 1** — Windows server yadrosi: touch injection, click-through indikator, capture
      (lokal test harness bilan)
- [x] **Faza 2** — streaming + Windows viewer (LAN). MVP transport = WebSocket + JPEG
      (`server-win/server_main.py` + `viewer-win/main.py`), uchma-uch tasdiqlandi. Past
      kechikishli H.264/WebRTC — keyingi optimizatsiya (input protokoli o'zgarmaydi)
- [x] **Faza 3** — backend: FastAPI + SQLModel/Postgres + SQLAdmin admin panel
      (signaling endpointlari Faza 2 da qo'shiladi)
- [x] **Faza 4** — Telegram bot (aiogram) + qo'lda to'lov oqimi (karta→chek→tasdiq+summa),
      referal + promo. To'lov mantig'i `backend/app/payments.py` da (skillga ajratishga tayyor)
- [x] **Faza 5** — Android native viewer (Kotlin) skeleti: `viewer-android/` — WS+JPEG
      protokoli, multi-touch gesturalar, klaviatura, touchpad. Android Studio'da build qilinadi
      (bu muhitда SDK yo'q, APK sinalmagan)
- [ ] **Faza 6** — indikator sayqal, limitlar, hardening

## Hozir nimani sinab ko'rish mumkin

Windows laptopda (Faza 1 lokal demo — tarmoq shart emas):

```powershell
cd server-win
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python test_harness.py
```

Batafsil: [`server-win/README.md`](server-win/README.md).
