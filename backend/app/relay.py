"""Unique-kod orqali ulanish (relay) — AnyDesk uslubi.

Oqim:
  - Server (host) `/relay/host` ga ulanadi -> backend 9-xonali KOD beradi. Host `?id=&secret=`
    yuborsa, o'sha doimiy kod beriladi (birinchi marta egallaydi, keyin faqat shu secret bilan).
  - Viewer `/relay/viewer` ga ulanadi va {code, token, device_id, device_name} yuboradi ->
    backend juftlaydi va host'ga {"t":"viewer_connected", device_id, device_name, user} yuboradi.
  - Shundan so'ng backend ikki tomon orasida relay qiladi:
      host -> viewer : binary JPEG kadrlar (va matn control)
      viewer -> host : matn JSON input hodisalari

Shunday qilib telefon va kompyuter har xil tarmoqda bo'lsa ham ulanadi — IP kerak emas, faqat KOD.
Ruxsat (kim ulanishi mumkin) host tomonida hal qilinadi; backend faqat juftlaydi.

Litsenziya: viewer `token` yuborsa, u Telegram-hisobiga bog'lanadi va faol obuna tekshiriladi
(settings.relay_require_subscription=True bo'lsa majburiy). Token `/kirish` bot buyrug'idan
olinadi.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .config import settings

router = APIRouter()


class HostSession:
    def __init__(self, code: str, ws: WebSocket) -> None:
        self.code = code
        self.host = ws
        self.viewer: WebSocket | None = None
        self.viewer_device = ""


# kod -> HostSession (xotirada; bitta instans uchun. Keyin Redis'ga ko'chirish mumkin.)
hosts: dict[str, HostSession] = {}


def _is_persistent(code: str) -> bool:
    """Kod biror kompyuterning doimiy kodi sifatida egallanganmi (DB)."""
    from sqlmodel import Session

    from .db import engine
    from .models import HostId

    with Session(engine) as s:
        return s.get(HostId, code) is not None


def _gen_code() -> str:
    while True:
        code = "".join(secrets.choice("0123456789") for _ in range(9))
        if code[0] != "0" and code not in hosts and not _is_persistent(code):
            return code


def _claim_code(want: str, secret: str) -> str | None:
    """Doimiy kodni beradi: yangi bo'lsa shu secret bilan egallaydi, bor bo'lsa secret mos kelishi
    kerak. Mos kelmasa None (chaqiruvchi tasodifiy kod beradi)."""
    if not (len(want) == 9 and want.isdigit() and want[0] != "0" and len(secret) >= 16):
        return None
    from sqlmodel import Session

    from .db import engine
    from .models import HostId

    digest = hashlib.sha256(secret.encode()).hexdigest()
    try:
        with Session(engine) as s:
            row = s.get(HostId, want)
            if row is None:
                s.add(HostId(id=want, secret_hash=digest))
            elif hmac.compare_digest(row.secret_hash, digest):
                row.last_seen_at = datetime.utcnow()
                s.add(row)
            else:
                return None
            s.commit()
        return want
    except Exception:
        return None


def _fmt(code: str) -> str:
    return f"{code[0:3]} {code[3:6]} {code[6:9]}"


def _check_token(token: str) -> tuple[bool, str]:
    """token -> (ruxsat bormi, user yorlig'i). DB sync, shuning uchun to_thread bilan chaqiriladi."""
    if not token:
        return not settings.relay_require_subscription, ""
    from sqlmodel import Session, select

    from .db import engine
    from .models import User, active_subscription

    with Session(engine) as s:
        user = s.exec(select(User).where(User.login_token == token)).first()
        if not user or user.is_blocked:
            return False, ""
        label = user.phone or user.full_name or ""
        if settings.relay_require_subscription:
            return active_subscription(s, user.id) is not None, label
        return True, label


async def _close(ws: WebSocket | None) -> None:
    if ws is None:
        return
    try:
        await ws.close()
    except Exception:
        pass


@router.websocket("/relay/host")
async def relay_host(ws: WebSocket, id: str = "", secret: str = "") -> None:
    await ws.accept()
    code = await asyncio.to_thread(_claim_code, id, secret) if id else None
    if code is None:
        code = await asyncio.to_thread(_gen_code)
    old = hosts.get(code)
    if old is not None:
        # o'sha kompyuterning eski (uzilgan, lekin hali sezilmagan) ulanishi — almashtiramiz
        await _close(old.viewer)
        await _close(old.host)
    session = HostSession(code, ws)
    hosts[code] = session
    await ws.send_text(json.dumps({"t": "code", "code": code, "pretty": _fmt(code)}))
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            v = session.viewer
            if v is None:
                continue
            try:
                if msg.get("bytes") is not None:
                    await v.send_bytes(msg["bytes"])
                elif msg.get("text") is not None:
                    await v.send_text(msg["text"])
            except Exception:
                session.viewer = None
    except WebSocketDisconnect:
        pass
    finally:
        if hosts.get(code) is session:
            hosts.pop(code, None)
        await _close(session.viewer)


@router.websocket("/relay/viewer")
async def relay_viewer(ws: WebSocket) -> None:
    await ws.accept()
    try:
        first = await ws.receive_text()
        data = json.loads(first)
    except Exception:
        await ws.close()
        return

    code = str(data.get("code", "")).replace(" ", "")
    token = str(data.get("token", ""))
    device_id = str(data.get("device_id", ""))[:64]
    device_name = str(data.get("device_name", ""))[:80]

    ok, user_label = await asyncio.to_thread(_check_token, token)
    if not ok:
        await ws.send_text(json.dumps({"t": "error", "code": "unauthorized"}))
        await ws.close()
        return

    session = hosts.get(code)
    if session is None:
        await ws.send_text(json.dumps({"t": "error", "code": "not_found"}))
        await ws.close()
        return
    if session.viewer is not None:
        if device_id and device_id == session.viewer_device:
            # shu telefonning o'zi qayta ulanmoqda (eski socket o'lik) — eskisini almashtiramiz
            old = session.viewer
            session.viewer = None
            await _close(old)
            try:
                await session.host.send_text(json.dumps({"t": "viewer_disconnected"}))
            except Exception:
                pass
        else:
            await ws.send_text(json.dumps({"t": "error", "code": "busy"}))
            await ws.close()
            return

    session.viewer = ws
    session.viewer_device = device_id
    try:
        await session.host.send_text(json.dumps({
            "t": "viewer_connected",
            "device_id": device_id,
            "device_name": device_name,
            "user": user_label,
        }))
    except Exception:
        pass
    await ws.send_text(json.dumps({"t": "connected"}))

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if session.viewer is not ws:
                break  # boshqa ulanish bilan almashtirilgan
            if msg.get("text") is not None:
                try:
                    await session.host.send_text(msg["text"])
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        if session.viewer is ws:
            session.viewer = None
            try:
                await session.host.send_text(json.dumps({"t": "viewer_disconnected"}))
            except Exception:
                pass
