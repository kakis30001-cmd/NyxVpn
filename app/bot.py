"""
Telegram-бот на aiogram 3.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, WebAppInfo, MenuButtonWebApp, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import CONFIG
from app import database as db
from app.utils import format_subscription_key


logging.basicConfig(level=getattr(logging, CONFIG.LOG_LEVEL))
logger = logging.getLogger(__name__)

bot = Bot(token=CONFIG.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()


# ========== Утилиты ==========

async def notify_user(telegram_id: int, text: str):
    """Отправить сообщение пользователю."""
    try:
        await bot.send_message(telegram_id, text)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение {telegram_id}: {e}")


# ========== Команды ==========

@router.message(Command("start"))
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    await db.add_or_update_user(telegram_id, username, first_name, last_name)

    web_app_url = CONFIG.WEBAPP_PUBLIC_URL
    if not web_app_url.startswith("http"):
        web_app_url = f"https://{web_app_url}"

    # Устанавливаем кнопку меню WebApp
    await bot.set_chat_menu_button(
        chat_id=telegram_id,
        menu_button=MenuButtonWebApp(
            text="Открыть Nyx VPN",
            web_app=WebAppInfo(url=web_app_url),
        ),
    )

    await message.answer(
        "Привет! Это Nyx VPN — надежный и быстрый VPN по очень доступным ценам.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть меню",
                        web_app=WebAppInfo(url=web_app_url),
                    )
                ]
            ]
        ),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Скрытая админ-панель. Если пользователя нет в списке — полное игнорирование."""
    if message.from_user.id not in CONFIG.ADMIN_IDS:
        return  # полностью игнорируем

    stats = await db.get_stats()
    text = (
        "<b>Админ-панель Nyx VPN</b>\n\n"
        f"Пользователей всего: {stats['total_users']}\n"
        f"Активных подписок: {stats['active_subscriptions']}\n"
        f"Общая выручка: {stats['total_revenue']}₽\n\n"
        "Команды:\n"
        "/broadcast текст — рассылка всем пользователям"
    )
    await message.answer(text)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    """Рассылка текста всем пользователям. Только для админов."""
    if message.from_user.id not in CONFIG.ADMIN_IDS:
        return

    text = command.args
    if not text:
        await message.answer("Использование: /broadcast Ваше сообщение")
        return

    users = await db.get_all_users()
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)  # небольшая задержка
        except Exception as e:
            logger.error(f"Рассылка не удалась для {user['telegram_id']}: {e}")
            failed += 1

    await message.answer(f"Рассылка завершена. Отправлено: {sent}, ошибок: {failed}.")


# ========== Регистрация роутеров ==========

dp.include_router(router)


# ========== Запуск ==========

async def start_bot():
    await dp.start_polling(bot)
