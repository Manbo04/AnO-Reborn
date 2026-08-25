"""Persist starboard config and posted-message dedupe tracking.

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same tables with the same shapes.
"""

from dataclasses import dataclass
from typing import Optional

from database import QueryHelper, get_db_cursor


@dataclass
class StarboardConfig:
    guild_id: str
    enabled: bool = False
    channel_id: Optional[str] = None
    emoji: str = "⭐"
    threshold: int = 3


@dataclass
class StarboardPost:
    guild_id: str
    source_message_id: str
    source_channel_id: str
    starboard_message_id: str
    star_count: int


def get_starboard_config(guild_id: str) -> StarboardConfig:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, enabled, channel_id, emoji, threshold
        FROM discord_starboard_config WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return StarboardConfig(guild_id=guild_id)
    return StarboardConfig(
        guild_id=str(row["guild_id"]),
        enabled=bool(row["enabled"]),
        channel_id=row.get("channel_id"),
        emoji=str(row["emoji"]),
        threshold=int(row["threshold"]),
    )


def set_starboard_config(config: StarboardConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_starboard_config (guild_id, enabled, channel_id, emoji, threshold, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                channel_id = EXCLUDED.channel_id,
                emoji = EXCLUDED.emoji,
                threshold = EXCLUDED.threshold,
                updated_at = NOW()
            """,
            (config.guild_id, config.enabled, config.channel_id, config.emoji, config.threshold),
        )


def get_starboard_post(guild_id: str, source_message_id: str) -> Optional[StarboardPost]:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, source_message_id, source_channel_id, starboard_message_id, star_count
        FROM discord_starboard_posts WHERE guild_id = %s AND source_message_id = %s
        """,
        (guild_id, source_message_id),
        dict_cursor=True,
    )
    if not row:
        return None
    return StarboardPost(
        guild_id=str(row["guild_id"]),
        source_message_id=str(row["source_message_id"]),
        source_channel_id=str(row["source_channel_id"]),
        starboard_message_id=str(row["starboard_message_id"]),
        star_count=int(row["star_count"]),
    )


def upsert_starboard_post(
    guild_id: str, source_message_id: str, source_channel_id: str, starboard_message_id: str, star_count: int
) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_starboard_posts
                (guild_id, source_message_id, source_channel_id, starboard_message_id, star_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (guild_id, source_message_id) DO UPDATE SET
                starboard_message_id = EXCLUDED.starboard_message_id,
                star_count = EXCLUDED.star_count
            """,
            (guild_id, source_message_id, source_channel_id, starboard_message_id, star_count),
        )


def update_star_count(guild_id: str, source_message_id: str, star_count: int) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            UPDATE discord_starboard_posts SET star_count = %s
            WHERE guild_id = %s AND source_message_id = %s
            """,
            (star_count, guild_id, source_message_id),
        )
