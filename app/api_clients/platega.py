"""
Асинхронный клиент для API platega.io.

ВНИМАНИЕ: Точные эндпоинты и поля запроса/ответа platega.io
должны быть уточнены в официальной документации платежной системы.
Ниже приведена типичная структура для крипто/фиатных шлюзов.
"""

import json
from typing import Optional, Dict, Any

import aiohttp
from app.config import CONFIG


class PlategaError(Exception):
    pass


class PlategaClient:
    def __init__(self):
        self.base_url = CONFIG.PLATEGA_API_URL.rstrip("/")
        self.api_key = CONFIG.PLATEGA_API_KEY
        self.merchant_id = CONFIG.PLATEGA_MERCHANT_ID

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_payment(
        self,
        order_id: str,
        amount: int,
        description: str,
        user_id: int,
        return_url: str,
        webhook_url: str,
    ) -> Dict[str, Any]:
        """
        Создает счет на оплату.

        Возвращает словарь с минимум полем payment_url.
        """
        url = f"{self.base_url}/invoices"
        payload = {
            "merchant_id": self.merchant_id,
            "order_id": order_id,
            "amount": amount,
            "currency": "RUB",
            "description": description,
            "callback_url": webhook_url,
            "return_url": return_url,
            "metadata": {"telegram_id": user_id},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._headers(), json=payload, ssl=True
            ) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"raw": text}

                if resp.status == 404:
                    raise PlategaError(
                        "Оплата временно недоступна. Пожалуйста, свяжитесь с поддержкой."
                    )

                if resp.status not in (200, 201):
                    raise PlategaError(
                        f"HTTP {resp.status}: {data}"
                    )

                # Поддержка разных форматов ответа
                payment_url = (
                    data.get("payment_url")
                    or data.get("url")
                    or data.get("data", {}).get("payment_url")
                    or data.get("invoice", {}).get("payment_url")
                )
                if not payment_url:
                    raise PlategaError(f"Не получен payment_url: {data}")

                return {
                    "success": True,
                    "payment_url": payment_url,
                    "order_id": data.get("order_id") or order_id,
                    "raw": data,
                }

    def verify_webhook(self, headers: Dict[str, str], body: bytes, signature: str) -> bool:
        """
        Проверяет подпись webhook от platega.io.
        Если platega не использует подпись — вернет True.
        """
        if not signature:
            return True
        try:
            import hmac
            import hashlib

            expected = hmac.new(
                self.api_key.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def parse_webhook(self, body: bytes) -> Dict[str, Any]:
        """Парсит тело webhook."""
        return json.loads(body)
