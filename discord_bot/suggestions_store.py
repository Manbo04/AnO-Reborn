"""Persist suggestion-box config and individual suggestions.

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same tables with the same shapes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database import QueryHelper, get_db_cursor


@dataclass
class SuggestionsConfig:
    guild_id: str
    enabled: bool = True
    channel_id: Optional[str] = None


@dataclass
class Suggestion:
    id: int
    guild_id: str
    author_user_id: str
    channel_id: str
    message_id: Optional[str]
    content: str
    status: str  # pending | approved | denied | implemented
    created_at: datetime
    decided_at: Optional[datetime]
    decided_by_user_id: Optional[str]


def get_suggestions_config(guild_id: str) -> SuggestionsConfig:
    row = QueryHelper.fetch_one(
        "SELECT guild_id, enabled, channel_id FROM discord_suggestions_config WHERE guild_id = %s",
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return SuggestionsConfig(guild_id=guild_id)
    return SuggestionsConfig(
        guild_id=str(row["guild_id"]),
        enabled=bool(row["enabled"]),
        channel_id=row.get("channel_id"),
    )


def set_suggestions_config(config: SuggestionsConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_suggestions_config (guild_id, enabled, channel_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                channel_id = EXCLUDED.channel_id,
                updated_at = NOW()
            """,
            (config.guild_id, config.enabled, config.channel_id),
        )


def _row_to_suggestion(row) -> Suggestion:
    return Suggestion(
        id=int(row["id"]),
        guild_id=str(row["guild_id"]),
        author_user_id=str(row["author_user_id"]),
        channel_id=str(row["channel_id"]),
        message_id=row.get("message_id"),
        content=str(row["content"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        decided_at=row.get("decided_at"),
        decided_by_user_id=row.get("decided_by_user_id"),
    )


def create_suggestion(guild_id: str, author_user_id: str, channel_id: str, content: str) -> int:
    row = QueryHelper.execute_returning(
        """
        INSERT INTO discord_suggestions (guild_id, author_user_id, channel_id, content)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (guild_id, author_user_id, channel_id, content),
    )
    return int(row[0])


def set_suggestion_message(suggestion_id: int, message_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            "UPDATE discord_suggestions SET message_id = %s WHERE id = %s",
            (message_id, suggestion_id),
        )


def get_suggestion_by_message(guild_id: str, message_id: str) -> Optional[Suggestion]:
    row = QueryHelper.fetch_one(
        """
        SELECT id, guild_id, author_user_id, channel_id, message_id, content, status,
               created_at, decided_at, decided_by_user_id
        FROM discord_suggestions WHERE guild_id = %s AND message_id = %s
        """,
        (guild_id, message_id),
        dict_cursor=True,
    )
    return _row_to_suggestion(row) if row else None


def decide_suggestion(suggestion_id: int, status: str, decided_by_user_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            UPDATE discord_suggestions
            SET status = %s, decided_at = NOW(), decided_by_user_id = %s
            WHERE id = %s
            """,
            (status, decided_by_user_id, suggestion_id),
        )


def list_suggestions(guild_id: str, status: Optional[str] = None, limit: int = 20) -> List[Suggestion]:
    if status:
        rows = QueryHelper.fetch_all(
            """
            SELECT id, guild_id, author_user_id, channel_id, message_id, content, status,
                   created_at, decided_at, decided_by_user_id
            FROM discord_suggestions WHERE guild_id = %s AND status = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (guild_id, status, limit),
            dict_cursor=True,
        )
    else:
        rows = QueryHelper.fetch_all(
            """
            SELECT id, guild_id, author_user_id, channel_id, message_id, content, status,
                   created_at, decided_at, decided_by_user_id
            FROM discord_suggestions WHERE guild_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (guild_id, limit),
            dict_cursor=True,
        )
    return [_row_to_suggestion(r) for r in rows or []]
