"""Router agregatsiyasi."""
from aiogram import Router

from . import admin, user


def build_router() -> Router:
    root = Router()
    # admin birinchi — FSM holatlari to'g'ri ustun bo'lishi uchun
    root.include_router(admin.router)
    root.include_router(user.router)
    return root
