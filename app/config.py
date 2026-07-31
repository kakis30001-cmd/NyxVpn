"""
Главный конфигурационный файл Nyx VPN Bot.
Заполните все поля в секции CONFIG ниже перед запуском.
"""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Конфигурация приложения."""

    # ========== Telegram Bot ==========
    BOT_TOKEN: str = ""
    # Пример: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    # ========== Администраторы ==========
    ADMIN_IDS: List[int] = field(default_factory=list)
    # Пример: [123456789, 987654321]

    # ========== WebApp ==========
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = 8000
    WEBAPP_PUBLIC_URL: str = ""
    # Публичный URL, по которому Telegram откроет WebApp.
    # Пример: "https://your-domain.com"
    # Для локального теста через ngrok: "https://xxxx.ngrok-free.app"

    # ========== 3X-UI Panel ==========
    XUI_BASE_URL: str = ""
    # URL панели 3X-UI. Пример: "https://vpn.your-domain.com:54321"
    XUI_USERNAME: str = ""
    XUI_PASSWORD: str = ""
    XUI_INBOUND_ID: int = 1
    # Основной ID inbound'а в панели 3X-UI (для обратной совместимости).
    XUI_INBOUND_IDS: List[int] = field(default_factory=lambda: [1])
    # Список ID inbound'ов, в которые добавлять клиентов. Если пустой — используется XUI_INBOUND_ID.
    # Узнать можно в панели: Inbounds -> номер колонки ID.

    # ========== Platega.io ==========
    PLATEGA_API_KEY: str = ""
    PLATEGA_MERCHANT_ID: str = ""
    PLATEGA_API_URL: str = "https://api.platega.io/v1"
    # Уточните базовый URL API у поддержки platega.io.

    # ========== Приложение ==========
    DATABASE_PATH: str = "nyx_vpn.db"
    LOG_LEVEL: str = "INFO"
    TRIAL_DAYS: int = 1
    # Срок триала в днях.

    # Тарифы (месяцы -> {дни, цена, лимит устройств})
    PLANS: dict = field(default_factory=dict)


# ========== ЗАПОЛНИТЕ ЭТИ ПОЛЯ ==========
CONFIG = Config(
    BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
    ADMIN_IDS=[int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x] or [],

    WEBAPP_HOST=os.getenv("WEBAPP_HOST", "0.0.0.0"),
    WEBAPP_PORT=int(os.getenv("WEBAPP_PORT", "8000")),
    WEBAPP_PUBLIC_URL=os.getenv("WEBAPP_PUBLIC_URL", ""),

    XUI_BASE_URL=os.getenv("XUI_BASE_URL", ""),
    XUI_USERNAME=os.getenv("XUI_USERNAME", ""),
    XUI_PASSWORD=os.getenv("XUI_PASSWORD", ""),
    XUI_INBOUND_ID=int(os.getenv("XUI_INBOUND_ID", "1")),
    XUI_INBOUND_IDS=[int(x.strip()) for x in os.getenv("XUI_INBOUND_IDS", "").split(",") if x.strip()] or [int(os.getenv("XUI_INBOUND_ID", "1"))],

    PLATEGA_API_KEY=os.getenv("PLATEGA_API_KEY", ""),
    PLATEGA_MERCHANT_ID=os.getenv("PLATEGA_MERCHANT_ID", ""),
    PLATEGA_API_URL=os.getenv("PLATEGA_API_URL", "https://api.platega.io/v1"),

    DATABASE_PATH=os.getenv("DATABASE_PATH", "nyx_vpn.db"),
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
    TRIAL_DAYS=int(os.getenv("TRIAL_DAYS", "1")),

    PLANS={
        "1m": {"days": 30, "price": 149, "devices": 2, "title": "1 месяц"},
        "3m": {"days": 90, "price": 299, "devices": 3, "title": "3 месяца"},
        "6m": {"days": 180, "price": 549, "devices": 5, "title": "6 месяцев"},
        "1y": {"days": 365, "price": 999, "devices": 8, "title": "1 год"},
    },
)


# Валидация обязательных полей при импорте
def validate_config():
    required = [
        ("BOT_TOKEN", CONFIG.BOT_TOKEN),
        ("ADMIN_IDS", CONFIG.ADMIN_IDS),
        ("WEBAPP_PUBLIC_URL", CONFIG.WEBAPP_PUBLIC_URL),
        ("XUI_BASE_URL", CONFIG.XUI_BASE_URL),
        ("XUI_USERNAME", CONFIG.XUI_USERNAME),
        ("XUI_PASSWORD", CONFIG.XUI_PASSWORD),
        ("PLATEGA_API_KEY", CONFIG.PLATEGA_API_KEY),
        ("PLATEGA_MERCHANT_ID", CONFIG.PLATEGA_MERCHANT_ID),
    ]
    missing = [name for name, value in required if not value]
    if missing:
        raise RuntimeError(
            f"Заполните обязательные настройки в app/config.py или через env: {', '.join(missing)}"
        )
