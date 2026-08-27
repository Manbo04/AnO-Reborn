"""Persist Discord engagement config/state (leveling, welcome, reaction roles, giveaways).

Shared by the bot process and the Flask dashboard so both read/write the same
tables with the same shapes. Mirrors the style of guild_store.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from database import QueryHelper, get_db_cursor


# ---------------------------------------------------------------------------
# Leveling
# ---------------------------------------------------------------------------


@dataclass
class LevelConfig:
    guild_id: str
    xp_per_message: int = 15
    xp_cooldown_seconds: int = 60
    xp_per_voice_minute: int = 5
    level_up_channel_id: Optional[str] = None
    level_up_enabled: bool = True


def get_level_config(guild_id: str) -> LevelConfig:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, xp_per_message, xp_cooldown_seconds, xp_per_voice_minute,
               level_up_channel_id, level_up_enabled
        FROM discord_level_config WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return LevelConfig(guild_id=guild_id)
    return LevelConfig(
        guild_id=str(row["guild_id"]),
        xp_per_message=int(row["xp_per_message"]),
        xp_cooldown_seconds=int(row["xp_cooldown_seconds"]),
        xp_per_voice_minute=int(row["xp_per_voice_minute"]),
        level_up_channel_id=row.get("level_up_channel_id"),
        level_up_enabled=bool(row["level_up_enabled"]),
    )


def set_level_config(config: LevelConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_level_config
                (guild_id, xp_per_message, xp_cooldown_seconds, xp_per_voice_minute,
                 level_up_channel_id, level_up_enabled, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                xp_per_message = EXCLUDED.xp_per_message,
                xp_cooldown_seconds = EXCLUDED.xp_cooldown_seconds,
                xp_per_voice_minute = EXCLUDED.xp_per_voice_minute,
                level_up_channel_id = EXCLUDED.level_up_channel_id,
                level_up_enabled = EXCLUDED.level_up_enabled,
                updated_at = NOW()
            """,
            (
                config.guild_id,
                config.xp_per_message,
                config.xp_cooldown_seconds,
                config.xp_per_voice_minute,
                config.level_up_channel_id,
                config.level_up_enabled,
            ),
        )


def get_user_xp(guild_id: str, user_id: str) -> tuple:
    """Returns (xp, level, last_xp_at)."""
    row = QueryHelper.fetch_one(
        "SELECT xp, level, last_xp_at FROM discord_user_xp WHERE guild_id = %s AND user_id = %s",
        (guild_id, user_id),
    )
    if not row:
        return 0, 0, None
    return int(row[0]), int(row[1]), row[2]


def get_last_active_map(guild_id: str) -> Dict[str, datetime]:
    """user_id -> last_xp_at for every member with tracked message activity in this guild."""
    rows = QueryHelper.fetch_all(
        "SELECT user_id, last_xp_at FROM discord_user_xp WHERE guild_id = %s AND last_xp_at IS NOT NULL",
        (guild_id,),
    )
    return {str(row[0]): row[1] for row in rows}


def set_user_xp(guild_id: str, user_id: str, xp: int, level: int, last_xp_at: datetime) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_user_xp (guild_id, user_id, xp, level, last_xp_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                xp = EXCLUDED.xp,
                level = EXCLUDED.level,
                last_xp_at = EXCLUDED.last_xp_at
            """,
            (guild_id, user_id, xp, level, last_xp_at),
        )


def get_leaderboard(guild_id: str, limit: int = 10) -> List[tuple]:
    """Returns [(user_id, xp, level), ...] ordered by xp desc."""
    rows = QueryHelper.fetch_all(
        """
        SELECT user_id, xp, level FROM discord_user_xp
        WHERE guild_id = %s ORDER BY xp DESC LIMIT %s
        """,
        (guild_id, limit),
    )
    return [(str(r[0]), int(r[1]), int(r[2])) for r in rows or []]


def get_level_role(guild_id: str, level: int) -> Optional[str]:
    row = QueryHelper.fetch_one(
        "SELECT role_id FROM discord_level_roles WHERE guild_id = %s AND level = %s",
        (guild_id, level),
    )
    return str(row[0]) if row else None


def list_level_roles(guild_id: str) -> List[tuple]:
    """Returns [(level, role_id), ...] ordered by level asc."""
    rows = QueryHelper.fetch_all(
        "SELECT level, role_id FROM discord_level_roles WHERE guild_id = %s ORDER BY level ASC",
        (guild_id,),
    )
    return [(int(r[0]), str(r[1])) for r in rows or []]


def set_level_role(guild_id: str, level: int, role_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_level_roles (guild_id, level, role_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (guild_id, level) DO UPDATE SET role_id = EXCLUDED.role_id
            """,
            (guild_id, level, role_id),
        )


# ---------------------------------------------------------------------------
# Welcome / auto-roles
# ---------------------------------------------------------------------------


@dataclass
class WelcomeConfig:
    guild_id: str
    enabled: bool = False
    channel_id: Optional[str] = None
    message_template: Optional[str] = None
    dm_enabled: bool = False
    dm_template: Optional[str] = None
    auto_role_ids: List[str] = field(default_factory=list)


def get_welcome_config(guild_id: str) -> WelcomeConfig:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, enabled, channel_id, message_template,
               dm_enabled, dm_template, auto_role_ids
        FROM discord_welcome_config WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return WelcomeConfig(guild_id=guild_id)
    return WelcomeConfig(
        guild_id=str(row["guild_id"]),
        enabled=bool(row["enabled"]),
        channel_id=row.get("channel_id"),
        message_template=row.get("message_template"),
        dm_enabled=bool(row["dm_enabled"]),
        dm_template=row.get("dm_template"),
        auto_role_ids=list(row.get("auto_role_ids") or []),
    )


def set_welcome_config(config: WelcomeConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_welcome_config
                (guild_id, enabled, channel_id, message_template,
                 dm_enabled, dm_template, auto_role_ids, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                channel_id = EXCLUDED.channel_id,
                message_template = EXCLUDED.message_template,
                dm_enabled = EXCLUDED.dm_enabled,
                dm_template = EXCLUDED.dm_template,
                auto_role_ids = EXCLUDED.auto_role_ids,
                updated_at = NOW()
            """,
            (
                config.guild_id,
                config.enabled,
                config.channel_id,
                config.message_template,
                config.dm_enabled,
                config.dm_template,
                config.auto_role_ids,
            ),
        )


# ---------------------------------------------------------------------------
# Reaction roles
# ---------------------------------------------------------------------------


def add_reaction_role(guild_id: str, message_id: str, emoji: str, role_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_reaction_roles (guild_id, message_id, emoji, role_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (guild_id, message_id, emoji) DO UPDATE SET role_id = EXCLUDED.role_id
            """,
            (guild_id, message_id, emoji, role_id),
        )


def remove_reaction_role(guild_id: str, message_id: str, emoji: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            "DELETE FROM discord_reaction_roles WHERE guild_id = %s AND message_id = %s AND emoji = %s",
            (guild_id, message_id, emoji),
        )


def get_reaction_role(guild_id: str, message_id: str, emoji: str) -> Optional[str]:
    row = QueryHelper.fetch_one(
        """
        SELECT role_id FROM discord_reaction_roles
        WHERE guild_id = %s AND message_id = %s AND emoji = %s
        """,
        (guild_id, message_id, emoji),
    )
    return str(row[0]) if row else None


def list_reaction_roles(guild_id: str, message_id: Optional[str] = None) -> List[tuple]:
    """Returns [(message_id, emoji, role_id), ...]."""
    if message_id:
        rows = QueryHelper.fetch_all(
            "SELECT message_id, emoji, role_id FROM discord_reaction_roles WHERE guild_id = %s AND message_id = %s",
            (guild_id, message_id),
        )
    else:
        rows = QueryHelper.fetch_all(
            "SELECT message_id, emoji, role_id FROM discord_reaction_roles WHERE guild_id = %s",
            (guild_id,),
        )
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows or []]


# ---------------------------------------------------------------------------
# Giveaways
# ---------------------------------------------------------------------------


@dataclass
class Giveaway:
    id: int
    guild_id: str
    channel_id: str
    message_id: Optional[str]
    prize: str
    winners_count: int
    ends_at: datetime
    ended: bool


def create_giveaway(
    guild_id: str, channel_id: str, prize: str, winners_count: int, ends_at: datetime
) -> int:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_giveaways (guild_id, channel_id, prize, winners_count, ends_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (guild_id, channel_id, prize, winners_count, ends_at),
        )
        return int(db.fetchone()[0])


def set_giveaway_message(giveaway_id: int, message_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            "UPDATE discord_giveaways SET message_id = %s WHERE id = %s",
            (message_id, giveaway_id),
        )


def mark_giveaway_ended(giveaway_id: int) -> None:
    with get_db_cursor() as db:
        db.execute("UPDATE discord_giveaways SET ended = TRUE WHERE id = %s", (giveaway_id,))


def get_due_giveaways() -> List[Giveaway]:
    rows = QueryHelper.fetch_all(
        """
        SELECT id, guild_id, channel_id, message_id, prize, winners_count, ends_at, ended
        FROM discord_giveaways
        WHERE ended = FALSE AND ends_at <= NOW()
        """,
        (),
        dict_cursor=True,
    )
    return [
        Giveaway(
            id=int(r["id"]),
            guild_id=str(r["guild_id"]),
            channel_id=str(r["channel_id"]),
            message_id=r.get("message_id"),
            prize=r["prize"],
            winners_count=int(r["winners_count"]),
            ends_at=r["ends_at"],
            ended=bool(r["ended"]),
        )
        for r in rows or []
    ]


def list_active_giveaways(guild_id: str) -> List[Giveaway]:
    rows = QueryHelper.fetch_all(
        """
        SELECT id, guild_id, channel_id, message_id, prize, winners_count, ends_at, ended
        FROM discord_giveaways
        WHERE guild_id = %s AND ended = FALSE
        ORDER BY ends_at ASC
        """,
        (guild_id,),
        dict_cursor=True,
    )
    return [
        Giveaway(
            id=int(r["id"]),
            guild_id=str(r["guild_id"]),
            channel_id=str(r["channel_id"]),
            message_id=r.get("message_id"),
            prize=r["prize"],
            winners_count=int(r["winners_count"]),
            ends_at=r["ends_at"],
            ended=bool(r["ended"]),
        )
        for r in rows or []
    ]
