"""
Точка входа Nyx VPN Bot.
Запускает одновременно:
- FastAPI WebApp (+ webhook platega)
- aiogram Telegram-бот
- APScheduler фоновые задачи
"""

import asyncio
import logging
import signal
import uvicorn

from app.config import CONFIG, validate_config
from app.webapp.app import app as fastapi_app
from app.bot import start_bot, bot, dp
from app.scheduler import setup_scheduler, scheduler
from app import database as db


# ASGI/WSGI entry point for Railway / uvicorn
app = fastapi_app


logging.basicConfig(
    level=getattr(logging, CONFIG.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_webapp():
    """Запуск FastAPI через uvicorn."""
    config = uvicorn.Config(
        fastapi_app,
        host=CONFIG.WEBAPP_HOST,
        port=CONFIG.WEBAPP_PORT,
        log_level=CONFIG.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    validate_config()
    await db.init_db()
    setup_scheduler()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def on_signal(sig):
        logger.info(f"Получен сигнал {sig}, завершаем работу...")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: on_signal(s))

    logger.info("Запуск Nyx VPN Bot...")
    webapp_task = asyncio.create_task(run_webapp())
    bot_task = asyncio.create_task(start_bot())

    # Ждем сигнала остановки
    await stop_event.wait()

    logger.info("Останавливаем компоненты...")
    webapp_task.cancel()
    bot_task.cancel()
    scheduler.shutdown(wait=False)
    try:
        await bot.session.close()
    except Exception as e:
        logger.warning(f"Ошибка закрытия сессии бота: {e}")

    try:
        await webapp_task
    except asyncio.CancelledError:
        pass
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    logger.info("Nyx VPN Bot остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
