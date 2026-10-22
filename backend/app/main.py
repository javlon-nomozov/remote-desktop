"""FastAPI web xizmati: admin panel + chek ko'rish routi + health.

Signaling (WebRTC) endpointlari keyingi fazada shu ilovaga qo'shiladi.

Ishga tushirish (lokal):
    uvicorn app.main:app --reload
Railway'da:
    uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import secrets

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .admin import setup_admin
from .config import settings
from .db import get_session, init_db
from .models import Payment
from .relay import router as relay_router

app = FastAPI(title="Remote Desktop Backend")
_basic = HTTPBasic()


@app.on_event("startup")
def _startup() -> None:
    init_db()


# SQLAdmin panel + relay (unique-kod ulanish)
setup_admin(app)
app.include_router(relay_router)


def require_admin(creds: HTTPBasicCredentials = Depends(_basic)) -> bool:
    """Chek routi uchun HTTP Basic (admin panel login/parol bilan bir xil)."""
    ok = secrets.compare_digest(creds.username, settings.admin_panel_user) and secrets.compare_digest(
        creds.password, settings.admin_panel_password
    )
    if not ok:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return True


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/receipt/{payment_id}")
async def receipt(payment_id: int, _: bool = Depends(require_admin)):
    """Chek rasmini ko'rsatadi. Bot admin chatga shu linkni yuboradi (Basic auth so'raladi)."""
    with get_session() as s:
        pay = s.get(Payment, payment_id)
        if not pay or not pay.receipt_file_id:
            return Response("Chek topilmadi", status_code=404)
        file_id = pay.receipt_file_id

    token = settings.bot_token
    if not token:
        return Response("BOT_TOKEN sozlanmagan", status_code=500)

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id}
        )
        data = r.json()
        if not data.get("ok"):
            return Response("Telegramdan chek olinmadi", status_code=502)
        file_path = data["result"]["file_path"]
        fr = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
        if fr.status_code != 200:
            return Response("Chek yuklab olinmadi", status_code=502)
        media = fr.headers.get("content-type", "application/octet-stream")
        return Response(content=fr.content, media_type=media)
