"""Qo'lda to'lov tasdiqlash xizmati (qayta ishlatiladigan yadro).

Oqim: user kartaga o'tkazadi → chek (Telegram) → admin tasdiq/rad + haqiqiy summa →
obuna faollashadi → referal bonus (yoqilgan bo'lsa) + promo hisobga olinadi.

Bu modul UI/transport'dan mustaqil (faqat Session bilan ishlaydi), shuning uchun uni
`manual-payment-approval` skilliga ajratish oson. Bot handlerlari shu funksiyalarni chaqiradi.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from . import models
from .models import (
    AppSettings,
    BalanceTx,
    Payment,
    Plan,
    PromoCode,
    User,
)


# --- Promo ---------------------------------------------------------------
def find_promo(session: Session, code: str) -> Optional[PromoCode]:
    code = (code or "").strip().upper()
    if not code:
        return None
    return session.exec(select(PromoCode).where(PromoCode.code == code)).first()


def compute_amount(base: int, promo: Optional[PromoCode]) -> tuple[int, int]:
    """(expected_amount, discount) — promo chegirmasini qo'llaydi."""
    if promo and promo.discount_percent > 0:
        discount = base * promo.discount_percent // 100
        return max(0, base - discount), discount
    return base, 0


# --- To'lov yaratish -----------------------------------------------------
def create_payment(
    session: Session,
    user: User,
    plan: Plan,
    receipt_file_id: str,
    receipt_kind: str = "photo",
    promo_code: Optional[str] = None,
) -> Payment:
    promo = find_promo(session, promo_code) if promo_code else None
    if promo and not promo.is_valid(plan.id):
        promo = None  # yaroqsiz promo e'tiborsiz
    expected, discount = compute_amount(plan.price, promo)
    pay = Payment(
        user_id=user.id,
        plan_id=plan.id,
        base_amount=plan.price,
        promo_code_id=promo.id if promo else None,
        discount=discount,
        expected_amount=expected,
        status=models.PAY_PENDING,
        receipt_file_id=receipt_file_id,
        receipt_kind=receipt_kind,
    )
    session.add(pay)
    session.commit()
    session.refresh(pay)
    return pay


# --- Tasdiqlash ----------------------------------------------------------
def approve_payment(
    session: Session, payment: Payment, admin_id: int, paid_amount: int
) -> models.Subscription:
    """To'lovni tasdiqlaydi: obuna uzaytiriladi, promo va referal hisobga olinadi."""
    payment.status = models.PAY_APPROVED
    payment.admin_id = admin_id
    payment.paid_amount = paid_amount
    payment.decided_at = datetime.utcnow()
    session.add(payment)

    plan = session.get(Plan, payment.plan_id)
    sub = models.extend_subscription(session, payment.user_id, plan)

    # promo ishlatilgan deb belgilash
    if payment.promo_code_id:
        promo = session.get(PromoCode, payment.promo_code_id)
        if promo:
            promo.used_count += 1
            session.add(promo)

    # referal bonus
    _apply_referral_bonus(session, payment)

    session.commit()
    session.refresh(sub)
    return sub


def reject_payment(session: Session, payment: Payment, admin_id: int, reason: str = "") -> None:
    payment.status = models.PAY_REJECTED
    payment.admin_id = admin_id
    payment.note = reason
    payment.decided_at = datetime.utcnow()
    session.add(payment)
    session.commit()


def _apply_referral_bonus(session: Session, payment: Payment) -> None:
    cfg = AppSettings.get_or_create(session)
    if not cfg.referral_enabled or cfg.referral_bonus_percent <= 0:
        return
    user = session.get(User, payment.user_id)
    if not user or not user.referred_by_id:
        return
    referrer = session.get(User, user.referred_by_id)
    if not referrer:
        return
    base = payment.paid_amount or payment.expected_amount
    bonus = base * cfg.referral_bonus_percent // 100
    if bonus <= 0:
        return
    referrer.balance += bonus
    session.add(referrer)
    session.add(
        BalanceTx(
            user_id=referrer.id,
            amount=bonus,
            reason=f"Referal bonus ({cfg.referral_bonus_percent}%)",
            ref_payment_id=payment.id,
        )
    )
