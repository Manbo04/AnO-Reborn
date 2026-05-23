"""Data access for slash commands: direct Postgres (preferred on Railway bot) or HTTP API."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Protocol


class BotBackend(Protocol):
    def register(self, discord_user_id: str, code: str) -> Dict[str, Any]: ...

    def me(self, discord_user_id: str) -> Dict[str, Any]: ...

    def nation(self, identifier: str) -> Dict[str, Any]: ...

    def wars(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]: ...

    def resources(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]: ...


class BotBackendError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class DirectDatabaseBackend:
    """Use game DB directly — only needs DATABASE_URL + DISCORD_BOT_TOKEN on Railway."""

    def register(self, discord_user_id: str, code: str) -> Dict[str, Any]:
        from bot_api import register_discord_with_code

        from database import QueryHelper

        ok, message, user_id = register_discord_with_code(discord_user_id, code)
        if not ok:
            raise BotBackendError(message, 400)
        username = None
        if user_id:
            row = QueryHelper.fetch_one(
                "SELECT username FROM users WHERE id = %s",
                (user_id,),
                dict_cursor=True,
            )
            if row:
                username = row.get("username")
        return {
            "ok": True,
            "message": message,
            "user_id": user_id,
            "username": username,
        }

    def me(self, discord_user_id: str) -> Dict[str, Any]:
        from bot_api import nation_snapshot_for_bot
        from database import resolve_user_id_by_discord

        user_id = resolve_user_id_by_discord(discord_user_id)
        if user_id is None:
            raise BotBackendError(
                "Not registered. Generate a link code on your account page, then "
                "/register code:XXXXXXXX",
                404,
            )
        snap = nation_snapshot_for_bot(user_id)
        if not snap.get("id"):
            raise BotBackendError(
                "Could not load nation statistics. Try again in a moment.",
                500,
            )
        return snap

    def nation(self, identifier: str) -> Dict[str, Any]:
        from bot_api import _resolve_nation_identifier, nation_snapshot_for_bot

        user_id = _resolve_nation_identifier(identifier)
        if user_id is None:
            raise BotBackendError("Nation not found", 404)
        snap = nation_snapshot_for_bot(user_id, full_detail=True)
        if not snap.get("id"):
            raise BotBackendError("Could not load nation statistics.", 500)
        return snap

    def wars(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]:
        from bot_api import _list_active_wars, _resolve_nation_identifier
        from database import resolve_user_id_by_discord

        if nation:
            user_id = _resolve_nation_identifier(nation)
        else:
            if not discord_user_id:
                raise BotBackendError("Register first or provide a nation name/id", 400)
            user_id = resolve_user_id_by_discord(discord_user_id)
        if user_id is None:
            raise BotBackendError("Nation not found or not registered", 404)
        return {"nation_id": user_id, "wars": _list_active_wars(user_id)}

    def resources(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]:
        from bot_api import _resolve_nation_identifier, nation_snapshot_for_bot
        from database import resolve_user_id_by_discord

        if nation:
            user_id = _resolve_nation_identifier(nation)
        else:
            if not discord_user_id:
                raise BotBackendError("Register first or provide a nation name/id", 400)
            user_id = resolve_user_id_by_discord(discord_user_id)
        if user_id is None:
            raise BotBackendError("Nation not found or not registered", 404)
        snap = nation_snapshot_for_bot(user_id, full_detail=True)
        if not snap.get("id"):
            raise BotBackendError("Could not load nation statistics.", 500)
        return snap


class HttpApiBackend:
    """Call web service /api/bot/* (needs BOT_API_BASE_URL + auth secret)."""

    def __init__(self) -> None:
        from discord_bot.api import BotApiClient

        self._client = BotApiClient()

    def _wrap(self, fn, *args, **kwargs) -> Dict[str, Any]:
        from discord_bot.api import BotApiError

        try:
            return fn(*args, **kwargs)
        except BotApiError as exc:
            raise BotBackendError(str(exc), exc.status_code) from exc

    def register(self, discord_user_id: str, code: str) -> Dict[str, Any]:
        return self._wrap(self._client.register, discord_user_id, code)

    def me(self, discord_user_id: str) -> Dict[str, Any]:
        return self._wrap(self._client.me, discord_user_id)

    def nation(self, identifier: str) -> Dict[str, Any]:
        return self._wrap(self._client.nation, identifier)

    def wars(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._wrap(self._client.wars, discord_user_id, nation)

    def resources(
        self, discord_user_id: Optional[str] = None, nation: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._wrap(self._client.resources, discord_user_id, nation)


def _has_database_url() -> bool:
    return bool(
        (os.getenv("DATABASE_PUBLIC_URL") or "").strip()
        or (os.getenv("DATABASE_URL") or "").strip()
    )


def _use_web_embed_backend() -> bool:
    flag = (os.getenv("DISCORD_BOT_USE_WEB_EMBEDS") or "").strip().lower()
    return flag in ("1", "true", "yes")


def get_backend() -> BotBackend:
    if _use_web_embed_backend():
        from discord_bot.web_embed_backend import WebEmbedBackend

        return WebEmbedBackend()
    if _has_database_url():
        return DirectDatabaseBackend()
    return HttpApiBackend()


def backend_mode_label() -> str:
    if _use_web_embed_backend():
        return "web-embeds"
    return "database" if _has_database_url() else "http-api"
