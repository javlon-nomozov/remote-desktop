"""DB engine va sessiya (SQLModel, sync).

Modest traffic uchun sync yetarli (SQLite lokal, Postgres Railway'da). Bot handlerlari
asyncio bo'lsa ham, qisqa so'rovlar event loop'ni sezilarli bloklamaydi.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from .config import settings

_url = settings.database_url
# Railway "postgres://" beradi. SQLAlchemy 2.1 standart postgres drayveri psycopg(v3) —
# bizda psycopg2-binary bor, shuning uchun psycopg2'ni MAJBURIY qilamiz.
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _url.startswith("postgresql://") and "+psycopg" not in _url:
    _url = _url.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, echo=False, pool_pre_ping=True, connect_args=connect_args)


def init_db() -> None:
    """Jadvallarni yaratish va boshlang'ich sozlamalar qatorini ta'minlash."""
    # modellar import qilinishi shart (metadata to'lishi uchun)
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate_bigint()
    with Session(engine) as s:
        models.AppSettings.get_or_create(s)


def _migrate_bigint() -> None:
    """Telegram ID ustunlarini INTEGER -> BIGINT (Postgres). create_all mavjud ustunni o'zgartirmaydi;
    yangi akkauntlar ID'si 2^31 dan katta bo'lgani uchun ular ro'yxatdan o'ta olmas edi. Takroriy
    ishga tushirish xavfsiz (faqat INTEGER bo'lsa o'zgartiradi). SQLite'da INTEGER allaqachon 64-bit."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, column in (("users", "telegram_id"), ("payments", "admin_id")):
            kind = conn.execute(
                text("SELECT data_type FROM information_schema.columns "
                     "WHERE table_name = :t AND column_name = :c"),
                {"t": table, "c": column},
            ).scalar()
            if kind == "integer":
                conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BIGINT"))


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
