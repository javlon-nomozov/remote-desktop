"""DB engine va sessiya (SQLModel, sync).

Modest traffic uchun sync yetarli (SQLite lokal, Postgres Railway'da). Bot handlerlari
asyncio bo'lsa ham, qisqa so'rovlar event loop'ni sezilarli bloklamaydi.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from .config import settings

_url = settings.database_url
# Railway ba'zan "postgres://" beradi; SQLAlchemy "postgresql://" kutadi.
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, echo=False, pool_pre_ping=True, connect_args=connect_args)


def init_db() -> None:
    """Jadvallarni yaratish va boshlang'ich sozlamalar qatorini ta'minlash."""
    # modellar import qilinishi shart (metadata to'lishi uchun)
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        models.AppSettings.get_or_create(s)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
