"""Inline klaviaturalar."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import Plan


def main_menu(referral_enabled: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Tariflar", callback_data="plans")
    kb.button(text="📊 Mening obunam", callback_data="mysub")
    kb.button(text="📥 Ilovalarni yuklash", callback_data="apps")
    kb.button(text="🎟 Promo kod", callback_data="promo")
    if referral_enabled:
        kb.button(text="👥 Referal", callback_data="referral")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def plans_kb(plans: list[Plan]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in plans:
        kb.button(text=p.name, callback_data=f"plan:{p.id}")
    kb.button(text="⬅️ Orqaga", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def plan_detail_kb(plan_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Sotib olish", callback_data=f"buy:{plan_id}")
    kb.button(text="🎟 Promo bilan", callback_data=f"buypromo:{plan_id}")
    kb.button(text="⬅️ Tariflar", callback_data="plans")
    kb.adjust(1)
    return kb.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Menyu", callback_data="menu")
    return kb.as_markup()


def admin_decision_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_ok:{payment_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no:{payment_id}"),
            ]
        ]
    )
