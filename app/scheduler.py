"""
Фоновые задачи APScheduler.
"""

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import database as db
from app.api_clients.xui import XUIClient
from app.bot import notify_user


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def check_subscriptions():
    """
    Проверка подписок раз в сутки:
    - уведомление за 24 часа и за 3 дня
    - отключение/удаление при истечении
    """
    logger.info("Запуск проверки подписок")
    now = datetime.datetime.utcnow()
    day = datetime.timedelta(days=1)
    three_days = datetime.timedelta(days=3)

    xui = XUIClient()
    users = await db.get_all_users()

    for user in users:
        sub = await db.get_subscription(user["id"])
        if not sub or not sub.get("expiry_at"):
            continue

        expiry = datetime.datetime.fromisoformat(sub["expiry_at"])
        if expiry.tzinfo:
            expiry = expiry.replace(tzinfo=None)

        diff = expiry - now

        # Истекла
        if diff.total_seconds() <= 0:
            logger.info(f"Подписка истекла: user={user['telegram_id']}")
            if sub.get("xui_uuid"):
                try:
                    await xui.disable_or_delete_client(sub["xui_uuid"])
                except Exception as e:
                    logger.error(f"Ошибка отключения клиента: {e}")
            await db.deactivate_subscription(user["id"])
            await notify_user(
                user["telegram_id"],
                "Срок действия вашей подписки Nyx VPN истек. Чтобы продолжить пользоваться VPN, оформите подписку в меню.",
            )
            continue

        # Уведомление за 24 часа (проверяем окно +/- 30 мин)
        if day <= diff <= day + datetime.timedelta(minutes=30):
            await notify_user(
                user["telegram_id"],
                "Напоминание: ваша подписка Nyx VPN истекает через 24 часа. Не забудьте продлить доступ.",
            )

        # Уведомление за 3 дня
        if three_days <= diff <= three_days + datetime.timedelta(minutes=30):
            await notify_user(
                user["telegram_id"],
                "Напоминание: ваша подписка Nyx VPN истекает через 3 дня. Продлите подписку заранее.",
            )


def setup_scheduler():
    """Настройка и запуск планировщика."""
    scheduler.add_job(
        check_subscriptions,
        "cron",
        hour=10,
        minute=0,
        id="subscriptions_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик запущен")
