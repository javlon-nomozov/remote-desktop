"""Namuna ma'lumot: bir nechta tarif + sozlamalar. Bir marta ishga tushiring.

    cd backend
    python -m seed
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import AppSettings, Plan


def run() -> None:
    init_db()
    with Session(engine) as s:
        cfg = AppSettings.get_or_create(s)
        if not cfg.card_number:
            cfg.card_number = "8600 1234 5678 9012"
            cfg.card_holder = "ISM FAMILIYA"
            cfg.currency = "so'm"
            cfg.referral_enabled = True
            cfg.referral_bonus_percent = 10
            s.add(cfg)

        if not s.exec(select(Plan)).first():
            s.add_all([
                Plan(name="1 oy", description="Bir oylik to'liq kirish", price=30000,
                     duration_days=30, max_devices=1, sort_order=1),
                Plan(name="3 oy", description="Chegirmali uch oylik", price=75000,
                     duration_days=90, max_devices=2, sort_order=2),
                Plan(name="1 yil", description="Eng foydali yillik", price=250000,
                     duration_days=365, max_devices=3, sort_order=3),
            ])
        s.commit()
    print("Seed tayyor: tariflar va sozlamalar yaratildi.")


if __name__ == "__main__":
    run()
