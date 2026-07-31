"""
Вспомогательные функции.
"""

import uuid
import datetime
from typing import Optional


def generate_uuid() -> str:
    """Генерация UUID для клиента 3X-UI."""
    return str(uuid.uuid4())


def generate_email(telegram_id: int) -> str:
    """Генерация уникального email для клиента 3X-UI."""
    return f"user_{telegram_id}@nyxvpn.ru"


def format_subscription_key(link: str) -> str:
    """Форматирование ключа для пользователя."""
    return f"Ваш ключ доступа:\n\n<code>{link}</code>\n\nСкопируйте его и вставьте в приложение VLESS."


def days_hours_minutes(end: Optional[datetime.datetime]) -> str:
    """Возвращает строку дни:часы:минуты до окончания подписки."""
    if not end:
        return "00:00:00"
    now = datetime.datetime.utcnow()
    diff = end - now
    if diff.total_seconds() <= 0:
        return "00:00:00"
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days:02d}:{hours:02d}:{minutes:02d}"


def expiry_from_now(days: int) -> datetime.datetime:
    """Дата окончания подписки через N дней."""
    return datetime.datetime.utcnow() + datetime.timedelta(days=days)
