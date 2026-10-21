# viewer-android — Android (Kotlin) viewer (Faza 5)

Telefondan Windows serverni ko'rish va **touchscreen/klaviatura/touchpad** sifatida
boshqarish. Hozirgi server (WS+JPEG MVP, `server-win/server_main.py`) bilan to'g'ridan-to'g'ri
ishlaydi — bir xil protokol (PROTOCOL.md).

## Nega bu "haqiqiysidek"

Teginishlar `touch` kontakt massivi sifatida yuboriladi (har barmoqqa `id`, normalizatsiya
qilingan `x,y`, `state`). Server ularni **haqiqiy touch** sifatida injekt qiladi, shuning
uchun 2/3/4-barmoq gesturalarni Windows'ning o'zi taniydi (pinch-zoom, scroll, swipe).

## Build (Android Studio)

> Bu yerda Android SDK yo'q edi, shuning uchun APK men tomonimdan build qilinmagan —
> quyidagicha oching va yig'ing. Build xatosi chiqsa, menga ayting — tuzatamiz.

1. **Android Studio** (Koala+ / 2024+) da `viewer-android/` papkasini oching.
2. Gradle sync — Studio Gradle wrapper (`gradlew`) ni avtomatik yaratadi va kerakli SDK'ni
   so'raydi (compileSdk 34). (Yoki terminalда, agar `gradle` o'rnatilgan bo'lsa:
   `gradle wrapper` → keyin `./gradlew assembleDebug`.)
3. Telefonni USB orqali ulang (USB debugging yoqilgan) yoki emulyator → **Run**.
4. Yoki APK: `./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk`.

## Ishlatish

1. Serverда (Windows): `python server_main.py` (ekranда "faol" indikator yonadi).
2. Telefon va laptop **bir xil WiFi** da bo'lsin.
3. Ilovани oching → laptop IP (masalan `192.168.1.50`) va port `8765` → **Ulanish**.
4. Ekran jonli ko'rinadi. Pastki tugmalar:
   - **Touch/Touchpad** — rejim almashtirish (absolute touchscreen ↔ nisbiy touchpad).
   - **⌨** — klaviatura (yozilgan matn serverga boradi).
   - **✕** — uzish.

## Tuzilishi

| Fayl | Vazifasi |
|------|----------|
| `MainActivity.kt` | ulanish ekrani (IP/port) |
| `ViewerActivity.kt` | oqim + boshqaruv + klaviatura |
| `StreamClient.kt` | OkHttp WebSocket (WS+JPEG protokoli) |
| `RemoteView.kt` | kadrni chizish + teginish → `touch`/`mouse` hodisalari |

## Keyingi (ixtiyoriy optimizatsiya)
- Internet orqali ulanish uchun backend signaling (Railway) qo'shiladi (hozir to'g'ridan IP).
- Past kechikish uchun H.264/WebRTC (`stream-webrtc-android`) — input protokoli o'zgarmaydi.
