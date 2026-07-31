"""
Точка входа Nyx VPN Bot.
Запускает одновременно:
- FastAPI WebApp (+ webhook platega)
- aiogram Telegram-бот
- APScheduler фоновые задачи
"""

import asyncio
import logging
import uvicorn

from app.config import CONFIG, validate_config
from app.webapp.app import app as fastapi_app
from app.bot import start_bot
from app.scheduler import setup_scheduler
from app import database as db


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

    logger.info("Запуск Nyx VPN Bot...")
    await asyncio.gather(
        run_webapp(),
        start_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
