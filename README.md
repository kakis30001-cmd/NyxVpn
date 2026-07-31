# Nyx VPN Bot

Полноценная система продажи VPN через Telegram-бота с WebApp, интеграцией 3X-UI и платежной системой platega.io.

## Стек

- **aiogram 3** — Telegram-бот
- **FastAPI + Uvicorn** — WebApp и webhook platega.io
- **aiosqlite** — асинхронная SQLite
- **APScheduler** — фоновая проверка подписок
- **aiohttp** — HTTP-клиент для 3X-UI и platega.io

## Структура проекта

```
nyx_vpn_bot/
├── app/
│   ├── __init__.py
│   ├── config.py          # конфигурация
│   ├── database.py        # работа с SQLite
│   ├── utils.py           # утилиты
│   ├── bot.py             # aiogram роутеры
│   ├── scheduler.py       # APScheduler задачи
│   ├── api_clients/
│   │   ├── xui.py         # клиент 3X-UI
│   │   └── platega.py     # клиент platega.io
│   └── webapp/
│       ├── app.py         # FastAPI приложение
│       ├── templates/
│       │   └── index.html # WebApp SPA
│       └── static/        # статические файлы
├── main.py                # точка входа
├── requirements.txt
├── .env.example
└── README.md
```

## Установка

1. Установите зависимости:

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Скопируйте `.env.example` в `.env` и заполните реальными значениями.

3. Запустите:

```bash
python main.py
```

## Конфигурация

Все настройки берутся из `.env` (или `app/config.py`). Обязательные поля:

- `BOT_TOKEN` — токен от @BotFather
- `ADMIN_IDS` — ID администраторов через запятую
- `WEBAPP_PUBLIC_URL` — публичный URL вашего WebApp
- `XUI_BASE_URL`, `XUI_USERNAME`, `XUI_PASSWORD`, `XUI_INBOUND_ID`
- `PLATEGA_API_KEY`, `PLATEGA_MERCHANT_ID`

## Настройка WebApp в BotFather

В @BotFather выполните `/mybots` → выберите бота → `Bot Settings` → `Menu Button` → `Configure menu button`:

- Menu button title: `Открыть Nyx VPN`
- URL: ваш `WEBAPP_PUBLIC_URL`

## Подключение 3X-UI

1. В панели 3X-UI создайте inbound с протоколом VLESS.
2. Узнайте его ID (колонка ID в списке inbounds).
3. Укажите этот ID в `XUI_INBOUND_ID`.

Бот автоматически создает клиентов с нужным `limitIP` и сроком действия.

## Подключение platega.io

1. Зарегистрируйтесь и получите API-ключ и Merchant ID.
2. Укажите их в `.env`.
3. В личном кабинете platega.io установите webhook URL: `{WEBAPP_PUBLIC_URL}/webhook/platega`.

**Важно:** реальные эндпоинты и формат webhook platega.io могут отличаться. При необходимости скорректируйте `app/api_clients/platega.py` и обработчик `app/webapp/app.py::webhook_platega` под актуальную документацию.

## Процесс работы

1. Пользователь пишет `/start` → бот отправляет приветствие и кнопку WebApp.
2. В WebApp пользователь:
   - видит статус подписки и таймер;
   - может активировать пробный период (1 день, 2 устройства);
   - выбирает тариф и оплачивает через platega.io.
3. После успешной оплаты webhook активирует подписку, создает/продляет клиента в 3X-UI и отправляет ключ.
4. Раз в сутки планировщик проверяет сроки и отправляет уведомления за 24ч/3 дня, а при истечении — отключает клиента.

## Админ-команды

- `/admin` — статистика (только для `ADMIN_IDS`, для остальных команда полностью игнорируется)
- `/broadcast текст` — рассылка всем пользователям

## Безопасность

- Не коммитьте `.env` в публичный репозиторий.
- Используйте HTTPS для WebApp и webhook'а.
- Для production рекомендуется добавить rate limiting и валидацию initData Telegram WebApp.
