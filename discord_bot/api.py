"""HTTP client for the Flask bot API."""


from typing import Any, Dict, Optional

import requests

from discord_bot.config import BOT_API_BASE_URL, BOT_API_SECRET


class BotApiError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class BotApiClient:
    def __init__(self) -> None:
        self.base_url = BOT_API_BASE_URL
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Bot-Secret": BOT_API_SECRET,
                "Content-Type": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        discord_user_id: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        headers = {}
        if discord_user_id:
            headers["X-Discord-User-Id"] = str(discord_user_id)
        url = f"{self.base_url}{path}"
        resp = self.session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=30,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"error": resp.text[:500] or resp.reason}
        if not resp.ok:
            msg = data.get("error") if isinstance(data, dict) else str(data)
            raise BotApiError(msg or f"HTTP {resp.status_code}", resp.status_code)
        return data if isinstance(data, dict) else {"data": data}

    def register(self, discord_user_id: str, code: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/bot/register",
            json_body={"discord_user_id": str(discord_user_id), "code": code},
        )

    def me(self, discord_user_id: str) -> Dict[str, Any]:
        return self._request("GET", "/api/bot/me", discord_user_id=discord_user_id)

    def nation(self, identifier: str) -> Dict[str, Any]:
        return self._request(
            "GET", "/api/bot/nation", params={"identifier": identifier}
        )

    def wars(
        self,
        discord_user_id: Optional[str] = None,
        nation: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {}
        if nation:
            params["nation"] = nation
        return self._request(
            "GET",
            "/api/bot/wars",
            discord_user_id=discord_user_id,
            params=params or None,
        )

    def resources(
        self,
        discord_user_id: Optional[str] = None,
        nation: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {}
        if nation:
            params["nation"] = nation
        return self._request(
            "GET",
            "/api/bot/resources",
            discord_user_id=discord_user_id,
            params=params or None,
        )
