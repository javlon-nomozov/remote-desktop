"""Bot matnlari (o'zbekcha) va formatlash yordamchilari."""
from __future__ import annotations

from datetime import datetime

from ..models import AppSettings, Payment, Plan, User


def fmt_money(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", " ") + f" {currency}"


def plan_line(p: Plan, currency: str) -> str:
    return f"• <b>{p.name}</b> — {fmt_money(p.price, currency)} / {p.duration_days} kun"


def plan_card(p: Plan, currency: str) -> str:
    lines = [f"<b>{p.name}</b>", ""]
    if p.description:
        lines += [p.description, ""]
    lines += [
        f"Narx: <b>{fmt_money(p.price, currency)}</b>",
        f"Muddat: {p.duration_days} kun",
        f"Qurilmalar: {p.max_devices} tagacha",
    ]
    return "\n".join(lines)


def payment_instructions(cfg: AppSettings, plan: Plan, expected: int, discount: int) -> str:
    lines = [
        f"To'lov: <b>{plan.name}</b>",
        "",
        f"To'lov summasi: <b>{fmt_money(expected, cfg.currency)}</b>",
    ]
    if discount:
        lines.append(f"(promo chegirma: -{fmt_money(discount, cfg.currency)})")
    lines += [
        "",
        "Quyidagi kartaga o'tkazing:",
        f"💳 <code>{cfg.card_number or '—'}</code>",
        f"👤 {cfg.card_holder or '—'}",
        "",
        "To'lagach, <b>chek rasmini</b> shu yerga yuboring. "
        "Admin tekshirib, obunangizni faollashtiradi.",
    ]
    return "\n".join(lines)


def sub_status(user: User, sub, plan_name: str | None, currency: str) -> str:
    if sub is None:
        return "Sizda faol obuna yo'q. <b>Tariflar</b> bo'limidan tanlang."
    left = sub.expires_at - datetime.utcnow()
    days = max(0, left.days)
    return (
        f"✅ Faol obuna: <b>{plan_name or '—'}</b>\n"
        f"Tugaydi: {sub.expires_at:%Y-%m-%d %H:%M} (≈{days} kun)\n"
        f"Balans: {fmt_money(user.balance, currency)}"
    )


def admin_payment_notice(user: User, plan: Plan, pay: Payment, currency: str, link: str) -> str:
    uname = f"@{user.username}" if user.username else f"id {user.telegram_id}"
    lines = [
        "🧾 <b>Yangi to'lov cheki</b>",
        f"Foydalanuvchi: {user.full_name} ({uname})",
        f"Tarif: <b>{plan.name}</b>",
        f"Kutilgan summa: <b>{fmt_money(pay.expected_amount, currency)}</b>",
    ]
    if pay.discount:
        lines.append(f"Promo chegirma: -{fmt_money(pay.discount, currency)}")
    lines += ["", f"Chekni ko'rish: {link}", "", "Tasdiqlaysizmi?"]
    return "\n".join(lines)
