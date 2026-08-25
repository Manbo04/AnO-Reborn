"""Persist moderation/auto-mod config, the bad-word list, and the case log.

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same tables with the same shapes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database import QueryHelper, get_db_cursor


@dataclass
class ModerationConfig:
    guild_id: str
    log_channel_id: Optional[str] = None
    filter_spam_enabled: bool = False
    filter_spam_message_limit: int = 5
    filter_spam_interval_seconds: int = 5
    filter_invites_enabled: bool = False
    filter_mass_mentions_enabled: bool = False
    filter_mass_mentions_limit: int = 5
    filter_bad_words_enabled: bool = False
    filter_action: str = "delete_warn"  # delete_warn | delete_timeout | delete_only
    filter_timeout_minutes: int = 10


@dataclass
class ModCase:
    id: int
    guild_id: str
    action: str
    target_user_id: str
    moderator_user_id: str
    reason: Optional[str]
    duration_minutes: Optional[int]
    created_at: datetime


def get_moderation_config(guild_id: str) -> ModerationConfig:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, log_channel_id, filter_spam_enabled, filter_spam_message_limit,
               filter_spam_interval_seconds, filter_invites_enabled,
               filter_mass_mentions_enabled, filter_mass_mentions_limit,
               filter_bad_words_enabled, filter_action, filter_timeout_minutes
        FROM discord_moderation_config WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return ModerationConfig(guild_id=guild_id)
    return ModerationConfig(
        guild_id=str(row["guild_id"]),
        log_channel_id=row.get("log_channel_id"),
        filter_spam_enabled=bool(row["filter_spam_enabled"]),
        filter_spam_message_limit=int(row["filter_spam_message_limit"]),
        filter_spam_interval_seconds=int(row["filter_spam_interval_seconds"]),
        filter_invites_enabled=bool(row["filter_invites_enabled"]),
        filter_mass_mentions_enabled=bool(row["filter_mass_mentions_enabled"]),
        filter_mass_mentions_limit=int(row["filter_mass_mentions_limit"]),
        filter_bad_words_enabled=bool(row["filter_bad_words_enabled"]),
        filter_action=str(row["filter_action"]),
        filter_timeout_minutes=int(row["filter_timeout_minutes"]),
    )


def set_moderation_config(config: ModerationConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_moderation_config
                (guild_id, log_channel_id, filter_spam_enabled, filter_spam_message_limit,
                 filter_spam_interval_seconds, filter_invites_enabled,
                 filter_mass_mentions_enabled, filter_mass_mentions_limit,
                 filter_bad_words_enabled, filter_action, filter_timeout_minutes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                log_channel_id = EXCLUDED.log_channel_id,
                filter_spam_enabled = EXCLUDED.filter_spam_enabled,
                filter_spam_message_limit = EXCLUDED.filter_spam_message_limit,
                filter_spam_interval_seconds = EXCLUDED.filter_spam_interval_seconds,
                filter_invites_enabled = EXCLUDED.filter_invites_enabled,
                filter_mass_mentions_enabled = EXCLUDED.filter_mass_mentions_enabled,
                filter_mass_mentions_limit = EXCLUDED.filter_mass_mentions_limit,
                filter_bad_words_enabled = EXCLUDED.filter_bad_words_enabled,
                filter_action = EXCLUDED.filter_action,
                filter_timeout_minutes = EXCLUDED.filter_timeout_minutes,
                updated_at = NOW()
            """,
            (
                config.guild_id,
                config.log_channel_id,
                config.filter_spam_enabled,
                config.filter_spam_message_limit,
                config.filter_spam_interval_seconds,
                config.filter_invites_enabled,
                config.filter_mass_mentions_enabled,
                config.filter_mass_mentions_limit,
                config.filter_bad_words_enabled,
                config.filter_action,
                config.filter_timeout_minutes,
            ),
        )


def list_bad_words(guild_id: str) -> List[str]:
    rows = QueryHelper.fetch_all(
        "SELECT word FROM discord_bad_words WHERE guild_id = %s ORDER BY word ASC",
        (guild_id,),
    )
    return [str(r[0]) for r in rows or []]


def add_bad_word(guild_id: str, word: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_bad_words (guild_id, word) VALUES (%s, %s)
            ON CONFLICT (guild_id, word) DO NOTHING
            """,
            (guild_id, word.strip().lower()),
        )


def remove_bad_word(guild_id: str, word: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            "DELETE FROM discord_bad_words WHERE guild_id = %s AND word = %s",
            (guild_id, word),
        )


def create_case(
    guild_id: str,
    action: str,
    target_user_id: str,
    moderator_user_id: str,
    reason: Optional[str] = None,
    duration_minutes: Optional[int] = None,
) -> int:
    row = QueryHelper.execute_returning(
        """
        INSERT INTO discord_mod_cases
            (guild_id, action, target_user_id, moderator_user_id, reason, duration_minutes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (guild_id, action, target_user_id, moderator_user_id, reason, duration_minutes),
    )
    return int(row[0])


def list_cases(guild_id: str, target_user_id: Optional[str] = None, limit: int = 20) -> List[ModCase]:
    if target_user_id:
        rows = QueryHelper.fetch_all(
            """
            SELECT id, guild_id, action, target_user_id, moderator_user_id, reason,
                   duration_minutes, created_at
            FROM discord_mod_cases
            WHERE guild_id = %s AND target_user_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (guild_id, target_user_id, limit),
            dict_cursor=True,
        )
    else:
        rows = QueryHelper.fetch_all(
            """
            SELECT id, guild_id, action, target_user_id, moderator_user_id, reason,
                   duration_minutes, created_at
            FROM discord_mod_cases
            WHERE guild_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (guild_id, limit),
            dict_cursor=True,
        )
    return [
        ModCase(
            id=int(r["id"]),
            guild_id=str(r["guild_id"]),
            action=str(r["action"]),
            target_user_id=str(r["target_user_id"]),
            moderator_user_id=str(r["moderator_user_id"]),
            reason=r.get("reason"),
            duration_minutes=r.get("duration_minutes"),
            created_at=r["created_at"],
        )
        for r in rows or []
    ]
