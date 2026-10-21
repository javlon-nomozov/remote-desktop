"""Ma'lumotlar modellari (SQLModel).

Monetizatsiya yadrosi: User, Plan (tarif), Subscription, Payment, PromoCode, BalanceTx
(referal bonus daftari) va AppSettings (admin paneldan sozlanadigan global sozlamalar).
Qurilma/sessiya modellari (signaling) keyingi fazada qo'shiladi.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field, Session, SQLModel, select

# --- Status konstantalari (SQLite-friendly, str) ---
PAY_PENDING = "pending"
PAY_APPROVED = "approved"
PAY_REJECTED = "rejected"


def _now() -> datetime:
    return datetime.utcnow()


class AppSettings(SQLModel, table=True):
    """Global sozlamalar — bitta qator (id=1). Admin paneldan tahrirlanadi."""

    __tablename__ = "app_settings"

    id: Optional[int] = Field(default=1, primary_key=True)
    # To'lov
    card_number: str = Field(default="")
    card_holder: str = Field(default="")
    currency: str = Field(default="so'm")
    # Referal
    referral_enabled: bool = Field(default=True)
    referral_bonus_percent: int = Field(default=10)  # taklif qilingan to'lovdan %
    # Ilova linklari
    apk_url: str = Field(default="")
    server_installer_url: str = Field(default="")
    # Matnlar / aloqa
    support_username: str = Field(default="")
    welcome_text: str = Field(default="Assalomu alaykum! Remote desktop xizmatiga xush kelibsiz.")

    @classmethod
    def get_or_create(cls, session: Session) -> "AppSettings":
        obj = session.get(cls, 1)
        if obj is None:
            obj = cls(id=1)
            session.add(obj)
            session.commit()
            session.refresh(obj)
        return obj


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True)
    username: Optional[str] = Field(default=None)
    full_name: str = Field(default="")
    referral_code: str = Field(default="", index=True)
    referred_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
    balance: int = Field(default=0)  # referal bonus balansi (currency)
    is_blocked: bool = Field(default=False)
    created_at: NaiveDatetime = Field(default_factory=_now)


class Plan(SQLModel, table=True):
    __tablename__ = "plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = Field(default="")
    price: int = Field(default=0)  # currency (masalan so'm)
    duration_days: int = Field(default=30)
    max_devices: int = Field(default=1)
    max_fps: int = Field(default=60)
    is_active: bool = Field(default=True)
    sort_order: int = Field(default=0)


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan_id: int = Field(foreign_key="plans.id")
    starts_at: NaiveDatetime = Field(default_factory=_now)
    expires_at: NaiveDatetime
    is_active: bool = Field(default=True)
    created_at: NaiveDatetime = Field(default_factory=_now)

    def is_valid(self) -> bool:
        return self.is_active and self.expires_at > _now()


class PromoCode(SQLModel, table=True):
    __tablename__ = "promo_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    discount_percent: int = Field(default=0)  # [0..100]
    max_uses: int = Field(default=0)  # 0 = cheksiz
    used_count: int = Field(default=0)
    is_active: bool = Field(default=True)
    expires_at: Optional[NaiveDatetime] = Field(default=None)
    plan_id: Optional[int] = Field(default=None, foreign_key="plans.id")  # None = barcha tariflar

    def is_valid(self, plan_id: Optional[int] = None) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < _now():
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.plan_id and plan_id and self.plan_id != plan_id:
            return False
        return True


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan_id: int = Field(foreign_key="plans.id")
    base_amount: int = Field(default=0)       # tarif narxi
    promo_code_id: Optional[int] = Field(default=None, foreign_key="promo_codes.id")
    discount: int = Field(default=0)          # promo chegirmasi (currency)
    expected_amount: int = Field(default=0)   # to'lanishi kerak (base - discount)
    paid_amount: Optional[int] = Field(default=None)  # admin kiritgan haqiqiy summa
    status: str = Field(default=PAY_PENDING, index=True)
    receipt_file_id: str = Field(default="")  # Telegram file_id
    receipt_kind: str = Field(default="photo")  # "photo" | "document"
    admin_id: Optional[int] = Field(default=None)  # qaror qabul qilgan admin telegram id
    note: str = Field(default="")             # rad etish sababi va h.k.
    created_at: NaiveDatetime = Field(default_factory=_now)
    decided_at: Optional[NaiveDatetime] = Field(default=None)


class BalanceTx(SQLModel, table=True):
    """Balans daftari — referal bonuslar va boshqa o'zgarishlar shaffofligi uchun."""

    __tablename__ = "balance_tx"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    amount: int  # ishorali (musbat = qo'shildi)
    reason: str = Field(default="")
    ref_payment_id: Optional[int] = Field(default=None, foreign_key="payments.id")
    created_at: NaiveDatetime = Field(default_factory=_now)


# --- yordamchi so'rovlar ---
def active_subscription(session: Session, user_id: int) -> Optional[Subscription]:
    rows = session.exec(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active == True)  # noqa: E712
        .order_by(Subscription.expires_at.desc())
    ).all()
    for sub in rows:
        if sub.is_valid():
            return sub
    return None


def extend_subscription(session: Session, user_id: int, plan: Plan) -> Subscription:
    """Mavjud amaldagi obunani uzaytiradi yoki yangisini yaratadi."""
    current = active_subscription(session, user_id)
    if current:
        current.expires_at = current.expires_at + timedelta(days=plan.duration_days)
        current.plan_id = plan.id
        session.add(current)
        return current
    sub = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        starts_at=_now(),
        expires_at=_now() + timedelta(days=plan.duration_days),
    )
    session.add(sub)
    return sub
