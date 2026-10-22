"""Unique-kod orqali ulanish (relay) — AnyDesk uslubi.

Oqim:
  - Server (host) `/relay/host` ga ulanadi -> backend unique 9-xonali KOD beradi.
  - Viewer `/relay/viewer` ga ulanadi va {code, token} yuboradi -> backend juftlaydi.
  - Shundan so'ng backend ikki tomon orasida relay qiladi:
      host -> viewer : binary JPEG kadrlar (va matn control)
      viewer -> host : matn JSON input hodisalari

Shunday qilib telefon va kompyuter har xil tarmoqda bo'lsa ham (Railway orqali) ulanadi —
IP kerak emas, faqat KOD.

Litsenziya: viewer `token` yuborsa, u Telegram-hisobiga bog'lanadi va faol obuna tekshiriladi
(settings.relay_require_subscription=True bo'lsa majburiy). Token `/kirish` bot buyrug'idan
olinadi.
"""
from __future__ import annotations

import asyncio
import json
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .config import settings

router = APIRouter()


class HostSession:
    def __init__(self, code: str, ws: WebSocket) -> None:
        self.code = code
        self.host = ws
        self.viewer: WebSocket | None = None


# kod -> HostSession (xotirada; bitta instans uchun. Keyin Redis'ga ko'chirish mumkin.)
hosts: dict[str, HostSession] = {}


def _gen_code() -> str:
    while True:
        code = "".join(secrets.choice("0123456789") for _ in range(9))
        if code not in hosts:
            return code


def _fmt(code: str) -> str:
    return f"{code[0:3]} {code[3:6]} {code[6:9]}"


def _check_token(token: str) -> bool:
    """token -> faol obuna bormi. DB sync, shuning uchun to_thread bilan chaqiriladi."""
    if not token:
        return not settings.relay_require_subscription
    from sqlmodel import Session, select

    from .db import engine
    from .models import User, active_subscription

    with Session(engine) as s:
        user = s.exec(select(User).where(User.login_token == token)).first()
        if not user or user.is_blocked:
            return False
        if settings.relay_require_subscription:
            return active_subscription(s, user.id) is not None
        return True


@router.websocket("/relay/host")
async def relay_host(ws: WebSocket) -> None:
    await ws.accept()
    code = _gen_code()
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
        hosts.pop(code, None)
        if session.viewer is not None:
            try:
                await session.viewer.close()
            except Exception:
                pass


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

    if not await asyncio.to_thread(_check_token, token):
        await ws.send_text(json.dumps({"t": "error", "code": "unauthorized"}))
        await ws.close()
        return

    session = hosts.get(code)
    if session is None:
        await ws.send_text(json.dumps({"t": "error", "code": "not_found"}))
        await ws.close()
        return
    if session.viewer is not None:
        await ws.send_text(json.dumps({"t": "error", "code": "busy"}))
        await ws.close()
        return

    session.viewer = ws
    try:
        await session.host.send_text(json.dumps({"t": "viewer_connected"}))
    except Exception:
        pass
    await ws.send_text(json.dumps({"t": "connected"}))

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
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
