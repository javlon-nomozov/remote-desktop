# backend — FastAPI + admin panel + Telegram bot (Faza 3–4)

Ikki jarayon, bitta kod bazasi va bitta DB:
- **web** (`app.main:app`) — admin panel (SQLAdmin) + chek ko'rish routi + health (keyinroq signaling).
- **bot** (`app.run_bot`) — aiogram Telegram bot (ro'yxat, tariflar, to'lov, referal, promo).

To'lov oqimi qayta ishlatiladigan `app/payments.py` da (keyin `manual-payment-approval`
skilliga ajratiladi).

## Sozlash

1. Loyiha ildizidagi `.env.example` ni `.env` ga nusxalang va to'ldiring
   (`BOT_TOKEN`, `ADMIN_IDS`, admin panel login/parol). **Nomlar aynan shunday bo'lsin.**
2. **Python 3.12 yoki 3.13** kerak. (Python 3.15 hali yangi — `pydantic-core`, `aiohttp`,
   `pyyaml` uchun tayyor wheel yo'q, shuning uchun o'rnatish source'dan qurilmoqchi bo'lib
   xato beradi. Railway ham `.python-version` bo'yicha 3.12 ishlatadi.)
   ```powershell
   cd backend
   py -3.12 -m venv .venv      # yoki: py -3.13 -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Namuna tariflar (ixtiyoriy):
   ```powershell
   python -m seed
   ```

## Lokal ishga tushirish

Ikki terminalда:
```powershell
# 1) web + admin panel
uvicorn app.main:app --reload
#   -> http://localhost:8000/admin  (login: .env dagi ADMIN_PANEL_USER/PASSWORD)
#   -> http://localhost:8000/health

# 2) bot
python -m app.run_bot
```

Botда `/start` yuboring → menyu. Tarif tanlab, chek (istalgan rasm) yuboring → admin
hisobingizga tugmali xabar keladi → **Tasdiqlash** → summa kiriting → obuna faollashadi.
`/admin` buyrug'i admin panel linkini beradi.

## Railway'ga deploy

Bitta repo, **ikkita service** (ikkalasi bir xil Postgres va env):
1. Postgres plugin qo'shing → `DATABASE_URL` avtomatik ulanadi.
2. **web** service — Start command:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
   (Root Directory: `backend`). Env: `BOT_TOKEN`, `ADMIN_IDS`, `ADMIN_PANEL_USER`,
   `ADMIN_PANEL_PASSWORD`, `ADMIN_SESSION_SECRET`, `PUBLIC_BASE_URL`(=service public URL).
3. **bot** service — Start command:
   ```
   python -m app.run_bot
   ```
   (Root Directory: `backend`). Bir xil env (`PUBLIC_BASE_URL` = web service URL, shunda
   chek linklari to'g'ri bo'ladi).

> Chiroyli domain shart emas — Railway bergan `*.up.railway.app` yetarli.

## Eslatma
- Chek rasmi hech qayerga saqlanmaydi — panel linki ochilganda Telegramdan oqim bilan
  ko'rsatiladi (HTTP Basic: admin panel login/parol).
- Obuna muddati tekshiruvi ulanish vaqtida (signaling, keyingi faza) qo'llanadi.
