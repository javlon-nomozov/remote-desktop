"""Admin panel (SQLAdmin) — tariflar, sozlamalar, to'lovlar, userlar, promo.

Oddiy login/parol himoyasi (.env dan). Bu — shaxsiy admin panel uchun yetarli.
"""
from __future__ import annotations

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from .config import settings
from .db import engine
from .models import (
    AppSettings,
    BalanceTx,
    Payment,
    Plan,
    PromoCode,
    Subscription,
    User,
)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        if (
            form.get("username") == settings.admin_panel_user
            and form.get("password") == settings.admin_panel_password
        ):
            request.session.update({"auth": "ok"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("auth") == "ok"


class SettingsAdmin(ModelView, model=AppSettings):
    name = "Sozlama"
    name_plural = "Sozlamalar"
    icon = "fa-solid fa-gear"
    column_list = [AppSettings.id, AppSettings.card_number, AppSettings.card_holder,
                   AppSettings.currency, AppSettings.referral_enabled,
                   AppSettings.referral_bonus_percent]
    can_create = False
    can_delete = False


class PlanAdmin(ModelView, model=Plan):
    name = "Tarif"
    name_plural = "Tariflar"
    icon = "fa-solid fa-tags"
    column_list = [Plan.id, Plan.name, Plan.price, Plan.duration_days, Plan.max_devices,
                   Plan.is_active, Plan.sort_order]
    column_searchable_list = [Plan.name]
    column_sortable_list = [Plan.sort_order, Plan.price]


class PromoAdmin(ModelView, model=PromoCode):
    name = "Promo kod"
    name_plural = "Promo kodlar"
    icon = "fa-solid fa-ticket"
    column_list = [PromoCode.id, PromoCode.code, PromoCode.discount_percent,
                   PromoCode.used_count, PromoCode.max_uses, PromoCode.is_active,
                   PromoCode.expires_at]
    column_searchable_list = [PromoCode.code]


class UserAdmin(ModelView, model=User):
    name = "Foydalanuvchi"
    name_plural = "Foydalanuvchilar"
    icon = "fa-solid fa-users"
    column_list = [User.id, User.telegram_id, User.username, User.full_name,
                   User.balance, User.referral_code, User.referred_by_id, User.is_blocked]
    column_searchable_list = [User.username, User.telegram_id]
    can_create = False


class SubscriptionAdmin(ModelView, model=Subscription):
    name = "Obuna"
    name_plural = "Obunalar"
    icon = "fa-solid fa-calendar-check"
    column_list = [Subscription.id, Subscription.user_id, Subscription.plan_id,
                   Subscription.starts_at, Subscription.expires_at, Subscription.is_active]


class PaymentAdmin(ModelView, model=Payment):
    name = "To'lov"
    name_plural = "To'lovlar"
    icon = "fa-solid fa-receipt"
    column_list = [Payment.id, Payment.user_id, Payment.plan_id, Payment.expected_amount,
                   Payment.paid_amount, Payment.status, Payment.created_at, Payment.decided_at]
    column_sortable_list = [Payment.created_at, Payment.status]
    can_create = False


class BalanceTxAdmin(ModelView, model=BalanceTx):
    name = "Balans amali"
    name_plural = "Balans daftari"
    icon = "fa-solid fa-coins"
    column_list = [BalanceTx.id, BalanceTx.user_id, BalanceTx.amount, BalanceTx.reason,
                   BalanceTx.ref_payment_id, BalanceTx.created_at]
    can_create = False
    can_edit = False


def setup_admin(app) -> Admin:
    backend = AdminAuth(secret_key=settings.admin_session_secret)
    admin = Admin(app, engine, authentication_backend=backend, title="Remote Desktop Admin")
    admin.add_view(SettingsAdmin)
    admin.add_view(PlanAdmin)
    admin.add_view(PromoAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(SubscriptionAdmin)
    admin.add_view(PaymentAdmin)
    admin.add_view(BalanceTxAdmin)
    return admin
