"""
FastAPI приложение для WebApp и webhook'ов.
"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import CONFIG
from app import database as db
from app.api_clients.xui import XUIClient


logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Статические файлы (если понадобятся) — fallback на рут
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница WebApp."""
    html_path = BASE_DIR / "templates" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/me")
async def api_me(request: Request):
    """Возвращает данные о пользователе и подписке по telegram_id."""
    logger.info(f"/api/me request from {request.headers.get('origin')}")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"/api_me parse error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id required")

    user = await db.get_user_by_telegram_id(int(telegram_id))
    if not user:
        # Создаем пользователя при первом открытии WebApp
        # Имя берем из initData, но здесь упрощенно
        user_id = await db.add_or_update_user(
            telegram_id=int(telegram_id),
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        user = await db.get_user_by_telegram_id(int(telegram_id))
    else:
        user_id = user["id"]

    subscription = await db.get_subscription(user_id)
    trial_used = await db.has_used_trial(user_id)

    return JSONResponse(
        {
            "user": {
                "telegram_id": telegram_id,
                "first_name": user.get("first_name"),
                "username": user.get("username"),
            },
            "subscription": subscription,
            "trial_used": trial_used,
        }
    )


@app.post("/api/activate-trial")
async def api_activate_trial(request: Request):
    """Активирует пробный период."""
    logger.info(f"/api/activate-trial request")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"/api_activate_trial parse error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    telegram_id = int(data.get("telegram_id"))
    user = await db.get_user_by_telegram_id(telegram_id)
    if not user:
        # Автоматически создаем пользователя, если его нет
        logger.info(f"Auto-creating user: {telegram_id}")
        await db.add_or_update_user(
            telegram_id=telegram_id,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        user = await db.get_user_by_telegram_id(telegram_id)

    user_id = user["id"]
    if await db.has_used_trial(user_id):
        raise HTTPException(status_code=403, detail="Trial already used")

    xui = XUIClient()
    try:
        client = await xui.add_client(
            telegram_id=telegram_id,
            days=CONFIG.TRIAL_DAYS,
            limit_ip=2,
            total_gb=100 * 1024 * 1024 * 1024,
        )
    except Exception as e:
        logger.exception("3X-UI add_client failed")
        raise HTTPException(status_code=502, detail=f"3X-UI error: {e}")

    import datetime

    await db.create_or_update_subscription(
        user_id=user_id,
        plan_code="trial",
        plan_title="Пробный период",
        expiry_at=datetime.datetime.utcnow() + datetime.timedelta(days=CONFIG.TRIAL_DAYS),
        devices_limit=2,
        xui_uuid=client["uuid"],
        xui_email=client["email"],
        is_active=True,
    )
    await db.mark_trial_used(user_id)

    # Формируем единую base64-подписку со всеми серверами
    import base64
    subscription = "\n".join([l["link"] for l in client["links"] if l["link"]])
    subscription_b64 = base64.b64encode(subscription.encode()).decode()
    return JSONResponse({"success": True, "key": subscription_b64})


@app.post("/api/create-payment")
async def api_create_payment(request: Request):
    """Создает платеж и возвращает ссылку."""
    from app.api_clients.platega import PlategaClient

    logger.info(f"/api/create-payment request")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"/api_create_payment parse error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    telegram_id = int(data.get("telegram_id"))
    plan_code = data.get("plan_code")

    plan = CONFIG.PLANS.get(plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan")

    user = await db.get_user_by_telegram_id(telegram_id)
    if not user:
        logger.info(f"Auto-creating user: {telegram_id}")
        await db.add_or_update_user(
            telegram_id=telegram_id,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        user = await db.get_user_by_telegram_id(telegram_id)

    user_id = user["id"]
    payment_id = await db.create_payment(user_id, plan_code, plan["price"])
    order_id = f"nyxvpn_{payment_id}"
    await db.update_payment_order_id(payment_id, order_id)

    platega = PlategaClient()
    try:
        result = await platega.create_payment(
            order_id=order_id,
            amount=plan["price"],
            description=f"Nyx VPN {plan['title']}",
            user_id=telegram_id,
            return_url=f"{CONFIG.WEBAPP_PUBLIC_URL}",
            webhook_url=f"{CONFIG.WEBAPP_PUBLIC_URL}/webhook/platega",
        )
    except Exception as e:
        logger.exception("Platega create_payment failed")
        raise HTTPException(status_code=502, detail=f"Payment error: {e}")

    return JSONResponse({"success": True, "payment_url": result["payment_url"]})


@app.post("/webhook/platega")
async def webhook_platega(request: Request):
    """Обработчик webhook'ов от platega.io."""
    from app.api_clients.platega import PlategaClient
    from app.bot import notify_user  # отложенный импорт
    import datetime

    body = await request.body()
    platega = PlategaClient()

    signature = request.headers.get("X-Platega-Signature", "")
    if not platega.verify_webhook(dict(request.headers), body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = platega.parse_webhook(body)

    # Определяем статус платежа (форматы могут отличаться)
    status = (
        payload.get("status")
        or payload.get("payment_status")
        or payload.get("data", {}).get("status")
    )
    order_id = (
        payload.get("order_id")
        or payload.get("external_id")
        or payload.get("data", {}).get("order_id")
    )

    if status not in ("paid", "success", "completed"):
        return JSONResponse({"ok": True})

    payment = await db.get_payment_by_order_id(order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["status"] == "paid":
        return JSONResponse({"ok": True})

    await db.mark_payment_paid(order_id)

    user_id = payment["user_id"]
    plan_code = payment["plan_code"]
    plan = CONFIG.PLANS[plan_code]

    user = await db.get_user_by_telegram_id(payment["user_id"])
    telegram_id = user["telegram_id"]

    xui = XUIClient()
    existing_sub = await db.get_subscription(user_id)

    if existing_sub and existing_sub.get("xui_uuid"):
        # Продление
        try:
            await xui.update_client_expiry(
                existing_sub["xui_uuid"], plan["days"], plan["devices"]
            )
            new_expiry = max(
                existing_sub["expiry_at"],
                datetime.datetime.utcnow(),
            ) + datetime.timedelta(days=plan["days"])
        except Exception:
            # Если клиента нет, создадим нового
            client = await xui.add_client(
                telegram_id=telegram_id,
                days=plan["days"],
                limit_ip=plan["devices"],
                total_gb=0,
                existing_uuid=existing_sub["xui_uuid"],
            )
            new_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=plan["days"])
            existing_sub = {"xui_uuid": client["uuid"], "xui_email": client["email"]}
    else:
        client = await xui.add_client(
            telegram_id=telegram_id,
            days=plan["days"],
            limit_ip=plan["devices"],
            total_gb=0,
        )
        new_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=plan["days"])
        existing_sub = {"xui_uuid": client["uuid"], "xui_email": client["email"]}

    await db.create_or_update_subscription(
        user_id=user_id,
        plan_code=plan_code,
        plan_title=plan["title"],
        expiry_at=new_expiry,
        devices_limit=plan["devices"],
        xui_uuid=existing_sub["xui_uuid"],
        xui_email=existing_sub["xui_email"],
        is_active=True,
    )

    # Отправляем ссылки в Telegram
    xui_client = await xui.get_inbound()
    links = [
        xui._build_vless_link(await xui.get_inbound_by_id(iid), existing_sub["xui_uuid"])
        for iid in CONFIG.XUI_INBOUND_IDS
    ]
    links_text = "\n\n".join([format_subscription_key(link) for link in links if link])
    await notify_user(
        telegram_id,
        f"Оплата прошла успешно! Ваша подписка «{plan['title']}» активна.\n\n{links_text}",
    )

    return JSONResponse({"ok": True, "links": links})


def format_subscription_key(link: str) -> str:
    return f"Ваш ключ доступа:\n\n<code>{link}</code>\n\nСкопируйте его и вставьте в приложение VLESS."
