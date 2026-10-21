"""Botni mustaqil ishga tushirish (long polling).

Ishlatish:
    python -m app.run_bot

Railway'da alohida xizmat sifatida shu buyruq bilan ishga tushiriladi (web xizmat bilan
bir xil DATABASE_URL va BOT_TOKEN ishlatadi).
"""
from __future__ import annotations

import asyncio
import logging

from .config import settings
from .db import init_db
from .bot.handlers import build_router
from .bot.loader import bot, dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylga BOT_TOKEN=... qo'shing.")
    init_db()
    dp.include_router(build_router())
    me = await bot.get_me()
    logging.info("Bot ishga tushdi: @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
