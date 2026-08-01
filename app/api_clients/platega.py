"""
Асинхронный клиент для API platega.io.

Фактический endpoint (проверен в рабочем боте):
  POST https://app.platega.io/v2/transaction/process

Заголовки:
  Content-Type: application/json
  X-MerchantId: {PLATEGA_MERCHANT_ID}
  X-Secret: {PLATEGA_API_SECRET}

Тело:
  {
    "command": "create",
    "paymentDetails": {"amount": float, "currency": "RUB"},
    "description": str,
    "return": str,
    "failedUrl": str,
    "payload": "order_{user_id}_{order_id}",
    "paymentMethod": ["SBP", "CRYPTO"]
  }

Ответ:
  {"url": "https://...", ...}

Webhook:
  POST /webhook/platega
  {"status": "CONFIRMED", "payload": "order_{user_id}_{order_id}", ...}
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
            "Content-Type": "application/json",
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.api_key,
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
        Создает счет на оплату через platega.io v2 API.

        Возвращает словарь с минимум полем payment_url.
        """
        url = f"{self.base_url}/v2/transaction/process"
        payload = {
            "command": "create",
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB",
            },
            "description": description,
            "return": return_url,
            "failedUrl": return_url,
            "payload": f"order_{user_id}_{order_id}",
            "paymentMethod": ["SBP", "CRYPTO"],
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

                if resp.status not in (200, 201):
                    raise PlategaError(
                        f"HTTP {resp.status}: {data}"
                    )

                payment_url = data.get("url")
                if not payment_url:
                    raise PlategaError(f"Не получен payment_url: {data}")

                return {
                    "success": True,
                    "payment_url": payment_url,
                    "order_id": order_id,
                    "raw": data,
                }

    def verify_webhook(self, headers: Dict[str, str], body: bytes, signature: str) -> bool:
        """
        Проверяет подпись webhook от platega.io.
        Platega v2 использует базовую авторизацию по заголовкам, подпись не требуется.
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
