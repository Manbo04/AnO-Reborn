"""Persist per-guild server-logging configuration.

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same table with the same shape.
"""

from dataclasses import dataclass
from typing import Optional

from database import QueryHelper, get_db_cursor


@dataclass
class LoggingConfig:
    guild_id: str
    log_channel_id: Optional[str] = None
    log_message_edit: bool = True
    log_message_delete: bool = True
    log_member_join: bool = True
    log_member_leave: bool = True
    log_member_ban: bool = True
    log_member_timeout: bool = True
    log_role_changes: bool = False
    log_channel_changes: bool = False


def get_logging_config(guild_id: str) -> LoggingConfig:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, log_channel_id, log_message_edit, log_message_delete,
               log_member_join, log_member_leave, log_member_ban,
               log_member_timeout, log_role_changes, log_channel_changes
        FROM discord_logging_config WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return LoggingConfig(guild_id=guild_id)
    return LoggingConfig(
        guild_id=str(row["guild_id"]),
        log_channel_id=row.get("log_channel_id"),
        log_message_edit=bool(row["log_message_edit"]),
        log_message_delete=bool(row["log_message_delete"]),
        log_member_join=bool(row["log_member_join"]),
        log_member_leave=bool(row["log_member_leave"]),
        log_member_ban=bool(row["log_member_ban"]),
        log_member_timeout=bool(row["log_member_timeout"]),
        log_role_changes=bool(row["log_role_changes"]),
        log_channel_changes=bool(row["log_channel_changes"]),
    )


def set_logging_config(config: LoggingConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_logging_config
                (guild_id, log_channel_id, log_message_edit, log_message_delete,
                 log_member_join, log_member_leave, log_member_ban,
                 log_member_timeout, log_role_changes, log_channel_changes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                log_channel_id = EXCLUDED.log_channel_id,
                log_message_edit = EXCLUDED.log_message_edit,
                log_message_delete = EXCLUDED.log_message_delete,
                log_member_join = EXCLUDED.log_member_join,
                log_member_leave = EXCLUDED.log_member_leave,
                log_member_ban = EXCLUDED.log_member_ban,
                log_member_timeout = EXCLUDED.log_member_timeout,
                log_role_changes = EXCLUDED.log_role_changes,
                log_channel_changes = EXCLUDED.log_channel_changes,
                updated_at = NOW()
            """,
            (
                config.guild_id,
                config.log_channel_id,
                config.log_message_edit,
                config.log_message_delete,
                config.log_member_join,
                config.log_member_leave,
                config.log_member_ban,
                config.log_member_timeout,
                config.log_role_changes,
                config.log_channel_changes,
            ),
        )
