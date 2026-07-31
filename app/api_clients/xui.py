"""
Асинхронный клиент для API панели 3X-UI.

API 3X-UI v3.5.0 (фактические пути панели):
  GET  /                                    — получить cookie 3x-ui и CSRF-токен.
  POST /login                               — авторизация с CSRF-токеном, выдает cookie 3x-ui.
  GET  /panel/api/inbounds/get/{id}         — получить inbound с клиентами.
  POST /panel/api/inbounds/addClient        — добавить клиента.
  POST /panel/api/inbounds/update/{id}      — обновить inbound целиком.
  POST /panel/api/inbounds/{id}/delClient/{uuid} — удалить клиента.

Клиенты хранятся в поле settings JSON inbound'а в виде массива clients.
"""

import json
import logging
import re
import uuid as uuid_mod
from typing import Optional, Dict, Any

import aiohttp
from app.config import CONFIG


logger = logging.getLogger(__name__)


class XUIClientError(Exception):
    pass


class XUIClient:
    def __init__(self):
        self.base_url = CONFIG.XUI_BASE_URL.rstrip("/")
        self.username = CONFIG.XUI_USERNAME
        self.password = CONFIG.XUI_PASSWORD
        self.inbound_id = CONFIG.XUI_INBOUND_ID
        self._session_cookie: Optional[str] = None
        self._csrf_token: Optional[str] = None

    # ---------- Auth ----------

    async def _login(self, session: aiohttp.ClientSession) -> bool:
        """Авторизация в 3X-UI v3.5.0: требуется CSRF-токен и cookie 3x-ui."""
        # Шаг 1: GET / для получения cookie 3x-ui и CSRF-токена
        async with session.get(self.base_url, ssl=False) as get_resp:
            html = await get_resp.text()
            logger.info(f"3X-UI pre-login GET status={get_resp.status}")

        csrf_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
        if not csrf_match:
            logger.warning("3X-UI CSRF token not found in login page")
            return False
        self._csrf_token = csrf_match.group(1)
        logger.info(f"3X-UI CSRF token extracted: {self._csrf_token[:20]}...")

        # Шаг 2: POST /login с CSRF-токеном
        url = f"{self.base_url}/login"
        logger.info(f"3X-UI login URL: {url}")
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": self._csrf_token,
        }
        json_data = {"username": self.username, "password": self.password}
        async with session.post(url, json=json_data, headers=headers, ssl=False) as resp:
            text = await resp.text()
            logger.info(f"3X-UI login response: status={resp.status}, body={text[:200]}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}

            if resp.status == 200 and payload.get("success"):
                # Cookie сессии (3x-ui)
                cookies = resp.headers.getall("Set-Cookie", [])
                logger.info(f"3X-UI Set-Cookie headers: {cookies}")
                for c in cookies:
                    if "3x-ui=" in c:
                        self._session_cookie = c.split(";")[0]
                        logger.info(f"3X-UI session cookie set: {self._session_cookie[:30]}...")
                        return True
                # Fallback: cookie из jar
                for c in session.cookie_jar:
                    if c.key == "3x-ui":
                        self._session_cookie = f"3x-ui={c.value}"
                        logger.info(f"3X-UI session cookie from jar: {self._session_cookie[:30]}...")
                        return True
            logger.warning(f"3X-UI login failed: status={resp.status}, payload={payload}")
            return False

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Выполняет авторизованный запрос к 3X-UI с автоповтором логина."""
        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            # Попытка 1: с текущей cookie
            if self._session_cookie:
                headers = {"Cookie": self._session_cookie}
            else:
                headers = {}

            result = await self._do_request(
                session, method, path, headers, json_data, data
            )
            if not result.get("success"):
                # Попытка 2: перелогиниться (3X-UI v3.5.0 требует CSRF + cookie 3x-ui)
                logger.info("3X-UI request failed, trying login...")
                if await self._login(session):
                    headers = {"Cookie": self._session_cookie}
                    result = await self._do_request(
                        session, method, path, headers, json_data, data
                    )
            return result

    async def _do_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        # Для POST/PUT/DELETE добавляем CSRF-токен
        if method.upper() in ("POST", "PUT", "DELETE", "PATCH") and self._csrf_token:
            headers = {**headers, "X-CSRF-Token": self._csrf_token}
        logger.info(f"3X-UI request: {method} {url}")
        async with session.request(
            method, url, headers=headers, json=json_data, data=data, ssl=False
        ) as resp:
            text = await resp.text()
            logger.info(f"3X-UI response: status={resp.status}, body={text[:300]}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"success": False, "msg": text, "status": resp.status}

    # ---------- Public API ----------

    async def get_inbound(self) -> Dict[str, Any]:
        """Получить inbound по ID."""
        return await self.get_inbound_by_id(self.inbound_id)

    async def get_inbound_by_id(self, inbound_id: int) -> Dict[str, Any]:
        """Получить inbound по произвольному ID."""
        result = await self._request("GET", f"/panel/api/inbounds/get/{inbound_id}")
        if not result.get("success"):
            raise XUIClientError(f"Ошибка получения inbound {inbound_id}: {result}")
        return result.get("obj", {})

    async def add_client(
        self,
        telegram_id: int,
        days: int,
        limit_ip: int,
        total_gb: int = 0,
        existing_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Добавляет нового клиента во все inbound'ы из CONFIG.XUI_INBOUND_IDS.
        Возвращает {uuid, email, links: [{inbound_id, remark, link}]}.
        """
        from app.config import CONFIG

        inbound_ids = getattr(CONFIG, "XUI_INBOUND_IDS", [self.inbound_id])
        new_uuid = existing_uuid or str(uuid_mod.uuid4())
        email = f"user_{telegram_id}@nyxvpn"

        # Срок в миллисекундах (UTC)
        import datetime

        expiry_ms = int(
            (datetime.datetime.utcnow() + datetime.timedelta(days=days)).timestamp()
            * 1000
        )

        client_template = {
            "id": new_uuid,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": int(telegram_id),
            "subId": "",
            "comment": "Nyx VPN",
        }

        links = []
        for inbound_id in inbound_ids:
            inbound = await self.get_inbound_by_id(inbound_id)
            settings_raw = inbound.get("settings", "{}")
            settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
            clients = settings.get("clients", [])

            # Проверка на дубликат email/uuid
            clients = [c for c in clients if c.get("email") != email and c.get("id") != new_uuid]
            clients.append(client_template)
            settings["clients"] = clients

            update_payload = self._prepare_inbound_payload(inbound, settings)
            result = await self._request(
                "POST",
                f"/panel/api/inbounds/update/{inbound_id}",
                json_data=update_payload,
            )
            if not result.get("success"):
                raise XUIClientError(f"Ошибка добавления клиента в inbound {inbound_id}: {result}")

            link = self._build_vless_link(inbound, new_uuid)
            links.append({
                "inbound_id": inbound_id,
                "remark": inbound.get("remark", f"inbound-{inbound_id}"),
                "link": link,
            })

        return {"uuid": new_uuid, "email": email, "links": links}

    async def update_client_expiry(
        self,
        client_uuid: str,
        days_to_add: int,
        limit_ip: int,
    ):
        """Продлевает клиента на N дней во всех inbound'ах."""
        import datetime
        from app.config import CONFIG

        inbound_ids = getattr(CONFIG, "XUI_INBOUND_IDS", [self.inbound_id])
        now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
        add_ms = int(datetime.timedelta(days=days_to_add).total_seconds() * 1000)

        for inbound_id in inbound_ids:
            inbound = await self.get_inbound_by_id(inbound_id)
            settings_raw = inbound.get("settings", "{}")
            settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
            clients = settings.get("clients", [])

            target = None
            for c in clients:
                if c.get("id") == client_uuid:
                    target = c
                    break

            if target is None:
                continue

            current_expiry = target.get("expiryTime", 0)
            if current_expiry < now_ms:
                new_expiry = now_ms + add_ms
            else:
                new_expiry = current_expiry + add_ms

            target["expiryTime"] = new_expiry
            target["limitIp"] = limit_ip
            target["enable"] = True

            update_payload = self._prepare_inbound_payload(inbound, settings)
            result = await self._request(
                "POST",
                f"/panel/api/inbounds/update/{inbound_id}",
                json_data=update_payload,
            )
            if not result.get("success"):
                raise XUIClientError(f"Ошибка продления клиента в inbound {inbound_id}: {result}")

    async def disable_or_delete_client(self, client_uuid: str):
        """Отключает клиента во всех inbound'ах."""
        from app.config import CONFIG

        inbound_ids = getattr(CONFIG, "XUI_INBOUND_IDS", [self.inbound_id])
        for inbound_id in inbound_ids:
            inbound = await self.get_inbound_by_id(inbound_id)
            settings_raw = inbound.get("settings", "{}")
            settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
            clients = settings.get("clients", [])

            for c in clients:
                if c.get("id") == client_uuid:
                    c["enable"] = False
                    break

            update_payload = self._prepare_inbound_payload(inbound, settings)
            await self._request(
                "POST",
                f"/panel/api/inbounds/update/{inbound_id}",
                json_data=update_payload,
            )

    def _prepare_inbound_payload(
        self, inbound: Dict[str, Any], settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Готовит полный inbound payload для POST /panel/api/inbounds/update/{id}.

        3X-UI v3.5.0 принимает nested JSON-объекты (preferred) или JSON-строки (legacy).
        """
        payload = inbound.copy()
        payload["settings"] = settings
        # Убедимся, что вложенные объекты остаются dict, а не строками
        for key in ["streamSettings", "sniffing"]:
            val = payload.get(key)
            if isinstance(val, str):
                payload[key] = json.loads(val) if val else {}
            elif val is None:
                payload.pop(key, None)
        # Убираем read-only/вычисляемые поля, которые могут мешать валидации
        for key in ["clientStats", "tag", "shareAddrStrategy", "shareAddr"]:
            payload.pop(key, None)
        return payload

    def _build_vless_link(self, inbound: Dict[str, Any], client_uuid: str) -> str:
        """Собирает vless:// ссылку из inbound."""
        port = inbound.get("port", "443")
        listen = inbound.get("listen", "") or inbound.get("ip", "0.0.0.0")
        if listen == "0.0.0.0":
            listen = self.base_url.replace("https://", "").replace("http://", "").split(":")[0]

        stream_settings_raw = inbound.get("streamSettings", "{}")
        if isinstance(stream_settings_raw, str):
            stream_settings = json.loads(stream_settings_raw) if stream_settings_raw else {}
        else:
            stream_settings = stream_settings_raw or {}
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "none")
        sni = ""
        fingerprint = "chrome"
        public_key = ""
        short_id = ""
        path = ""
        host = ""

        if security == "tls" or security == "xtls":
            tls = stream_settings.get("tlsSettings", {})
            sni = tls.get("serverName", listen)
            fp = tls.get("fingerprint", "")
            if fp:
                fingerprint = fp

        if security == "reality":
            reality = stream_settings.get("realitySettings", {})
            sni = reality.get("serverNames", [listen])[0]
            public_key = reality.get("publicKey", "")
            short_id = reality.get("shortIds", [""])[0]
            fingerprint = reality.get("fingerprint", "chrome")

        if network in ("ws", "grpc", "httpupgrade", "xhttp"):
            ws_settings = stream_settings.get(f"{network}Settings", {})
            path = ws_settings.get("path", "/")
            host = ws_settings.get("host", "")

        # Формируем query params
        params = {
            "type": network,
            "security": security,
        }
        if security != "none":
            params["sni"] = sni
            params["fp"] = fingerprint
        if public_key:
            params["pbk"] = public_key
        if short_id:
            params["sid"] = short_id
        if path:
            params["path"] = path
        if host:
            params["host"] = host

        from urllib.parse import urlencode, quote

        query = urlencode(params)
        remark = quote("NyxVPN")
        return f"vless://{client_uuid}@{listen}:{port}?{query}#{remark}"
