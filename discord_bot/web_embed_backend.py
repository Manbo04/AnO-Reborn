"""Discord bot backend that renders nation cards on the web service (auto-deploy path)."""


from typing import Any, Dict, Optional

from discord_bot.api import BotApiClient, BotApiError
from discord_bot.backend import BotBackend, BotBackendError


class WebEmbedBackend(BotBackend):
    """Fetch pre-built embed JSON from /api/bot/*_embed on the Flask app."""

    def __init__(self) -> None:
        self._client = BotApiClient()

    def _wrap(self, fn, *args, **kwargs) -> Dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except BotApiError as exc:
            raise BotBackendError(str(exc), exc.status_code) from exc

    def register(self, discord_user_id: str, code: str) -> Dict[str, Any]:
        return self._wrap(self._client.register, discord_user_id, code)

    def me(self, discord_user_id: str) -> Dict[str, Any]:
        return self._wrap(
            self._client._request,
            "GET",
            "/api/bot/me_embed",
            discord_user_id=discord_user_id,
        )

    def nation(self, identifier: str) -> Dict[str, Any]:
        return self._wrap(
            self._client._request,
            "GET",
            "/api/bot/nation_embed",
            params={"identifier": identifier.strip(), "title": "Nation lookup"},
        )

    def wars(
        self,
        discord_user_id: Optional[str] = None,
        nation: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if nation:
            params["nation"] = nation.strip()
        return self._wrap(
            self._client._request,
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
        if nation:
            return self._wrap(
                self._client._request,
                "GET",
                "/api/bot/nation_embed",
                params={"identifier": nation.strip(), "title": "Resources"},
            )
        if discord_user_id:
            return self._wrap(
                self._client._request,
                "GET",
                "/api/bot/me_embed",
                discord_user_id=discord_user_id,
                params={"title": "Resources"},
            )
        raise BotBackendError("Register first or provide a nation name/id", 400)
