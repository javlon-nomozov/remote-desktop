"""Foydalanuvchi handlerlari: ro'yxat, tariflar, sotib olish, chek, referal, ilovalar."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlmodel import select

from ... import config
from ...db import get_session
from ...models import AppSettings, LoginNonce, Plan, Subscription, User, active_subscription
from ... import payments as pay_svc
from ... import users as user_svc
from .. import keyboards as kb
from .. import texts as T
from ..loader import bot
from ..states import BuyFlow

router = Router()

_bot_username: str | None = None
# telegram_id -> login nonce (/start login_<nonce> va contact orasida; bir jarayon)
_login_pending: dict[int, str] = {}


async def bot_username() -> str:
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username or ""
    return _bot_username


def _active_plans(session) -> list[Plan]:
    return list(
        session.exec(
            select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order, Plan.id)  # noqa: E712
        ).all()
    )


# --- /start + ro'yxat ----------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    ref_code = (command.args or "").strip() or None
    if ref_code and ref_code.startswith("login_"):
        _login_pending[message.from_user.id] = ref_code[len("login_"):]
        await message.answer(
            "Ilovaga kirish uchun telefon raqamingizni ulashing (pastdagi tugma):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        user, created = user_svc.get_or_create_user(
            s,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            referred_by_code=ref_code,
        )
        referral_enabled = cfg.referral_enabled
        welcome = cfg.welcome_text
    greet = welcome if created else "Qaytganingizdan xursandmiz!"
    await message.answer(greet, reply_markup=kb.main_menu(referral_enabled))


@router.message(Command("kirish"))
async def cmd_login(message: Message) -> None:
    """Ilovaga kirish tokenini beradi (viewer app'ga joylaydi)."""
    with get_session() as s:
        user, _ = user_svc.get_or_create_user(
            s, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        token = user_svc.ensure_login_token(s, user)
    await message.answer(
        "🔑 <b>Kirish kodingiz (token)</b>\n\n"
        f"<code>{token}</code>\n\n"
        "Ilovada (telefon/kompyuter) shu tokenni joylang. Hech kimga bermang.",
    )


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    """Telefon raqam ulashildi: hisobni tasdiqlab, login oqimi bo'lsa token beramiz."""
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Iltimos, o'z raqamingizni ulashing.")
        return
    nonce = _login_pending.pop(message.from_user.id, None)
    with get_session() as s:
        user, _ = user_svc.get_or_create_user(
            s, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        user.phone = contact.phone_number
        s.add(user)
        s.commit()
        token = user_svc.ensure_login_token(s, user)
        if nonce:
            ln = s.get(LoginNonce, nonce)
            if ln:
                ln.token = token
            else:
                ln = LoginNonce(nonce=nonce, token=token)
            s.add(ln)
            s.commit()
    if nonce:
        await message.answer("✅ Tasdiqlandi! Endi ilovaga qayting.",
                             reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("✅ Raqamingiz saqlandi.", reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        enabled = cfg.referral_enabled
    await call.message.edit_text("Asosiy menyu:", reply_markup=kb.main_menu(enabled))
    await call.answer()


# --- Tariflar ------------------------------------------------------------
@router.callback_query(F.data == "plans")
async def cb_plans(call: CallbackQuery) -> None:
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        plans = _active_plans(s)
        text = "Tariflar:\n\n" + "\n".join(T.plan_line(p, cfg.currency) for p in plans) if plans \
            else "Hozircha tariflar qo'shilmagan."
        markup = kb.plans_kb(plans)
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_detail(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        plan = s.get(Plan, pid)
        if not plan:
            await call.answer("Tarif topilmadi", show_alert=True)
            return
        text = T.plan_card(plan, cfg.currency)
    await call.message.edit_text(text, reply_markup=kb.plan_detail_kb(pid))
    await call.answer()


# --- Sotib olish (chek kutish) -------------------------------------------
async def _start_buy(call: CallbackQuery, state: FSMContext, plan_id: int, promo: str | None) -> None:
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        plan = s.get(Plan, plan_id)
        if not plan or not plan.is_active:
            await call.answer("Tarif mavjud emas", show_alert=True)
            return
        promo_obj = pay_svc.find_promo(s, promo) if promo else None
        if promo_obj and not promo_obj.is_valid(plan.id):
            promo_obj = None
        expected, discount = pay_svc.compute_amount(plan.price, promo_obj)
        text = T.payment_instructions(cfg, plan, expected, discount)
    await state.set_state(BuyFlow.waiting_receipt)
    await state.update_data(plan_id=plan_id, promo=(promo if promo_obj else None))
    await call.message.edit_text(text, reply_markup=kb.back_menu_kb())
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery, state: FSMContext) -> None:
    await _start_buy(call, state, int(call.data.split(":")[1]), promo=None)


@router.callback_query(F.data.startswith("buypromo:"))
async def cb_buy_promo(call: CallbackQuery, state: FSMContext) -> None:
    pid = int(call.data.split(":")[1])
    await state.set_state(BuyFlow.waiting_promo)
    await state.update_data(plan_id=pid)
    await call.message.edit_text("Promo kodingizni yuboring:", reply_markup=kb.back_menu_kb())
    await call.answer()


@router.message(BuyFlow.waiting_promo, F.text)
async def on_promo_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pid = data.get("plan_id")
    code = message.text.strip()
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        plan = s.get(Plan, pid)
        promo = pay_svc.find_promo(s, code)
        valid = bool(promo and promo.is_valid(pid) and plan)
        if valid:
            expected, discount = pay_svc.compute_amount(plan.price, promo)
            text = "✅ Promo qabul qilindi.\n\n" + T.payment_instructions(cfg, plan, expected, discount)
    if not valid:
        await message.answer("❌ Promo kod yaroqsiz. Keyinroq urinib ko'ring yoki promosiz davom eting.",
                             reply_markup=kb.plan_detail_kb(pid))
        await state.set_state(None)
        return
    await state.set_state(BuyFlow.waiting_receipt)
    await state.update_data(plan_id=pid, promo=code)
    await message.answer(text, reply_markup=kb.back_menu_kb())


@router.message(BuyFlow.waiting_receipt, F.photo | F.document)
async def on_receipt(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pid = data.get("plan_id")
    promo = data.get("promo")
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    else:
        file_id, kind = message.document.file_id, "document"

    with get_session() as s:
        plan = s.get(Plan, pid)
        user, _ = user_svc.get_or_create_user(
            s, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        if not plan:
            await message.answer("Tarif topilmadi.")
            await state.clear()
            return
        payment = pay_svc.create_payment(s, user, plan, file_id, kind, promo_code=promo)
        cfg = AppSettings.get_or_create(s)
        currency = cfg.currency
        # adminlarga yuborish uchun kerakli ma'lumotlarni olib qolamiz
        notice_link = f"{config.settings.public_base_url}/receipt/{payment.id}"
        notice_text = T.admin_payment_notice(user, plan, payment, currency, notice_link)
        pay_id = payment.id

    await state.clear()
    await message.answer("✅ Chek qabul qilindi. Admin tasdiqlagach obunangiz faollashadi.",
                         reply_markup=kb.back_menu_kb())

    # adminlarga chekni yuborish (chatda ko'rinadi) + panel link + qaror tugmalari
    for admin_id in config.settings.admin_id_list:
        try:
            if kind == "photo":
                await bot.send_photo(admin_id, file_id, caption=notice_text,
                                     reply_markup=kb.admin_decision_kb(pay_id))
            else:
                await bot.send_document(admin_id, file_id, caption=notice_text,
                                        reply_markup=kb.admin_decision_kb(pay_id))
        except Exception:
            pass  # bitta admin yetib bormasa, qolganlariga urinamiz


@router.message(BuyFlow.waiting_receipt)
async def on_receipt_wrong(message: Message) -> None:
    await message.answer("Iltimos, chek <b>rasmini</b> (yoki faylini) yuboring.")


# --- Mening obunam -------------------------------------------------------
@router.callback_query(F.data == "mysub")
async def cb_mysub(call: CallbackQuery) -> None:
    with get_session() as s:
        user = user_svc.get_user(s, call.from_user.id)
        sub = active_subscription(s, user.id) if user else None
        cfg = AppSettings.get_or_create(s)
        plan_name = s.get(Plan, sub.plan_id).name if sub else None
        text = T.sub_status(user, sub, plan_name, cfg.currency)
    await call.message.edit_text(text, reply_markup=kb.back_menu_kb())
    await call.answer()


# --- Ilovalar ------------------------------------------------------------
@router.callback_query(F.data == "apps")
async def cb_apps(call: CallbackQuery) -> None:
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        apk, srv = cfg.apk_url, cfg.server_installer_url
    lines = ["📥 <b>Ilovalar</b>", ""]
    lines.append(f"📱 Android (viewer): {apk}" if apk else "📱 Android (viewer): tez kunda")
    lines.append(f"💻 Windows server: {srv}" if srv else "💻 Windows server: tez kunda")
    await call.message.edit_text("\n".join(lines), reply_markup=kb.back_menu_kb(),
                                 disable_web_page_preview=True)
    await call.answer()


# --- Promo (menyu) -------------------------------------------------------
@router.callback_query(F.data == "promo")
async def cb_promo_info(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "🎟 Promo kod ishlatish: <b>Tariflar</b> → tarifni tanlang → <b>Promo bilan</b>.",
        reply_markup=kb.back_menu_kb(),
    )
    await call.answer()


# --- Referal -------------------------------------------------------------
@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery) -> None:
    with get_session() as s:
        cfg = AppSettings.get_or_create(s)
        if not cfg.referral_enabled:
            await call.answer("Referal tizimi o'chirilgan", show_alert=True)
            return
        user = user_svc.get_user(s, call.from_user.id)
        invited_count = len(s.exec(select(User).where(User.referred_by_id == user.id)).all())
        code = user.referral_code
        balance = user.balance
        percent = cfg.referral_bonus_percent
        currency = cfg.currency
    uname = await bot_username()
    link = f"https://t.me/{uname}?start={code}" if uname else f"Kod: {code}"
    text = (
        "👥 <b>Referal dastur</b>\n\n"
        f"Har bir taklif qilgan do'stingiz to'lov qilganda, siz uning summasidan "
        f"<b>{percent}%</b> bonus olasiz.\n\n"
        f"Sizning havolangiz:\n{link}\n\n"
        f"Taklif qilinganlar: <b>{invited_count}</b>\n"
        f"Balans: <b>{T.fmt_money(balance, currency)}</b>"
    )
    await call.message.edit_text(text, reply_markup=kb.back_menu_kb(), disable_web_page_preview=True)
    await call.answer()
