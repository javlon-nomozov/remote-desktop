"""Konfiguratsiya — muhit o'zgaruvchilari (.env yoki Railway env).

.env loyiha ildizida (c:\\Users\\User\\Desktop\\anydesk-clone\\.env) kutiladi. Railway'da
esa env o'zgaruvchilar dashboard orqali beriladi (ular .env qiymatidan ustun turadi).
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> [0]=app, [1]=backend, [2]=loyiha ildizi
ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # --- Telegram bot ---
    bot_token: str = ""
    # vergul bilan ajratilgan admin telegram user id'lari, masalan "12345678,9999"
    admin_ids: str = ""

    # --- Ma'lumotlar bazasi ---
    # Lokal: sqlite; Railway: postgresql://...  (DATABASE_URL avtomatik beriladi)
    database_url: str = "sqlite:///./remote.db"

    # --- Admin panel (SQLAdmin) kirish ---
    admin_panel_user: str = "admin"
    admin_panel_password: str = "change-me"
    admin_session_secret: str = "dev-secret-change-me"

    # --- Umumiy ---
    # Railway service public URL, masalan https://xxx.up.railway.app  (oxirida / yo'q)
    public_base_url: str = "http://localhost:8000"

    # Relay: viewer ulanishida faol obunani majburiy qilish (True bo'lsa token kerak)
    relay_require_subscription: bool = False

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def admin_id_list(self) -> list[int]:
        out: list[int] = []
        for part in self.admin_ids.replace(" ", "").split(","):
            if part:
                try:
                    out.append(int(part))
                except ValueError:
                    pass
        return out

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_id_list


settings = Settings()
