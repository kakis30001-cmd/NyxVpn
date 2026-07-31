"""
Работа с SQLite через aiosqlite.
"""

import aiosqlite
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import CONFIG


DB_PATH = Path(CONFIG.DATABASE_PATH)


async def init_db():
    """Инициализация таблиц базы данных."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                plan_code TEXT,
                plan_title TEXT,
                expiry_at TIMESTAMP,
                devices_limit INTEGER DEFAULT 2,
                xui_uuid TEXT,
                xui_email TEXT,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                amount INTEGER NOT NULL,
                platega_order_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS trial_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_expiry ON subscriptions(expiry_at);
            CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(platega_order_id);
            """
        )
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Получение соединения с БД."""
    return await aiosqlite.connect(DB_PATH)


async def add_or_update_user(
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
) -> int:
    """Добавляет пользователя или обновляет его данные. Возвращает внутренний id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
            RETURNING id
            """,
            (telegram_id, username, first_name, last_name),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0]


async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Получить пользователя по telegram_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    """Получить активную подписку пользователя по внутреннему user_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_subscription_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Получить подписку по telegram_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT s.* FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE u.telegram_id = ?
            """,
            (telegram_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_or_update_subscription(
    user_id: int,
    plan_code: str,
    plan_title: str,
    expiry_at: datetime.datetime,
    devices_limit: int,
    xui_uuid: str,
    xui_email: str,
    is_active: bool = True,
):
    """Создает или обновляет подписку пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions
                (user_id, plan_code, plan_title, expiry_at, devices_limit,
                 xui_uuid, xui_email, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan_code=excluded.plan_code,
                plan_title=excluded.plan_title,
                expiry_at=excluded.expiry_at,
                devices_limit=excluded.devices_limit,
                xui_uuid=excluded.xui_uuid,
                xui_email=excluded.xui_email,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                plan_code,
                plan_title,
                expiry_at,
                devices_limit,
                xui_uuid,
                xui_email,
                int(is_active),
                datetime.datetime.utcnow(),
            ),
        )
        await db.commit()


async def deactivate_subscription(user_id: int):
    """Деактивирует подписку."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET is_active = 0, updated_at = ? WHERE user_id = ?",
            (datetime.datetime.utcnow(), user_id),
        )
        await db.commit()


async def has_used_trial(user_id: int) -> bool:
    """Проверяет, использовал ли пользователь триал."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM trial_log WHERE user_id = ?", (user_id,)
        ) as cursor:
            return bool(await cursor.fetchone())


async def mark_trial_used(user_id: int):
    """Отмечает, что пользователь использовал триал."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO trial_log (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()


async def create_payment(user_id: int, plan_code: str, amount: int) -> int:
    """Создает запись о платеже. Возвращает id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO payments (user_id, plan_code, amount)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            (user_id, plan_code, amount),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0]


async def update_payment_order_id(payment_id: int, order_id: str):
    """Сохраняет внешний order_id платежа."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET platega_order_id = ? WHERE id = ?",
            (order_id, payment_id),
        )
        await db.commit()


async def get_payment_by_order_id(order_id: str) -> Optional[Dict[str, Any]]:
    """Получить платеж по order_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE platega_order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def mark_payment_paid(order_id: str):
    """Отмечает платеж оплаченным."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE payments
            SET status = 'paid', paid_at = ?
            WHERE platega_order_id = ?
            """,
            (datetime.datetime.utcnow(), order_id),
        )
        await db.commit()


async def get_all_users() -> List[Dict[str, Any]]:
    """Получить всех пользователей."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_stats() -> Dict[str, int]:
    """Получить статистику для админки."""
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        active_subs = await (
            await db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE is_active = 1 AND expiry_at > ?",
                (datetime.datetime.utcnow(),),
            )
        ).fetchone()
        revenue = await (
            await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"
            )
        ).fetchone()
        return {
            "total_users": total_users[0],
            "active_subscriptions": active_subs[0],
            "total_revenue": revenue[0],
        }
