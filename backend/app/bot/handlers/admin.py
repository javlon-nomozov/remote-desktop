"""Admin handlerlari: to'lovni tasdiqlash/rad etish + haqiqiy summa kiritish."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlmodel import select

from ...config import settings
from ...db import get_session
from ...models import PAY_PENDING, AppSettings, Payment, Plan, User
from ... import payments as pay_svc
from .. import texts as T
from ...users import get_user
from ..loader import bot
from ..states import AdminFlow

router = Router()


def _is_admin(uid: int) -> bool:
    return settings.is_admin(uid)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    with get_session() as s:
        pending = len(s.exec(select(Payment).where(Payment.status == PAY_PENDING)).all())
    link = f"{settings.public_base_url}/admin"
    await message.answer(
        f"🛠 <b>Admin</b>\nKutilayotgan to'lovlar: <b>{pending}</b>\n\nAdmin panel: {link}",
        disable_web_page_preview=True,
    )


# --- Tasdiqlash: summa so'rash --------------------------------------------
@router.callback_query(F.data.startswith("pay_ok:"))
async def cb_pay_ok(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    pid = int(call.data.split(":")[1])
    with get_session() as s:
        pay = s.get(Payment, pid)
        if not pay or pay.status != PAY_PENDING:
            await call.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return
        expected = pay.expected_amount
    await state.set_state(AdminFlow.waiting_amount)
    await state.update_data(payment_id=pid)
    await call.message.answer(
        f"💰 Hisobga <b>qancha pul</b> tushdi? (kutilgan: {expected})\n"
        f"Faqat raqam yuboring (masalan: {expected})."
    )
    await call.answer()


@router.message(AdminFlow.waiting_amount, F.text)
async def on_amount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    raw = message.text.replace(" ", "").replace("'", "")
    if not raw.isdigit():
        await message.answer("Iltimos, faqat raqam yuboring.")
        return
    amount = int(raw)
    data = await state.get_data()
    pid = data.get("payment_id")

    with get_session() as s:
        pay = s.get(Payment, pid)
        if not pay or pay.status != PAY_PENDING:
            await message.answer("To'lov topilmadi yoki allaqachon ko'rib chiqilgan.")
            await state.clear()
            return
        sub = pay_svc.approve_payment(s, pay, message.from_user.id, amount)
        user = s.get(User, pay.user_id)
        plan = s.get(Plan, pay.plan_id)
        cfg = AppSettings.get_or_create(s)
        user_tid = user.telegram_id
        expires = sub.expires_at
        plan_name = plan.name
        currency = cfg.currency

    await state.clear()
    await message.answer(f"✅ Tasdiqlandi. {plan_name} — {T.fmt_money(amount, currency)}.")
    try:
        await bot.send_message(
            user_tid,
            f"✅ To'lovingiz tasdiqlandi!\nTarif: <b>{plan_name}</b>\n"
            f"Amal qiladi: {expires:%Y-%m-%d %H:%M} gacha.",
        )
    except Exception:
        pass


# --- Rad etish: sabab so'rash ---------------------------------------------
@router.callback_query(F.data.startswith("pay_no:"))
async def cb_pay_no(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    pid = int(call.data.split(":")[1])
    with get_session() as s:
        pay = s.get(Payment, pid)
        if not pay or pay.status != PAY_PENDING:
            await call.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return
    await state.set_state(AdminFlow.waiting_reject_reason)
    await state.update_data(payment_id=pid)
    await call.message.answer("❌ Rad etish sababini yozing (yoki '-' yuboring):")
    await call.answer()


@router.message(AdminFlow.waiting_reject_reason, F.text)
async def on_reject_reason(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    reason = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    pid = data.get("payment_id")
    with get_session() as s:
        pay = s.get(Payment, pid)
        if not pay or pay.status != PAY_PENDING:
            await message.answer("To'lov topilmadi yoki allaqachon ko'rib chiqilgan.")
            await state.clear()
            return
        pay_svc.reject_payment(s, pay, message.from_user.id, reason)
        user = s.get(User, pay.user_id)
        user_tid = user.telegram_id

    await state.clear()
    await message.answer("❌ Rad etildi.")
    try:
        suffix = f"\nSabab: {reason}" if reason else ""
        await bot.send_message(user_tid, f"❌ To'lovingiz rad etildi.{suffix}\n"
                                         f"Savollar bo'lsa admin bilan bog'laning.")
    except Exception:
        pass
