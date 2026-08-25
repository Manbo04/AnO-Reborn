"""Persist per-guild custom commands / tags (trigger -> text or embed response).

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same table with the same shape.
"""

from dataclasses import dataclass
from typing import List, Optional

from database import QueryHelper, get_db_cursor


@dataclass
class CustomCommand:
    id: int
    guild_id: str
    trigger: str
    response_type: str  # text | embed
    response_text: Optional[str]
    embed_title: Optional[str]
    embed_color: Optional[str]


def _row_to_command(row) -> CustomCommand:
    return CustomCommand(
        id=int(row["id"]),
        guild_id=str(row["guild_id"]),
        trigger=str(row["trigger_word"]),
        response_type=str(row["response_type"]),
        response_text=row.get("response_text"),
        embed_title=row.get("embed_title"),
        embed_color=row.get("embed_color"),
    )


def list_custom_commands(guild_id: str) -> List[CustomCommand]:
    rows = QueryHelper.fetch_all(
        """
        SELECT id, guild_id, trigger_word, response_type, response_text,
               embed_title, embed_color
        FROM discord_custom_commands WHERE guild_id = %s ORDER BY trigger_word ASC
        """,
        (guild_id,),
        dict_cursor=True,
    )
    return [_row_to_command(r) for r in rows or []]


def get_custom_command(guild_id: str, trigger: str) -> Optional[CustomCommand]:
    row = QueryHelper.fetch_one(
        """
        SELECT id, guild_id, trigger_word, response_type, response_text,
               embed_title, embed_color
        FROM discord_custom_commands WHERE guild_id = %s AND trigger_word = %s
        """,
        (guild_id, trigger.lower()),
        dict_cursor=True,
    )
    return _row_to_command(row) if row else None


def get_custom_command_by_id(guild_id: str, command_id: int) -> Optional[CustomCommand]:
    row = QueryHelper.fetch_one(
        """
        SELECT id, guild_id, trigger_word, response_type, response_text,
               embed_title, embed_color
        FROM discord_custom_commands WHERE guild_id = %s AND id = %s
        """,
        (guild_id, command_id),
        dict_cursor=True,
    )
    return _row_to_command(row) if row else None


def save_custom_command(
    guild_id: str,
    trigger: str,
    response_type: str,
    response_text: Optional[str],
    embed_title: Optional[str],
    embed_color: Optional[str],
    command_id: Optional[int] = None,
) -> None:
    trigger = trigger.strip().lower().lstrip("!")
    with get_db_cursor() as db:
        if command_id:
            db.execute(
                """
                UPDATE discord_custom_commands
                SET trigger_word = %s, response_type = %s, response_text = %s,
                    embed_title = %s, embed_color = %s, updated_at = NOW()
                WHERE guild_id = %s AND id = %s
                """,
                (trigger, response_type, response_text, embed_title, embed_color, guild_id, command_id),
            )
        else:
            db.execute(
                """
                INSERT INTO discord_custom_commands
                    (guild_id, trigger_word, response_type, response_text, embed_title, embed_color)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (guild_id, trigger_word) DO UPDATE SET
                    response_type = EXCLUDED.response_type,
                    response_text = EXCLUDED.response_text,
                    embed_title = EXCLUDED.embed_title,
                    embed_color = EXCLUDED.embed_color,
                    updated_at = NOW()
                """,
                (guild_id, trigger, response_type, response_text, embed_title, embed_color),
            )


def delete_custom_command(guild_id: str, command_id: int) -> None:
    with get_db_cursor() as db:
        db.execute(
            "DELETE FROM discord_custom_commands WHERE guild_id = %s AND id = %s",
            (guild_id, command_id),
        )
