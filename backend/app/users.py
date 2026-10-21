"""Foydalanuvchi ro'yxatga olish + referal bog'lanish."""
from __future__ import annotations

import secrets
from typing import Optional

from sqlmodel import Session, select

from .models import AppSettings, User


def _gen_code(session: Session) -> str:
    for _ in range(20):
        code = secrets.token_hex(4).upper()  # 8 belgili
        if not session.exec(select(User).where(User.referral_code == code)).first():
            return code
    return secrets.token_hex(6).upper()


def get_user(session: Session, telegram_id: int) -> Optional[User]:
    return session.exec(select(User).where(User.telegram_id == telegram_id)).first()


def get_or_create_user(
    session: Session,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    referred_by_code: Optional[str] = None,
) -> tuple[User, bool]:
    """Qaytaradi: (user, created). Yangi bo'lsa referalni bog'laydi."""
    user = get_user(session, telegram_id)
    if user:
        # ma'lumotni yangilab turamiz
        changed = False
        if username != user.username:
            user.username, changed = username, True
        if full_name and full_name != user.full_name:
            user.full_name, changed = full_name, True
        if changed:
            session.add(user)
            session.commit()
        return user, False

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        referral_code=_gen_code(session),
    )

    # referalni bog'lash (faqat yoqilgan bo'lsa va o'ziga emas)
    cfg = AppSettings.get_or_create(session)
    if cfg.referral_enabled and referred_by_code:
        ref = session.exec(
            select(User).where(User.referral_code == referred_by_code.strip().upper())
        ).first()
        if ref and ref.telegram_id != telegram_id:
            user.referred_by_id = ref.id

    session.add(user)
    session.commit()
    session.refresh(user)
    return user, True
