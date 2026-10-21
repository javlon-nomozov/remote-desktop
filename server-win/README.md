# server-win — Windows server yadrosi (Faza 1)

Boshqariladigan Windows mashina qismi. Hozircha **lokal demo** tayyor: tarmoqsiz, faqat
input injection + click-through indikator + ekran capture sinab ko'riladi. Tarmoq (WebRTC)
Faza 2 da qo'shiladi.

## Tarkib

| Fayl | Vazifasi |
|------|----------|
| `input/winapi.py` | DPI awareness, ekran metrikasi, `SendInput` strukturalari |
| `input/touch.py` | **Multi-touch injection** (`InitializeTouchInjection`/`InjectTouchInput`) |
| `input/keyboard.py` | Klaviatura (scancode + unicode matn) |
| `input/mouse.py` | Sichqoncha (absolute/relative/wheel) |
| `input/controller.py` | Protokol hodisalarini qurilmaga qo'llaydi (normalizatsiya → piksel) |
| `overlay/indicator.py` | Click-through "faol" indikator (qizil nuqta / watermark) |
| `capture/screen.py` | Ekran capture (dxcam + mss fallback) |
| `test_harness.py` | Faza 1 lokal demo (CLI) |

## O'rnatish

```powershell
cd server-win
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

> `dxcam` o'rnatilmasa yoki ishlamasa, capture avtomatik `mss` ga o'tadi.
> `tkinter` va `ctypes` — standart kutubxona (alohida o'rnatish shart emas).

## Sinash

```powershell
# 1) Click-through indikator — ustidan bossangiz, tagidagi element bosilishi kerak
python test_harness.py indicator --mode dot
python test_harness.py indicator --mode watermark

# 2) Haqiqiy touch gesturalar (3 soniya ichida mos oynani fokusga oling)
python test_harness.py gesture tap
python test_harness.py gesture scroll            # 2-barmoq scroll
python test_harness.py gesture pinch --direction out   # zoom in (Photos/Xaritalar)
python test_harness.py gesture pinch --direction in    # zoom out
python test_harness.py gesture swipe3            # 3-barmoq swipe -> Task View

# 3) Capture tezligi
python test_harness.py capture --seconds 3

# 4) Hammasi ketma-ket
python test_harness.py all
```

### Nimani kutish kerak
- **Indikator**: ekran burchagida qizil nuqta "nafas olib" turadi (yoki butun ekranda 50%
  watermark). Uning ustidan sichqoncha bilan bossangiz — bosish **tagidagi oynaga** o'tadi,
  indikator hech narsa qilmaydi.
- **scroll/pinch/swipe3**: Windows bularni haqiqiy touchscreen gesturasi deb qabul qiladi —
  Photos'da rasm kattalashadi, brauzerda sahifa aylanadi, swipe'da Task View ochiladi.
  Demak viewer yuborgan barmoqlar serverда "huddi haqiqiy" ishlaydi.

## Faza 2 — tarmoq orqali streaming (viewer bilan)

Server ekranni stream qiladi va viewerдан input qabul qiladi (WebSocket + JPEG MVP).

```powershell
# venv (3.15 ham bo'ladi — streaming wheel'lari mavjud)
.\.venv\Scripts\activate   # yoki: py -3.12 -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt

python server_main.py                 # indikator=dot, input yoqilgan, ws://0.0.0.0:8765
python server_main.py --no-input      # XAVFSIZ sinov: faqat ekran, injeksiyasiz
python server_main.py --indicator watermark --fps 25 --quality 65
```

So'ng boshqa mashinada (yoki shu mashinada) viewer'ni ulang —
[viewer-win/README.md](../viewer-win/README.md):
```powershell
python main.py --host <server-ip>     # yoki localhost
```

Kutilishi: viewer oynasida server ekrani jonli ko'rinadi; viewerда sichqoncha/klaviatura
serverga uzatiladi. Birinchi marta `--no-input` bilan sinab, keyin to'liq ishlating.

## Eslatma
Touch injection uchun odatda administrator huquqi shart emas (bir sessiya ichida). Agar
`InjectTouchInput` xato bersa, mashinada touch qo'llab-quvvatlashi va sessiya turini
tekshiring. Ekran capture standart `mss` orqali (ishonchli); dxcam opt-in va `cv2` (opencv)
talab qilishi mumkin.
