"""FSM holatlari."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    waiting_receipt = State()   # user tarifni tanladi, chek kutilmoqda
    waiting_promo = State()     # promo kod kiritilmoqda


class AdminFlow(StatesGroup):
    waiting_amount = State()    # admin tasdiqladi, haqiqiy summani kiritmoqda
    waiting_reject_reason = State()
